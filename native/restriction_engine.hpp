/*
 * restriction_engine.hpp — public C ABI of the bot's native (C++) engine.
 *
 * The library is loaded by ``native_engine.py`` through ``ctypes`` and is on
 * the hot path of the bot:
 *
 *   * ``re_scan``          — one pass over an incoming message: is it a command,
 *                            how many t.me links does it carry, is any of them
 *                            private/restricted, is it a ``N-M`` range?
 *                            This is what lets a reply be produced without any
 *                            Python regex pass.
 *   * ``re_parse_link``    — Telegram message-URL parser (the single source of
 *                            truth for the link grammar used everywhere).
 *   * ``re_bucket_charge`` — token-bucket token accounting for the ⚙️ Python
 *                            Standard throughput cap (pure maths, no sleeping).
 *   * ``re_gov_*``         — the FloodWait governor: per-chat cooldown /
 *                            penalty bookkeeping shared by the dump channels,
 *                            the owner dump mirror and the giveaway poster.
 *   * ``re_escape_batch``  — HTML escaping of a whole broadcast batch on the
 *                            real ``std::thread`` pool (``re_pool_*``).
 *
 * Everything is plain C so the ABI never depends on the compiler's C++ ABI.
 * No function ever throws across the boundary and no function takes ownership
 * of a caller pointer.
 */
#ifndef RESTRICTION_ENGINE_HPP
#define RESTRICTION_ENGINE_HPP

#include <stddef.h>

#if defined(_WIN32)
#  define RE_API __declspec(dllexport)
#else
#  define RE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/*: ABI number — native_engine.py refuses a library that does not match. */
#define RE_ABI_VERSION 3

/* ------------------------------------------------------------------ */
/*  Version / diagnostics                                             */
/* ------------------------------------------------------------------ */

/*: Human readable version of the engine ("3.0.0"). */
RE_API const char *re_version(void);

/*: Compile-time ABI version (must equal RE_ABI_VERSION). */
RE_API int re_abi_version(void);

/*: Compiler identification string used at build time. */
RE_API const char *re_compiler(void);

/*: Self test — returns 0 when every internal check passes, otherwise the
 *  number of the first failing check.  Cheap enough to run at startup. */
RE_API int re_selftest(void);

/* ------------------------------------------------------------------ */
/*  Message scan (classification + link analysis in one pass)         */
/* ------------------------------------------------------------------ */

/*: Bit flags of re_scan_t.flags. */
#define RE_F_COMMAND       (1 << 0)   /* /command[...] at the start of the text  */
#define RE_F_UNKNOWN       (1 << 1)   /* command that is not in the registry     */
#define RE_F_LINK          (1 << 2)   /* at least one t.me link                  */
#define RE_F_PRIVATE_LINK  (1 << 3)   /* t.me/c/… or an invite link              */
#define RE_F_INVITE        (1 << 4)   /* t.me/+hash or t.me/joinchat/hash        */
#define RE_F_RANGE         (1 << 5)   /* …/N-M single range request              */
#define RE_F_MULTI         (1 << 6)   /* more than one distinct link             */
#define RE_F_USERNAME_LINK (1 << 7)   /* t.me/<public name>/<id>                 */
#define RE_F_PLAIN_TEXT    (1 << 8)   /* no command and no link                  */

typedef struct re_scan_s {
    int        flags;          /* bitmask of RE_F_*                        */
    int        command_index;  /* index in the registered table, -1 if none */
    int        command_len;    /* length of the command word ("/pin" -> 4)  */
    int        link_count;     /* distinct t.me links found                 */
    int        is_private;     /* 1 when the first link needs a session     */
    long long  first_id;       /* message id of the last link, 0 when none  */
    long long  range_start;    /* first id of an N-M range, 0 when none     */
    long long  range_end;      /* last id of an N-M range, 0 when none      */
} re_scan_t;

/*: Register the command names the scan must recognise (called once at start).
 *  The strings are copied; the caller keeps ownership of its buffers. */
RE_API void re_register_commands(const char *const *names, size_t count);

/*: Number of registered commands. */
RE_API int re_command_count(void);

/*: Name of a registered command by index (NULL when out of range). */
RE_API const char *re_command_name(int index);

