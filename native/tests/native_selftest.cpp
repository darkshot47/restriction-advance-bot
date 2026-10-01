/*
 * native_selftest.cpp — standalone verification of the native engine.
 *
 * It never needs Python: ``make test`` builds this binary and runs it, which is
 * how CI proves the C++ half of the engine is healthy before the pytest suite
 * (which loads the same library through ctypes) runs.
 */

#include "../restriction_engine.hpp"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

static int failures = 0;

static void check(bool condition, const char *what) {
    if (!condition) {
        std::printf("FAIL: %s\n", what);
        ++failures;
    }
}

static std::string escape(const std::string &input) {
    std::vector<char> buffer(512, '\0');
    re_escape_html(input.c_str(), buffer.data(), buffer.size());
    return std::string(buffer.data());
}

int main() {
    std::printf("restriction_engine %s (ABI %d, %s)\n",
                re_version(), re_abi_version(), re_compiler());

    int selftest = re_selftest();
    check(selftest == 0, "re_selftest() must pass");
    if (selftest != 0) std::printf("  selftest reported check #%d\n", selftest);

    /* --- link grammar ------------------------------------------------ */
    struct LinkCase {
        const char *link;
        const char *target;
        long long msg_id;
        int is_private;
    };
    const LinkCase links[] = {
        {"t.me/channel/123", "channel", 123, 0},
        {"https://t.me/telegram/55", "telegram", 55, 0},
        {"t.me/s/channel/77", "channel", 77, 0},
        {"t.me/c/1234567890/50", "-1001234567890", 50, 1},
        {"https://t.me/c/1234567890/9/45", "-1001234567890", 45, 0 | 1},
        {"telegram.me/MyChannel_1/8", "MyChannel_1", 8, 0},
        {"t.me/channel/0", "", 0, 0},
        {"t.me/share/url", "", 0, 0},
        {"https://example.com/channel/5", "", 0, 0},
        {"not a link", "", 0, 0},
    };
    for (const LinkCase &test : links) {
        char target[128] = {0};
        long long msg_id = -1;
        int is_private = -1;
        int ok = re_parse_link(test.link, target, sizeof(target), &msg_id, &is_private);
        check(ok == (test.target[0] != '\0'), test.link);
        if (ok) {
            check(std::strcmp(target, test.target) == 0, test.link);
            check(msg_id == test.msg_id, test.link);
            check(is_private == test.is_private, test.link);
        }
    }

    /* --- command registry + scan ------------------------------------- */
    const char *commands[] = {"/start", "/pin", "/pinned", "/giveaway", "broadcast"};
    re_register_commands(commands, 5);
    check(re_command_count() == 5, "five commands registered");
    check(std::strcmp(re_command_name(1), "pin") == 0, "index 1 is pin");

    re_scan_t scan;
    re_scan("/pin", &scan);
    check((scan.flags & RE_F_COMMAND) != 0, "/pin is a command");
    check(scan.command_index == 1, "/pin resolves to index 1");
    re_scan("/PIN@MyBot now", &scan);
    check(scan.command_index == 1, "/PIN@MyBot is case insensitive");
    re_scan("/unknown", &scan);
    check((scan.flags & RE_F_UNKNOWN) != 0, "unknown commands are flagged");

    re_scan("t.me/abcd/1\nt.me/abcd/2", &scan);
    check((scan.flags & RE_F_MULTI) != 0, "multi-link posts are detected");
    check(scan.link_count == 2, "two links counted");
    re_scan("t.me/c/1234567890/5", &scan);
    check((scan.flags & RE_F_PRIVATE_LINK) != 0, "private links are detected");
    re_scan("t.me/c/1234567890/1-500", &scan);
    check((scan.flags & RE_F_RANGE) != 0, "ranges are detected");
    check(scan.range_start == 1 && scan.range_end == 500, "range bounds parsed");
    re_scan("hello there", &scan);
    check((scan.flags & RE_F_PLAIN_TEXT) != 0, "plain text is detected");

    /* --- token bucket ------------------------------------------------- */
    re_bucket_t bucket{0.0, 0.0};
    double wait = re_bucket_charge(&bucket, 150.0, 100.0, 0.0, 0.0, 0.0);
    check(wait > 1.49 && wait < 1.51, "150 bytes at 100 B/s waits 1.5 s");
    bucket.tokens = 500.0;
    bucket.updated_at = 0.0;
    wait = re_bucket_charge(&bucket, 150.0, 100.0, 500.0, 0.0, 0.0);
    check(wait == 0.0, "a funded bucket pays instantly");
    check(bucket.tokens == 350.0, "tokens are debited exactly");

    /* --- governor ------------------------------------------------------ */
    check(re_gov_pause_ms("chat:1", 100.0, 3000) == 0, "first request never waits");
    check(re_gov_pause_ms("chat:1", 100.0, 3000) == 3000, "cooldown is enforced");
    re_gov_penalize("chat:1", 5);
    check(re_gov_pause_ms("chat:1", 100.0, 0) >= 7000, "FloodWait extends the block");
    re_gov_release("chat:1");
    check(re_gov_pause_ms("chat:1", 100.0, 3000) == 0, "release clears the key");

    /* --- escaping + the parallel pool ---------------------------------- */
    check(escape("<b>hi</b> & 'x' \"y\"") == "&lt;b&gt;hi&lt;/b&gt; &amp; &#x27;x&#x27; &quot;y&quot;",
          "HTML escaping matches html.escape(quote=True)");

    const size_t count = 4096;
    std::vector<std::string> inputs(count, "<a> & \"b\" 'c'");
    std::vector<std::vector<char>> buffers(count, std::vector<char>(64, '\0'));
    std::vector<const char *> in_ptrs(count);
    std::vector<char *> out_ptrs(count);
    for (size_t i = 0; i < count; ++i) {
        in_ptrs[i] = inputs[i].c_str();
        out_ptrs[i] = buffers[i].data();
    }
    long long before = re_pool_tasks();
    size_t escaped = re_escape_batch(in_ptrs.data(), count, out_ptrs.data(), 64, 0);
    check(escaped == count, "every string of the batch was escaped");
    check(re_pool_tasks() >= before + static_cast<long long>(count), "the pool ran every job");
    check(escape("<x>") == "&lt;x&gt;", "batch output is correct");

    std::printf("threads=%d pool_tasks=%lld bench=%lld ns\n",
                re_pool_threads(), re_pool_tasks(), re_bench_escape(20000, 1));
    if (failures == 0) {
        std::printf("native engine: ALL CHECKS PASSED\n");
        return 0;
    }
    std::printf("native engine: %d CHECK(S) FAILED\n", failures);
    return 1;
}
