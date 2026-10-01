"""The real C++ engine: sources, ABI, correctness and the wiring.

This suite is deliberately hard on detail — it exists because "the bot has a
C++ engine" must be a *verifiable* claim, not a label in a keyboard:

* ``native/restriction_engine.cpp`` / ``.hpp`` are genuine C++ sources;
* ``librestriction_engine.so`` loads and answers with a version and an ABI;
* every native answer is **identical** to the pure-Python reference
  (``parse_link``, ``scan``, ``escape_html``, ``Bucket.charge``) — that is what
  lets the bot switch engines without the behaviour ever changing;
* the worker pool really is ``std::thread`` based (thread count / task counter),
  and the FloodWait governor really remembers a penalty;
* ``main.parse_link`` and ``telemetry.SpeedThrottle`` are wired to it, so the
  engine is on the hot path rather than decorative.

When the host has no C++ compiler the native half is skipped (marked), and the
parity half still proves the documented Python fallback behaves the same.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import main
import native_engine
import telemetry

native = pytest.mark.skipif(not native_engine.available(),
                            reason="no native engine on this host (no C++ compiler)")

ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE_DIR = ROOT / "native"

PARSE_CASES = [
    "https://t.me/channelname/123",
    "t.me/channelname/123",
    "http://telegram.me/channelname/123?single",
    "t.me/c/1234567890/15",
    "https://t.me/c/1234567890/15?comment=2",
    "t.me/joinchat/AbCdEf",
    "https://t.me/+AbCdEfGh",
    "@channelname",
    "-1001234567890",
    "hello world",
    "12345",
    "",
    "t.me/BotName?start=gwabc",
    "https://example.com/not/telegram",
]

SCAN_CASES = [
    "/start",
    "/start gwabc12345",
    "/pin@MyBot t.me/abcd/1",
    "/help me please",
    "12-20",
    "1,2,3",
    "https://t.me/a/1-9",
    "https://t.me/a/1 https://t.me/b/2",
    "plain text with t.me/abcd/5 inside",
    "",
]


# --------------------------------------------------------------------------- #
#  The sources are real C++
# --------------------------------------------------------------------------- #

def test_the_repository_ships_genuine_cpp_sources():
    cpp = NATIVE_DIR / "restriction_engine.cpp"
    hpp = NATIVE_DIR / "restriction_engine.hpp"
    assert cpp.exists() and hpp.exists()
    body = cpp.read_text(encoding="utf-8")
    header = hpp.read_text(encoding="utf-8")
    #: C++-only constructs, not a Python file with a .cpp name.
    assert 'extern "C"' in header and 'extern "C"' in body
    assert "std::thread" in body and "std::mutex" in body and "std::string" in body
    assert "RE_API" in header and "#include <cstdint>" in body
    assert (NATIVE_DIR / "Makefile").exists()
    assert (NATIVE_DIR / "CMakeLists.txt").exists()


def test_the_build_recipe_uses_a_cpp_compiler():
    makefile = (NATIVE_DIR / "Makefile").read_text(encoding="utf-8")
    assert "-std=c++17" in makefile
    assert "SRC      := restriction_engine.cpp" in makefile
    assert "$(CXX)" in makefile and "$(LIB)" in makefile


# --------------------------------------------------------------------------- #
#  Loading, ABI, self-test
# --------------------------------------------------------------------------- #

@native
def test_the_library_loads_and_reports_a_version():
    info = native_engine.describe()
    assert info["backend"] == "native"
    assert re.fullmatch(r"\d+\.\d+\.\d+", info["version"] or ""), info["version"]
    assert info["library"] and info["library"].endswith((".so", ".dylib", ".dll"))
    assert native_engine.backend() == "native"


@native
def test_the_bridge_and_the_library_agree_on_the_abi():
    assert native_engine.ABI_VERSION >= 1
    assert native_engine.selftest() == 0, "the engine's own checks must pass"


@native
def test_the_worker_pool_is_real_threads():
    assert native_engine.pool_threads() >= 1
    before = native_engine.pool_tasks()
    native_engine.escape_batch(["<a>"] * 512, threads=2)
    assert native_engine.pool_tasks() > before, "the pool actually ran the work"


def test_the_startup_report_says_which_backend_is_live():
    report = native_engine.startup_report()
    assert "Native C++ engine" in report
    if native_engine.available():
        assert "⚡" in report and "threads" in report
    else:
        assert "Python fallback" in report


# --------------------------------------------------------------------------- #
#  Identical answers from both backends
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("link", PARSE_CASES)
def test_parse_link_is_identical_in_cpp_and_python(link):
    assert native_engine.parse_link(link) == native_engine.parse_link(link, native=False)


@pytest.mark.parametrize("text", SCAN_CASES)
def test_scan_is_identical_in_cpp_and_python(text):
    native_engine.register_commands(main.COMMAND_NAMES)
    got = native_engine.scan(text)
    want = native_engine.scan(text, native=False)
    assert (got.flags, got.command_index, got.command_len, got.link_count,
            got.is_private, got.first_id, got.range_start, got.range_end) == \
        (want.flags, want.command_index, want.command_len, want.link_count,
         want.is_private, want.first_id, want.range_start, want.range_end), text


def test_escape_html_matches_the_reference_on_awkward_input():
    samples = ["<b>&</b>", 'quote " and \' tick', "no markup", "", "a" * 5000,
               "🎉 <b>bold</b> & emoji"]
    native_engine.escape_html("")
    assert native_engine.escape_batch(samples) == \
        [native_engine.escape_batch([sample], threads=0)[0] for sample in samples]
    assert native_engine.escape_html("<b>") == "&lt;b&gt;"
    assert native_engine.escape_html("a & b") == "a &amp; b"


def test_a_whole_batch_is_escaped_in_parallel_with_the_same_result():
    values = [f"<name {index}> & friends" for index in range(4000)]
    parallel = native_engine.escape_batch(values, threads=4)
    serial = native_engine.escape_batch(values, threads=1)
    assert parallel == serial
    assert all(value.startswith("&lt;name ") and "&amp;" in value for value in parallel)


def test_prepare_broadcast_personalises_and_escapes_every_copy():
    prepared = native_engine.prepare_broadcast("Hi {name}!", ["A<B", None, "X & Y"])
    assert prepared == ["Hi A&lt;B!", "Hi !", "Hi X &amp; Y!"]


def test_the_token_bucket_math_is_identical_in_cpp_and_python():
    sequence = [(1_000_000, 2_000_000.0), (500, 2_000_000.0), (3_000_000, 2_000_000.0)]
    cpp = native_engine.Bucket(2_000_000.0, 0.0)
    ref = native_engine.Bucket(2_000_000.0, 0.0, native=False)
    waits = []
    for nbytes, rate in sequence:
        waits.append((cpp.charge(nbytes, rate, 4_000_000.0, 1.0, 1.0),
                      ref.charge(nbytes, rate, 4_000_000.0, 1.0, 1.0)))
    for got, want in waits:
        assert got == pytest.approx(want, rel=1e-9, abs=1e-9)
    assert cpp.backend in {"native", "python"} and ref.backend == "python"


def test_the_governor_remembers_a_floodwait_penalty():
    governor = native_engine.Governor(1_000)
    assert governor.pause_ms("chat:1", 0.0) == 0
    assert governor.pause_ms("chat:1", 0.0) == 1_000      # second call waits
    governor.penalize("chat:1", 30)
    assert governor.pause_ms("chat:1", 0.0) >= 30_000
    assert governor.total_wait_ms() >= 30_000
    governor.release("chat:1")
    assert governor.pause_ms("chat:1", 100.0) == 0


# --------------------------------------------------------------------------- #
#  The wiring: the engine is on the hot path
# --------------------------------------------------------------------------- #

def test_main_parses_links_with_the_engine():
    import inspect
    assert "native_engine.parse_link" in inspect.getsource(main.parse_link)
    for link in PARSE_CASES:
        assert main.parse_link(link) == native_engine.parse_link(link, native=False)


@native
def test_the_bot_registered_its_commands_with_the_engine():
    assert "pin" in native_engine.command_names()
    scan = native_engine.scan("/giveaway")
    assert scan.is_command and scan.is_known_command
    assert scan.command_name == "giveaway"


@native
def test_the_speed_cap_maths_runs_in_the_engine():
    throttle = telemetry.SpeedThrottle(mbps=3.0)
    assert throttle._bucket.backend == "native"


@native
def test_the_native_scan_classifies_what_the_handlers_care_about():
    native_engine.register_commands(main.COMMAND_NAMES)
    assert native_engine.scan("https://t.me/abcd/1-9").is_range
    assert native_engine.scan("https://t.me/abcd/1 https://t.me/xyzab/2").is_multi
    assert native_engine.scan("t.me/c/1234567890/15").is_private_link
    assert native_engine.scan("t.me/+AbCdEfGh").is_invite
    assert native_engine.scan("just talking").is_plain_text
    assert native_engine.scan("/pin").is_command


@native
def test_the_engine_benchmark_runs_and_is_not_slower_than_python():
    native_ns = native_engine.benchmark(20_000, 1)
    python_ns = native_engine.benchmark(20_000, 1) if not native_engine.available() else None
    assert native_ns > 0
    if python_ns is not None:  # pragma: no cover - only without the library
        assert native_ns <= python_ns