/*: Classify *text*; fills *out* and returns the same value as out->flags.
 *  Returns 0 and leaves *out* zeroed when the input is NULL/empty. */
RE_API int re_scan(const char *text, re_scan_t *out);

/* ------------------------------------------------------------------ */
/*  Telegram message-link parser                                      */
/* ------------------------------------------------------------------ */

/*: Parse a single Telegram message URL.
 *  On success returns 1, writes the chat reference (``@name`` style without
 *  '@', or the numeric ``-100…`` id) into ``out_target``, the message id into
 *  ``*out_msg_id`` and the private flag into ``*out_is_private``.
 *  Returns 0 when the text is not a Telegram message link. */
RE_API int re_parse_link(const char *link,
                         char *out_target, size_t target_len,
                         long long *out_msg_id, int *out_is_private);

/* ------------------------------------------------------------------ */
/*  Token bucket (⚙️ Python Standard speed cap)                       */
/* ------------------------------------------------------------------ */

typedef struct re_bucket_s {
    double tokens;       /* tokens (bytes) currently in the bucket       */
    double updated_at;   /* clock reading of the last refill (seconds)   */
} re_bucket_t;

/*: Charge ``nbytes`` to the bucket.
 *
 *   * ``rate_bps``     refill rate in bytes/second (``<= 0`` disables the cap)
 *   * ``capacity``     bucket size in bytes
 *   * ``refill_now``   clock reading used for the refill step
 *   * ``update_now``   clock reading stored when a wait is owed
 *
 *  Returns the seconds the caller must sleep (``0.0`` = nothing owed) and
 *  updates the bucket in place exactly like the pure-Python implementation. */
RE_API double re_bucket_charge(re_bucket_t *bucket, double nbytes,
                               double rate_bps, double capacity,
                               double refill_now, double update_now);

/* ------------------------------------------------------------------ */
/*  FloodWait governor                                                */
/* ------------------------------------------------------------------ */

/*: Record a request for *key* and return the milliseconds the caller must
 *  wait before it may hit Telegram again (0 = go ahead now). */
RE_API long long re_gov_pause_ms(const char *key, double now, long long cooldown_ms);

/*: A FloodWait of *seconds* arrived: block this key for that long. */
RE_API void re_gov_penalize(const char *key, long long seconds);

/*: Forget a key (used when a chat is disconnected). */
RE_API void re_gov_release(const char *key);

/*: How many keys the governor is tracking (diagnostics/tests). */
RE_API int re_gov_count(void);

/*: Total milliseconds this process has been told to wait so far. */
RE_API long long re_gov_total_wait_ms(void);

/* ------------------------------------------------------------------ */
/*  Parallel text formatting pool                                     */
/* ------------------------------------------------------------------ */

/*: Threads the internal pool starts (``RE_THREADS`` env, default: the number
 *  of hardware threads, clamped to 1..32). */
RE_API int re_pool_threads(void);

/*: Number of jobs the pool has completed since the process started. */
RE_API long long re_pool_tasks(void);

/*: HTML-escape ``count`` NUL terminated strings **in parallel**.
 *
 *   * ``inputs``   — ``count`` source strings (UTF-8, NUL terminated)
 *   * ``outputs``  — ``count`` caller-allocated buffers
 *   * ``out_len``  — size of every buffer in ``outputs``
 *   * ``threads``  — 0 = the pool default; 1 forces the serial path
 *
 *  Returns the number of strings that fitted into their buffer (a truncated
 *  string is still NUL terminated and counted as escaped). */
RE_API size_t re_escape_batch(const char *const *inputs, size_t count,
                             char *const *outputs, size_t out_len, int threads);

/*: HTML-escape one string (used for the caption path and by the tests). */
RE_API size_t re_escape_html(const char *input, char *output, size_t out_len);

/* ------------------------------------------------------------------ */
/*  Benchmarking (exposed on the /engine page and in the tests)       */
/* ------------------------------------------------------------------ */

/*: Run ``iterations`` escapes of the built-in corpus; returns nanoseconds. */
RE_API long long re_bench_escape(long long iterations, int threads);

#ifdef __cplusplus
}  /* extern "C" */
#endif

#endif /* RESTRICTION_ENGINE_HPP */
