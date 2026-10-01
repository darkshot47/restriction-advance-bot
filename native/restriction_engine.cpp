/*
 * restriction_engine.cpp — implementation of the native (C++) engine.
 *
 * Design notes
 * ------------
 *  * Everything is written in plain C++17 with no third-party dependency, so
 *    it builds with ``g++ -O3 -shared -fPIC -std=c++17`` on a bare host and
 *    with MSVC through the bundled CMake file.
 *  * The public symbols are ``extern "C"`` (see restriction_engine.hpp), so
 *    ctypes never has to know about C++ name mangling.
 *  * No exception ever crosses the ABI: every entry point is wrapped in
 *    ``RE_GUARD``/try-catch and degrades to a safe "not available" answer.
 *  * The thread pool is created lazily on the first parallel job and joined at
 *    process exit.  ctypes releases the GIL while a native call runs, so the
 *    workers really do run at the same time as the interpreter.
 */

#include "restriction_engine.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#define RE_VERSION "3.0.0"

/* ------------------------------------------------------------------ */
/*  Small helpers                                                     */
/* ------------------------------------------------------------------ */

namespace {

inline bool ascii_digit(char c) { return c >= '0' && c <= '9'; }

inline char lower_ascii(char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
}

inline bool ascii_alpha(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

/*: Python's ``str.strip("/")`` for a path. */
std::string strip_slashes(const std::string &value) {
    size_t begin = value.find_first_not_of('/');
    if (begin == std::string::npos) return std::string();
    size_t end = value.find_last_not_of('/');
    return value.substr(begin, end - begin + 1);
}

std::vector<std::string> split_slashes(const std::string &value) {
    std::vector<std::string> parts;
    std::string current;
    for (char c : value) {
        if (c == '/') {
            parts.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    parts.push_back(current);
    return parts;
}

/*: Strict integer parse (the link grammar only ever uses ASCII digits). */
bool parse_ll(const std::string &text, long long *out) {
    if (text.empty()) return false;
    size_t index = 0;
    bool negative = false;
    if (text[0] == '+' || text[0] == '-') {
        negative = text[0] == '-';
        index = 1;
    }
    if (index >= text.size()) return false;
    long long value = 0;
    for (; index < text.size(); ++index) {
        if (!ascii_digit(text[index])) return false;
        value = value * 10 + (text[index] - '0');
        if (value > 100000000000000000LL) return false;  /* overflow guard */
    }
    *out = negative ? -value : value;
    return true;
}

bool all_digits(const std::string &text) {
    if (text.empty()) return false;
    for (char c : text)
        if (!ascii_digit(c)) return false;
    return true;
}

/*: ``[A-Za-z][A-Za-z0-9_]{3,31}`` — a public channel username. */
bool is_public_name(const std::string &text) {
    if (text.size() < 4 || text.size() > 32) return false;
    if (!ascii_alpha(text[0])) return false;
    for (char c : text)
        if (!ascii_alpha(c) && !ascii_digit(c) && c != '_') return false;
    return true;
}

/* ------------------------------------------------------------------ */
/*  Telegram link parser                                              */
/* ------------------------------------------------------------------ */

struct ParsedLink {
    bool ok = false;
    std::string target;     /* username without '@' or numeric chat id */
    long long msg_id = 0;
    bool is_private = false;
};

/*: Mirror of ``main.parse_link`` — same grammar, same edge cases. */
ParsedLink parse_link_impl(const std::string &raw) {
    ParsedLink result;

    /* 1) scheme: "https://t.me/…" or a bare "t.me/…" */
    std::string url = raw;
    if (url.find("://") == std::string::npos) url = "https://" + url;
    size_t scheme_end = url.find("://") + 3;
    std::string rest = url.substr(scheme_end);

    /* 2) host (everything before the first '/'), honouring userinfo and port */
    size_t slash = rest.find('/');
    std::string host = (slash == std::string::npos) ? rest : rest.substr(0, slash);
    std::string path = (slash == std::string::npos) ? std::string() : rest.substr(slash);
    size_t at = host.find('@');
    if (at != std::string::npos) host = host.substr(at + 1);
    size_t colon = host.find(':');
    if (colon != std::string::npos) host = host.substr(0, colon);
    for (char &c : host) c = lower_ascii(c);
    if (host != "t.me" && host != "telegram.me" && host != "www.t.me") return result;

    /* 3) path: drop the query/fragment, then the "/s/" preview prefix */
    size_t cut = path.find_first_of("?#");
    if (cut != std::string::npos) path = path.substr(0, cut);
    std::vector<std::string> parts = split_slashes(strip_slashes(path));
    if (!parts.empty() && parts[0] == "s") parts.erase(parts.begin());
    if (parts.empty()) return result;

    /* 4) the last segment must be a positive message id */
    long long msg_id = 0;
    if (!parse_ll(parts.back(), &msg_id) || msg_id <= 0) return result;

    /* 5) private form: t.me/c/<internal id>/<msg> (optionally a topic) */
    if (parts[0] == "c" && (parts.size() == 3 || parts.size() == 4) && all_digits(parts[1])) {
        result.ok = true;
        result.target = "-100" + parts[1];
        result.msg_id = msg_id;
        result.is_private = true;
        return result;
    }

    /* 6) public form: t.me/<name>/<msg> (optionally a topic) */
    if ((parts.size() == 2 || parts.size() == 3) && is_public_name(parts[0])) {
        result.ok = true;
        result.target = parts[0];
        result.msg_id = msg_id;
        result.is_private = false;
        return result;
    }
    return result;
}

/* ------------------------------------------------------------------ */
/*  Command registry                                                  */
/* ------------------------------------------------------------------ */

class CommandRegistry {
public:
    void set(const std::vector<std::string> &names) {
        std::lock_guard<std::mutex> guard(mutex_);
        names_ = names;
        index_.clear();
        for (size_t i = 0; i < names_.size(); ++i)
            index_[names_[i]] = static_cast<int>(i);
    }

    int find(const std::string &name) const {
        std::lock_guard<std::mutex> guard(mutex_);
        auto it = index_.find(name);
        return it == index_.end() ? -1 : it->second;
    }

    int size() const {
        std::lock_guard<std::mutex> guard(mutex_);
        return static_cast<int>(names_.size());
    }

    const char *name(int index, std::string *storage) const {
        std::lock_guard<std::mutex> guard(mutex_);
        if (index < 0 || index >= static_cast<int>(names_.size())) return nullptr;
        *storage = names_[index];
        return storage->c_str();
    }

private:
    mutable std::mutex mutex_;
    std::vector<std::string> names_;
    std::unordered_map<std::string, int> index_;
};

CommandRegistry &registry() {
    static CommandRegistry instance;
    return instance;
}

/* ------------------------------------------------------------------ */
/*  Message scan                                                      */
/* ------------------------------------------------------------------ */

struct LinkHit {
    ParsedLink link;
    bool is_range = false;
    long long range_start = 0;
    long long range_end = 0;
};

/*: Split the text into whitespace separated tokens (links are never spaced). */
std::vector<std::string> tokenise(const std::string &text) {
    std::vector<std::string> tokens;
    std::string current;
    for (char c : text) {
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f') {
            if (!current.empty()) tokens.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    if (!current.empty()) tokens.push_back(current);
    return tokens;
}

/*: ``…/N-M`` range requests live on their own token. */
bool range_of(const std::string &token, long long *start, long long *end) {
    size_t dash = token.rfind('-');
    if (dash == std::string::npos || dash == 0 || dash + 1 >= token.size()) return false;
    std::string head = token.substr(0, dash);
    std::string tail = token.substr(dash + 1);
    size_t slash = head.rfind('/');
    if (slash == std::string::npos || slash + 1 >= head.size()) return false;
    std::string left = head.substr(slash + 1);
    if (!all_digits(left) || !all_digits(tail)) return false;
    long long a = 0, b = 0;
    if (!parse_ll(left, &a) || !parse_ll(tail, &b)) return false;
    if (a <= 0 || b <= 0) return false;
    *start = a;
    *end = b;
    return true;
}

bool looks_like_link_token(const std::string &token) {
    return token.find("t.me/") != std::string::npos ||
           token.find("telegram.me/") != std::string::npos;
}

int scan_impl(const std::string &text, re_scan_t *out) {
    std::memset(out, 0, sizeof(*out));
    out->command_index = -1;
    if (text.empty()) return 0;

    int flags = 0;
    int link_count = 0;
    bool first_private = false;
    long long first_id = 0;
    long long range_start = 0, range_end = 0;

    /* commands: "/name", "/name@bot" at the very start of the message */
    if (text[0] == '/') {
        size_t index = 1;
        std::string name;
        while (index < text.size() &&
               (ascii_alpha(text[index]) || ascii_digit(text[index]) || text[index] == '_')) {
            name.push_back(lower_ascii(text[index]));
            ++index;
        }
        bool well_formed = !name.empty() && ascii_alpha(name[0]);
        if (well_formed && index < text.size() && text[index] == '@') {
            size_t at = index + 1;
            while (at < text.size() &&
                   (ascii_alpha(text[at]) || ascii_digit(text[at]) || text[at] == '_')) ++at;
            if (at == index + 1) well_formed = false;
            index = at;
        }
        if (well_formed && index < text.size() && !std::isspace(static_cast<unsigned char>(text[index])))
            well_formed = false;
        if (well_formed) {
            flags |= RE_F_COMMAND;
            out->command_len = static_cast<int>(name.size()) + 1;
            int found = registry().find(name);
            out->command_index = found;
            if (found < 0) flags |= RE_F_UNKNOWN;
        }
    }

    for (const std::string &token : tokenise(text)) {
        if (!looks_like_link_token(token)) continue;
        if (token.find("joinchat/") != std::string::npos) {
            flags |= RE_F_INVITE | RE_F_PRIVATE_LINK;
            if (!link_count) {
                first_private = true;
                link_count = 1;
            }
            continue;
        }
        ParsedLink parsed = parse_link_impl(token);
        if (parsed.ok) {
            ++link_count;
            if (link_count == 1) {
                first_private = parsed.is_private;
                first_id = parsed.msg_id;
            }
            if (parsed.is_private) flags |= RE_F_PRIVATE_LINK;
            else if (!parsed.target.empty() && !ascii_digit(parsed.target[0]))
                flags |= RE_F_USERNAME_LINK;
        } else if (token.find("/+") != std::string::npos) {
            flags |= RE_F_INVITE | RE_F_PRIVATE_LINK;
            if (!link_count) {
                first_private = true;
                link_count = 1;
            }
        }
        if (range_start == 0 && range_of(token, &range_start, &range_end)) flags |= RE_F_RANGE;
    }

    /* A "…/1-500" range request is link-bearing even though the N-M tail is
     * not a parseable single message id. */
    if (range_start) flags |= RE_F_LINK;
    if (link_count) flags |= RE_F_LINK;
    if (link_count > 1) flags |= RE_F_MULTI;
    if (!link_count && !range_start && !(flags & RE_F_COMMAND)) flags |= RE_F_PLAIN_TEXT;

    out->flags = flags;
    out->link_count = link_count;
    out->is_private = first_private ? 1 : 0;
    out->first_id = first_id;
    out->range_start = range_start;
    out->range_end = range_end;
    return flags;
}

/* ------------------------------------------------------------------ */
/*  Token bucket                                                      */
/* ------------------------------------------------------------------ */

double bucket_charge_impl(re_bucket_t *bucket, double nbytes, double rate,
                          double capacity, double refill_now, double update_now) {
    if (bucket == nullptr || rate <= 0.0 || nbytes <= 0.0) return 0.0;

    double elapsed = refill_now - bucket->updated_at;
    if (elapsed < 0.0) elapsed = 0.0;
    bucket->updated_at = refill_now;
    double tokens = bucket->tokens + elapsed * rate;
    if (tokens > capacity) tokens = capacity;

    if (nbytes <= tokens) {
        bucket->tokens = tokens - nbytes;
        return 0.0;
    }
    double deficit = nbytes - tokens;
    double wait = deficit / rate;
    bucket->tokens = 0.0;
    bucket->updated_at = update_now + wait;
    return wait;
}

/* ------------------------------------------------------------------ */
/*  FloodWait governor                                                */
/* ------------------------------------------------------------------ */

struct GovEntry {
    double ready_at = 0.0;     /* seconds on the caller's clock */
    double last_seen = 0.0;
};

class Governor {
public:
    long long pause_ms(const std::string &key, double now, long long cooldown_ms) {
        std::lock_guard<std::mutex> guard(mutex_);
        GovEntry &entry = entries_[key];
        long long wait_ms = 0;
        if (entry.ready_at > now) wait_ms = static_cast<long long>((entry.ready_at - now) * 1000.0 + 0.999);
        double base = entry.ready_at > now ? entry.ready_at : now;
        entry.ready_at = base + static_cast<double>(cooldown_ms) / 1000.0;
        entry.last_seen = now;
        total_wait_ns_ += static_cast<long long>(wait_ms) * 1000000LL;
        if (wait_ms < 0) wait_ms = 0;
        return wait_ms;
    }

    void penalize(const std::string &key, long long seconds) {
        std::lock_guard<std::mutex> guard(mutex_);
        GovEntry &entry = entries_[key];
        entry.ready_at += static_cast<double>(seconds);
        if (seconds > 0) total_wait_ns_ += seconds * 1000000000LL;
    }

    void release(const std::string &key) {
        std::lock_guard<std::mutex> guard(mutex_);
        entries_.erase(key);
    }

    int count() const {
        std::lock_guard<std::mutex> guard(mutex_);
        return static_cast<int>(entries_.size());
    }

    long long total_wait_ms() const {
        std::lock_guard<std::mutex> guard(mutex_);
        return total_wait_ns_ / 1000000LL;
    }

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, GovEntry> entries_;
    long long total_wait_ns_ = 0;
};

Governor &governor() {
    static Governor instance;
    return instance;
}

/* ------------------------------------------------------------------ */
/*  Thread pool                                                       */
/* ------------------------------------------------------------------ */

int configured_threads() {
    const char *env = std::getenv("RE_THREADS");
    int threads = 0;
    if (env && *env) threads = std::atoi(env);
    if (threads <= 0) {
        unsigned int hardware = std::thread::hardware_concurrency();
        threads = hardware == 0 ? 2 : static_cast<int>(hardware);
    }
    if (threads < 1) threads = 1;
    if (threads > 32) threads = 32;
    return threads;
}

class TaskPool {
public:
    static TaskPool &instance() {
        static TaskPool pool;
        return pool;
    }

    int threads() const { return threads_; }

    long long tasks() const { return tasks_.load(std::memory_order_relaxed); }

    /*: Run every job on the pool and return once all of them finished. */
    void run(const std::vector<std::function<void()>> &jobs, int threads) {
        if (jobs.empty()) return;
        int limit = threads > 0 ? std::min(threads, threads_) : threads_;
        if (limit <= 1 || threads_ <= 1 || jobs.size() == 1) {
            for (const auto &job : jobs) {
                job();
                tasks_.fetch_add(1, std::memory_order_relaxed);
            }
            return;
        }
        std::atomic<size_t> next{0};
        std::atomic<int> remaining{limit};
        std::mutex done_mutex;
        std::condition_variable done_cv;
        auto worker = [&]() {
            for (;;) {
                size_t index = next.fetch_add(1, std::memory_order_relaxed);
                if (index >= jobs.size()) break;
                jobs[index]();
                tasks_.fetch_add(1, std::memory_order_relaxed);
            }
            if (remaining.fetch_sub(1, std::memory_order_acq_rel) == 1) {
                std::lock_guard<std::mutex> guard(done_mutex);
                done_cv.notify_all();
            }
        };
        std::vector<std::thread> spawned;
        spawned.reserve(static_cast<size_t>(limit));
        for (int i = 0; i < limit; ++i) spawned.emplace_back(worker);
        {
            std::unique_lock<std::mutex> lock(done_mutex);
            done_cv.wait(lock, [&]() { return remaining.load(std::memory_order_acquire) == 0; });
        }
        for (std::thread &thread : spawned) thread.join();
    }

private:
    TaskPool() : threads_(configured_threads()) {}
    ~TaskPool() = default;
    TaskPool(const TaskPool &) = delete;
    TaskPool &operator=(const TaskPool &) = delete;

    int threads_;
    std::atomic<long long> tasks_{0};
};

/* ------------------------------------------------------------------ */
/*  HTML escaping                                                     */
/* ------------------------------------------------------------------ */

size_t escape_impl(const char *input, char *output, size_t out_len) {
    if (output == nullptr || out_len == 0) return 0;
    output[0] = '\0';
    if (input == nullptr) return 0;

    size_t written = 0;
    for (const char *cursor = input; *cursor; ++cursor) {
        const char *replacement = nullptr;
        switch (*cursor) {
            case '&': replacement = "&amp;"; break;
            case '<': replacement = "&lt;"; break;
            case '>': replacement = "&gt;"; break;
            case '"': replacement = "&quot;"; break;
            case '\'': replacement = "&#x27;"; break;
            default: break;
        }
        if (replacement == nullptr) {
            if (written + 1 >= out_len) break;
            output[written++] = *cursor;
            continue;
        }
        size_t length = std::strlen(replacement);
        if (written + length >= out_len) break;
        std::memcpy(output + written, replacement, length);
        written += length;
    }
    output[written] = '\0';
    return written;
}

}  // namespace

/* ------------------------------------------------------------------ */
/*  Exported C ABI                                                    */
/* ------------------------------------------------------------------ */

extern "C" {

RE_API const char *re_version(void) { return RE_VERSION; }

RE_API int re_abi_version(void) { return RE_ABI_VERSION; }

RE_API const char *re_compiler(void) {
#if defined(__clang__)
    return "clang " __clang_version__;
#elif defined(__GNUC__)
    return "gcc " __VERSION__;
#elif defined(_MSC_VER)
    return "msvc";
#else
    return "unknown";
#endif
}

RE_API void re_register_commands(const char *const *names, size_t count) {
    try {
        std::vector<std::string> collected;
        collected.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            if (names == nullptr || names[i] == nullptr) continue;
            std::string name;
            for (const char *c = names[i]; *c; ++c) {
                char lowered = lower_ascii(*c);
                if (lowered == '@') break;  /* "/pin@bot" registers as "pin" */
                if (lowered == '/') continue;
                name.push_back(lowered);
            }
            if (!name.empty()) collected.push_back(name);
        }
        registry().set(collected);
    } catch (...) {
        /* registry left unchanged — the scan simply reports unknown commands */
    }
}

RE_API int re_command_count(void) {
    try {
        return registry().size();
    } catch (...) {
        return 0;
    }
}

RE_API const char *re_command_name(int index) {
    static thread_local std::string storage;
    try {
        return registry().name(index, &storage);
    } catch (...) {
        return nullptr;
    }
}

RE_API int re_scan(const char *text, re_scan_t *out) {
    if (out != nullptr) {
        std::memset(out, 0, sizeof(*out));
        out->command_index = -1;
    }
    if (text == nullptr || out == nullptr || *text == '\0') return 0;
    try {
        return scan_impl(std::string(text), out);
    } catch (...) {
        std::memset(out, 0, sizeof(*out));
        out->command_index = -1;
        return 0;
    }
}

RE_API int re_parse_link(const char *link, char *out_target, size_t target_len,
                         long long *out_msg_id, int *out_is_private) {
    if (out_target != nullptr && target_len > 0) out_target[0] = '\0';
    if (out_msg_id != nullptr) *out_msg_id = 0;
    if (out_is_private != nullptr) *out_is_private = 0;
    if (link == nullptr || out_target == nullptr || target_len == 0) return 0;
    try {
        ParsedLink parsed = parse_link_impl(std::string(link));
        if (!parsed.ok) return 0;
        if (parsed.target.size() + 1 > target_len) return 0;
        std::memcpy(out_target, parsed.target.c_str(), parsed.target.size() + 1);
        if (out_msg_id != nullptr) *out_msg_id = parsed.msg_id;
        if (out_is_private != nullptr) *out_is_private = parsed.is_private ? 1 : 0;
        return 1;
    } catch (...) {
        if (out_target != nullptr && target_len > 0) out_target[0] = '\0';
        return 0;
    }
}

RE_API double re_bucket_charge(re_bucket_t *bucket, double nbytes, double rate_bps,
                               double capacity, double refill_now, double update_now) {
    if (bucket == nullptr) return 0.0;
    try {
        return bucket_charge_impl(bucket, nbytes, rate_bps, capacity, refill_now, update_now);
    } catch (...) {
        return 0.0;
    }
}

RE_API long long re_gov_pause_ms(const char *key, double now, long long cooldown_ms) {
    if (key == nullptr) return 0;
    try {
        return governor().pause_ms(std::string(key), now, cooldown_ms < 0 ? 0 : cooldown_ms);
    } catch (...) {
        return 0;
    }
}

RE_API void re_gov_penalize(const char *key, long long seconds) {
    if (key == nullptr || seconds <= 0) return;
    try {
        governor().penalize(std::string(key), seconds);
    } catch (...) {
    }
}

RE_API void re_gov_release(const char *key) {
    if (key == nullptr) return;
    try {
        governor().release(std::string(key));
    } catch (...) {
    }
}

RE_API int re_gov_count(void) {
    try {
        return governor().count();
    } catch (...) {
        return 0;
    }
}

RE_API long long re_gov_total_wait_ms(void) {
    try {
        return governor().total_wait_ms();
    } catch (...) {
        return 0;
    }
}

RE_API int re_pool_threads(void) {
    try {
        return TaskPool::instance().threads();
    } catch (...) {
        return 1;
    }
}

RE_API long long re_pool_tasks(void) {
    try {
        return TaskPool::instance().tasks();
    } catch (...) {
        return 0;
    }
}

RE_API size_t re_escape_html(const char *input, char *output, size_t out_len) {
    try {
        return escape_impl(input, output, out_len);
    } catch (...) {
        if (output != nullptr && out_len > 0) output[0] = '\0';
        return 0;
    }
}

RE_API size_t re_escape_batch(const char *const *inputs, size_t count,
                              char *const *outputs, size_t out_len, int threads) {
    if (inputs == nullptr || outputs == nullptr || count == 0) return 0;
    try {
        std::atomic<size_t> escaped{0};
        std::vector<std::function<void()>> jobs;
        jobs.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            jobs.emplace_back([&, i]() {
                size_t written = escape_impl(inputs[i], outputs[i], out_len);
                if (written || (inputs[i] != nullptr && inputs[i][0] == '\0')) escaped.fetch_add(1);
            });
        }
        TaskPool::instance().run(jobs, threads);
        return escaped.load();
    } catch (...) {
        return 0;
    }
}

RE_API long long re_bench_escape(long long iterations, int threads) {
    static const char *corpus =
        "<b>Restriction Advance Bot</b> & \"friends\" — 100% safe: 5000 files";
    if (iterations <= 0) return 0;
    const long long total = std::min<long long>(iterations, 2000000);
    std::string buffer(512, '\0');
    auto begin = std::chrono::steady_clock::now();
    if (threads > 1) {
        std::vector<std::function<void()>> jobs;
        int workers = std::min<int>(threads, 16);
        for (int worker = 0; worker < workers; ++worker) {
            jobs.emplace_back([&]() {
                for (long long i = 0; i < total / workers; ++i)
                    escape_impl(corpus, &buffer[0], buffer.size());
            });
        }
        TaskPool::instance().run(jobs, workers);
    } else {
        for (long long i = 0; i < total; ++i) escape_impl(corpus, &buffer[0], buffer.size());
    }
    auto end = std::chrono::steady_clock::now();
    return std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
}

RE_API int re_selftest(void) {
    try {
        /* 1 — the link grammar */
        char target[128];
        long long msg_id = 0;
        int is_private = 0;
        if (!re_parse_link("t.me/channel/123", target, sizeof(target), &msg_id, &is_private))
            return 1;
        if (std::strcmp(target, "channel") != 0 || msg_id != 123 || is_private != 0) return 2;
        if (!re_parse_link("https://t.me/c/1234567890/50", target, sizeof(target), &msg_id, &is_private))
            return 3;
        if (std::strcmp(target, "-1001234567890") != 0 || msg_id != 50 || is_private != 1) return 4;
        if (re_parse_link("t.me/share/url", target, sizeof(target), &msg_id, &is_private)) return 5;

        /* 2 — classification */
        re_scan_t scan;
        re_register_commands(nullptr, 0);
        if (!(re_scan("/help", &scan) & RE_F_COMMAND)) return 6;
        if (!(re_scan("t.me/abcd/1\nt.me/abcd/2", &scan) & RE_F_MULTI)) return 7;
        if ((re_scan("hello", &scan) & RE_F_PLAIN_TEXT) == 0) return 8;

        /* 3 — token bucket */
        re_bucket_t bucket{0.0, 0.0};
        double wait = re_bucket_charge(&bucket, 100.0, 100.0, 0.0, 0.0, 0.0);
        if (wait < 0.999 || wait > 1.001) return 9;

        /* 4 — the parallel pool really started */
        if (re_pool_threads() < 1) return 10;
        const char *input = "<a> & 'b'";
        char output[64];
        if (re_escape_html(input, output, sizeof(output)) == 0) return 11;
        if (std::strcmp(output, "&lt;a&gt; &amp; &#x27;b&#x27;") != 0) return 12;
        return 0;
    } catch (...) {
        return 99;
    }
}

}  /* extern "C" */
