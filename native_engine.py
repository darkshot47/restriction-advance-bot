"""Bridge between the bot and the **native C++ engine**.

The engine lives in ``native/`` (``restriction_engine.hpp`` / ``.cpp``) and is
compiled into a shared library.  This module loads that library through
``ctypes`` and exposes a small, typed API to the rest of the bot:

============================  =================================================
``parse_link(text)``          Telegram message-URL parser (same grammar as the
                              rest of the bot, only much cheaper per message).
``scan(text)``                one pass classification of an incoming message:
                              is it a command, which command, how many links,
                              private/restricted links, ``N-M`` ranges.
``register_commands(names)``  hands the bot's command vocabulary to the engine
                              so ``scan`` can resolve commands natively.
``Bucket``                    token-bucket accounting for the ⚙️ Python
                              Standard throughput cap.
``Governor``                  the FloodWait governor (per-chat cooldowns and
                              penalties) used by the dump channels and the
                              owner dump mirror.
``escape_html`` /             HTML escaping, single and **on the thread pool**
``escape_batch``              (a real ``std::thread`` pool inside the library).
``benchmark``                 nanoseconds for N escapes — shown on /engine.
============================  =================================================

Nothing here is required for the bot to work: when no compiler is available (or
``NATIVE_ENGINE=off``) every function falls back to an equivalent pure-Python
implementation with **identical** semantics, and :func:`describe` reports which
backend is live.  That is what keeps a bare clone runnable while a normal deploy
really executes the C++ engine.

Environment
-----------
``NATIVE_ENGINE``      ``auto`` (default) builds/loads when possible, ``off``
                       forces the Python fallback, ``required`` makes a missing
                       library a hard error (used by the test suite).
``NATIVE_ENGINE_LIB``  explicit path to an already-built shared library.
``NATIVE_ENGINE_BUILD`` ``0`` disables the automatic ``make`` invocation.
``RE_THREADS``         thread count of the native pool (default: hardware).
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

__all__ = [
    "Scan", "Bucket", "Governor", "parse_link", "scan", "register_commands",
    "prepare_broadcast",
    "escape_html", "escape_batch", "benchmark", "selftest", "describe",
    "available", "backend", "version", "pool_threads", "pool_tasks",
    "ABI_VERSION",
]

ROOT = Path(__file__).resolve().parent
NATIVE_DIR = ROOT / "native"
BUILD_DIR = NATIVE_DIR / "build"
ABI_VERSION = 3
LIB_NAMES = ("librestriction_engine.so", "librestriction_engine.dylib",
             "restriction_engine.dll")

#: Flags mirrored from ``native/restriction_engine.hpp``.
F_COMMAND = 1 << 0
F_UNKNOWN = 1 << 1
F_LINK = 1 << 2
F_PRIVATE_LINK = 1 << 3
F_INVITE = 1 << 4
F_RANGE = 1 << 5
F_MULTI = 1 << 6
F_USERNAME_LINK = 1 << 7
F_PLAIN_TEXT = 1 << 8

# --------------------------------------------------------------------------- #
#  Library loading
# --------------------------------------------------------------------------- #


class _NativeScan(ctypes.Structure):
    """Layout of ``re_scan_t`` — keep in sync with the header."""

    _fields_ = [
        ("flags", ctypes.c_int),
        ("command_index", ctypes.c_int),
        ("command_len", ctypes.c_int),
        ("link_count", ctypes.c_int),
        ("is_private", ctypes.c_int),
        ("first_id", ctypes.c_longlong),
        ("range_start", ctypes.c_longlong),
        ("range_end", ctypes.c_longlong),
    ]


class _NativeBucket(ctypes.Structure):
    _fields_ = [("tokens", ctypes.c_double), ("updated_at", ctypes.c_double)]


def _mode() -> str:
    return os.environ.get("NATIVE_ENGINE", "auto").strip().lower() or "auto"


def _candidate_paths():
    explicit = os.environ.get("NATIVE_ENGINE_LIB", "").strip()
    if explicit:
        yield Path(explicit)
    for name in LIB_NAMES:
        yield BUILD_DIR / name
        yield NATIVE_DIR / name
        yield ROOT / name


def _build_library() -> tuple[bool, str]:
    """Compile the engine in place.  Returns ``(ok, log)``."""
    if not (NATIVE_DIR / "restriction_engine.cpp").exists():
        return False, "native/restriction_engine.cpp is missing"
    if os.environ.get("NATIVE_ENGINE_BUILD", "1").strip() in {"0", "off", "false", "no"}:
        return False, "automatic build disabled"
    build_dir = BUILD_DIR
    build_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    make = shutil.which("make")
    if make:
        try:
            done = subprocess.run([make, "-C", str(NATIVE_DIR)], capture_output=True,
                                  text=True, timeout=180)
            log_lines.append(done.stdout.strip() or done.stderr.strip())
            if done.returncode == 0 and any(path.exists() for path in _candidate_paths()):
                return True, "\n".join(line for line in log_lines if line)
        except Exception as exc:  # pragma: no cover - depends on the host
            log_lines.append(f"make failed: {exc}")
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        return False, "no C++ compiler found (install g++/clang++ or set NATIVE_ENGINE=off)"
    target = build_dir / "librestriction_engine.so"
    command = [compiler, "-O3", "-std=c++17", "-fPIC", "-shared",
               "-o", str(target), str(NATIVE_DIR / "restriction_engine.cpp"), "-pthread"]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except Exception as exc:  # pragma: no cover - depends on the host
        return False, f"compiler failed: {exc}"
    if done.returncode != 0 or not target.exists():
        return False, (done.stderr or done.stdout or "compilation failed").strip()
    return True, done.stdout.strip()


_LIB = None
_LIB_LOG = ""
_LOADED = False


def _stale(path: Path) -> bool:
    """True when the C++ sources are newer than *path* (a rebuild is needed)."""
    try:
        built_at = path.stat().st_mtime
    except OSError:  # pragma: no cover - the caller checked existence
        return True
    for source in (NATIVE_DIR / "restriction_engine.cpp",
                   NATIVE_DIR / "restriction_engine.hpp"):
        try:
            if source.stat().st_mtime > built_at:
                return True
        except OSError:
            continue
    return False


def _load() -> None:
    """Load (building first when needed) the native library, exactly once."""
    global _LIB_LOG, _LOADED
    if _LOADED:
        return
    _LOADED = True
    mode = _mode()
    if mode in {"0", "off", "false", "no", "python"}:
        _LIB_LOG = "disabled by NATIVE_ENGINE"
        return
    for path in _candidate_paths():
        if path.exists() and not _stale(path):
            lib = _try_open(path)
            if lib is not None:
                return
    ok, log = _build_library()
    _LIB_LOG = log
    if not ok:
        return
    for path in _candidate_paths():
        if path.exists():
            if _try_open(path) is not None:
                return


def _try_open(path: Path):
    global _LIB, _LIB_LOG
    try:
        lib = ctypes.CDLL(str(path))
    except OSError as exc:  # pragma: no cover - depends on the host
        _LIB_LOG = f"cannot load {path.name}: {exc}"
        return None
    try:
        abi = int(lib.re_abi_version())
    except AttributeError:
        _LIB_LOG = f"{path.name} is not a restriction engine"
        return None
    if abi != ABI_VERSION:
        _LIB_LOG = f"{path.name} speaks ABI {abi}, this bridge needs {ABI_VERSION}"
        return None
    _declare(lib)
    _LIB = lib
    _LIB_LOG = f"loaded {path}"
    return lib


def _declare(lib) -> None:
    lib.re_version.restype = ctypes.c_char_p
    lib.re_compiler.restype = ctypes.c_char_p
    lib.re_abi_version.restype = ctypes.c_int
    lib.re_selftest.restype = ctypes.c_int
    lib.re_command_count.restype = ctypes.c_int
    lib.re_command_name.restype = ctypes.c_char_p
    lib.re_command_name.argtypes = [ctypes.c_int]
    lib.re_scan.restype = ctypes.c_int
    lib.re_scan.argtypes = [ctypes.c_char_p, ctypes.POINTER(_NativeScan)]
    lib.re_register_commands.restype = None
    lib.re_register_commands.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t]
    lib.re_parse_link.restype = ctypes.c_int
    lib.re_parse_link.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(ctypes.c_int)]
    lib.re_bucket_charge.restype = ctypes.c_double
    lib.re_bucket_charge.argtypes = [ctypes.POINTER(_NativeBucket), ctypes.c_double,
                                     ctypes.c_double, ctypes.c_double,
                                     ctypes.c_double, ctypes.c_double]
    lib.re_gov_pause_ms.restype = ctypes.c_longlong
    lib.re_gov_pause_ms.argtypes = [ctypes.c_char_p, ctypes.c_double, ctypes.c_longlong]
    lib.re_gov_penalize.restype = None
    lib.re_gov_penalize.argtypes = [ctypes.c_char_p, ctypes.c_longlong]
    lib.re_gov_release.restype = None
    lib.re_gov_release.argtypes = [ctypes.c_char_p]
    lib.re_gov_count.restype = ctypes.c_int
    lib.re_gov_total_wait_ms.restype = ctypes.c_longlong
    lib.re_pool_threads.restype = ctypes.c_int
    lib.re_pool_tasks.restype = ctypes.c_longlong
    lib.re_escape_html.restype = ctypes.c_size_t
    lib.re_escape_html.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
    lib.re_escape_batch.restype = ctypes.c_size_t
    lib.re_escape_batch.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.POINTER(ctypes.c_char)),
                                    ctypes.c_size_t, ctypes.c_int]
    lib.re_bench_escape.restype = ctypes.c_longlong
    lib.re_bench_escape.argtypes = [ctypes.c_longlong, ctypes.c_int]


def _native():
    """The loaded library, or ``None`` when the Python fallback is in charge."""
    _load()
    if _LIB is None and _mode() in {"required", "must", "on"}:
        raise RuntimeError(
            "NATIVE_ENGINE=required but the native engine could not be loaded: "
            f"{_LIB_LOG}"
        )
    return _LIB


# --------------------------------------------------------------------------- #
#  Pure-Python fallbacks — identical semantics, used when no compiler exists
# --------------------------------------------------------------------------- #

_PUBLIC_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")


def _py_parse_link(link):
    """The reference implementation of the link grammar (mirrors the C++ one)."""
    if not link:
        return None, None, None
    parsed = urlparse(link if "://" in link else "https://" + link)
    if parsed.hostname not in {"t.me", "telegram.me", "www.t.me"}:
        return None, None, None
    parts = parsed.path.strip("/").split("/")
    if parts and parts[0] == "s":
        parts = parts[1:]
    try:
        msg_id = int(parts[-1])
        if msg_id <= 0:
            raise ValueError()
        if parts[0] == "c" and len(parts) in {3, 4} and parts[1].isdigit():
            return int("-100" + parts[1]), msg_id, True
        if len(parts) in {2, 3} and _PUBLIC_NAME_RE.fullmatch(parts[0]):
            return parts[0], msg_id, False
    except (ValueError, IndexError):
        pass
    return None, None, None


_LINK_TOKEN_RE = re.compile(r"(?:t\.me|telegram\.me)/\S*", re.IGNORECASE)
_RANGE_RE = re.compile(r"/(\d+)-(\d+)$")
_COMMAND_RE = re.compile(r"^/([A-Za-z][A-Za-z0-9_]*)(?:@[A-Za-z0-9_]+)?(?:\s|$)")


@dataclass
class Scan:
    """Result of :func:`scan` — the native struct, in Python."""

    flags: int = 0
    command_index: int = -1
    command_len: int = 0
    link_count: int = 0
    is_private: bool = False
    first_id: int = 0
    range_start: int = 0
    range_end: int = 0
    command_name: str | None = None
    backend: str = "python"

    @property
    def is_command(self) -> bool:
        return bool(self.flags & F_COMMAND)

    @property
    def is_known_command(self) -> bool:
        return self.is_command and not (self.flags & F_UNKNOWN)

    @property
    def is_link(self) -> bool:
        return bool(self.flags & F_LINK)

    @property
    def is_private_link(self) -> bool:
        return bool(self.flags & F_PRIVATE_LINK)

    @property
    def is_invite(self) -> bool:
        return bool(self.flags & F_INVITE)

    @property
    def is_multi(self) -> bool:
        return bool(self.flags & F_MULTI)

    @property
    def is_range(self) -> bool:
        return bool(self.flags & F_RANGE)

    @property
    def is_plain_text(self) -> bool:
        return bool(self.flags & F_PLAIN_TEXT)

    @property
    def is_username_link(self) -> bool:
        return bool(self.flags & F_USERNAME_LINK)


def _py_scan(text: str, commands=None) -> Scan:
    """Reference implementation of :func:`scan` — mirrors the C++ one exactly."""
    commands = _COMMANDS if commands is None else commands
    result = Scan(backend="python")
    if not text:
        return result
    flags = 0
    if text[0] == "/":
        match = _COMMAND_RE.match(text)
        if match:
            flags |= F_COMMAND
            name = match.group(1).lower()
            result.command_len = len(match.group(1)) + 1
            index = commands.get(name)
            if index is None:
                flags |= F_UNKNOWN
            else:
                result.command_index = index
                result.command_name = name
    link_count = 0
    first_private = False
    first_id = 0
    range_start = range_end = 0
    for token in text.split():
        if "t.me/" not in token and "telegram.me/" not in token:
            continue
        if "joinchat/" in token:
            flags |= F_INVITE | F_PRIVATE_LINK
            if not link_count:
                first_private = True
                link_count = 1
            continue
        target, msg_id, is_private = _py_parse_link(token)
        if target is not None:
            link_count += 1
            if link_count == 1:
                first_private = is_private
                first_id = msg_id
            if is_private:
                flags |= F_PRIVATE_LINK
            elif not str(target).isdigit():
                flags |= F_USERNAME_LINK
        elif "/+" in token:
            flags |= F_INVITE | F_PRIVATE_LINK
            if not link_count:
                first_private = True
                link_count = 1
        if not range_start:
            match = _RANGE_RE.search(token)
            if match:
                start, end = int(match.group(1)), int(match.group(2))
                if start > 0 and end > 0:
                    range_start, range_end = start, end
                    flags |= F_RANGE
    if range_start:
        flags |= F_LINK
    if link_count:
        flags |= F_LINK
    if link_count > 1:
        flags |= F_MULTI
    if not link_count and not range_start and not (flags & F_COMMAND):
        flags |= F_PLAIN_TEXT
    result.flags = flags
    result.link_count = link_count
    result.is_private = bool(first_private)
    result.first_id = first_id
    result.range_start = range_start
    result.range_end = range_end
    return result


_PY_ESCAPE = {ord("&"): "&amp;", ord("<"): "&lt;", ord(">"): "&gt;",
              ord('"'): "&quot;", ord("'"): "&#x27;"}


def _py_escape_html(text: str) -> str:
    return text.translate(_PY_ESCAPE)


# --------------------------------------------------------------------------- #
#  Command registry (shared by both backends)
# --------------------------------------------------------------------------- #

_COMMANDS: dict[str, int] = {}
_COMMAND_NAMES: tuple[str, ...] = ()


def register_commands(names) -> tuple[str, ...]:
    """Teach the engine the bot's command vocabulary (idempotent)."""
    global _COMMAND_NAMES
    cleaned: list[str] = []
    for name in names or ():
        text = str(name or "").strip().lstrip("/").split("@")[0].lower()
        if text and text not in cleaned:
            cleaned.append(text)
    _COMMAND_NAMES = tuple(cleaned)
    _COMMANDS.clear()
    _COMMANDS.update({name: index for index, name in enumerate(cleaned)})
    lib = _native()
    if lib is not None:
        array = (ctypes.c_char_p * len(cleaned))(*[name.encode() for name in cleaned])
        lib.re_register_commands(array, len(cleaned))
    return _COMMAND_NAMES


def command_names() -> tuple[str, ...]:
    return _COMMAND_NAMES


def _command_name(index: int) -> str | None:
    if 0 <= index < len(_COMMAND_NAMES):
        return _COMMAND_NAMES[index]
    return None


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #


def available() -> bool:
    """True when the compiled C++ engine is loaded and answering."""
    return _native() is not None


def backend() -> str:
    return "native" if _native() is not None else "python"


def version() -> str | None:
    lib = _native()
    if lib is None:
        return None
    return lib.re_version().decode()


def pool_threads() -> int:
    lib = _native()
    return int(lib.re_pool_threads()) if lib is not None else 1


def pool_tasks() -> int:
    lib = _native()
    return int(lib.re_pool_tasks()) if lib is not None else 0


def parse_link(link, *, native: bool = True):
    """Parse a Telegram message URL: ``(target, msg_id, is_private)``.

    The native engine answers every ASCII input; non-ASCII inputs (a unicode
    message id, which Python's ``int()`` accepts) keep the Python path so the
    two implementations can never disagree.
    """
    lib = _native() if native else None
    if lib is None or not link:
        return _py_parse_link(link)
    text = link if isinstance(link, str) else str(link)
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return _py_parse_link(text)
    target = ctypes.create_string_buffer(256)
    msg_id = ctypes.c_longlong(0)
    is_private = ctypes.c_int(0)
    ok = lib.re_parse_link(text.encode(), target, len(target),
                           ctypes.byref(msg_id), ctypes.byref(is_private))
    if not ok:
        return None, None, None
    reference = target.value.decode()
    #: ``t.me/c/<id>/<msg>`` resolves to a numeric chat id (the Python path
    #: returns an int there too, so both backends agree type for type).
    if reference.startswith("-") and reference[1:].isdigit():
        return int(reference), int(msg_id.value), bool(is_private.value)
    return reference, int(msg_id.value), bool(is_private.value)


def scan(text: str, *, native: bool = True) -> Scan:
    """Classify one incoming message (command / links / range) in one pass."""
    lib = _native() if native else None
    if lib is None or not text:
        return _py_scan(text or "")
    try:
        payload = text.encode()
    except UnicodeEncodeError:  # pragma: no cover - exotic input only
        return _py_scan(text)
    raw = _NativeScan()
    lib.re_scan(payload, ctypes.byref(raw))
    return Scan(
        flags=int(raw.flags),
        command_index=int(raw.command_index),
        command_len=int(raw.command_len),
        link_count=int(raw.link_count),
        is_private=bool(raw.is_private),
        first_id=int(raw.first_id),
        range_start=int(raw.range_start),
        range_end=int(raw.range_end),
        command_name=_command_name(int(raw.command_index)),
        backend="native",
    )


def escape_html(text: str) -> str:
    """``html.escape(quote=True)`` — on the native path when available."""
    lib = _native()
    if lib is None or not text:
        return _py_escape_html(text or "")
    try:
        payload = text.encode()
    except UnicodeEncodeError:  # pragma: no cover
        return _py_escape_html(text)
    size = len(payload) * 6 + 1
    buffer = ctypes.create_string_buffer(size)
    lib.re_escape_html(payload, buffer, size)
    return buffer.value.decode()


def escape_batch(items, *, threads: int = 0) -> list[str]:
    """HTML-escape a whole list, on the native ``std::thread`` pool."""
    values = [("" if item is None else str(item)) for item in items]
    lib = _native()
    if lib is None or not values:
        return [_py_escape_html(value) for value in values]
    try:
        encoded = [value.encode() for value in values]
    except UnicodeEncodeError:  # pragma: no cover
        return [_py_escape_html(value) for value in values]
    longest = max((len(item) for item in encoded), default=0)
    size = longest * 6 + 1
    count = len(encoded)
    in_array = (ctypes.c_char_p * count)(*encoded)
    buffers = [ctypes.create_string_buffer(size) for _ in range(count)]
    pointer_array = (ctypes.POINTER(ctypes.c_char) * count)(
        *[ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)) for buffer in buffers])
    lib.re_escape_batch(in_array, count, pointer_array, size, int(threads))
    return [buffer.value.decode() for buffer in buffers]


def prepare_broadcast(template: str, names, *, placeholder: str = "{name}",
                      threads: int = 0) -> list[str]:
    """Personalise one broadcast message per recipient, escaped on the pool.

    The owner's template and every ``{name}`` substitution are HTML-escaped, so
    a display name containing ``<`` can never break a ``parse_mode=HTML`` send —
    and a long broadcast really does the work on the native ``std::thread`` pool
    (the Python fallback produces exactly the same strings).
    """
    values = ["" if name is None else str(name) for name in names]
    safe_template = escape_html(template or "")
    escaped = escape_batch(values, threads=threads)
    if placeholder and placeholder in safe_template:
        return [safe_template.replace(placeholder, name) for name in escaped]
    return [safe_template for _ in escaped]


class Bucket:
    """Token bucket for the ⚙️ Python Standard speed cap.

    ``charge(nbytes, refill_now, update_now)`` returns the seconds the caller
    must sleep — pure maths, identically implemented by the C++ engine.
    """

    def __init__(self, tokens: float = 0.0, updated_at: float = 0.0, *, native: bool = True):
        self.tokens = float(tokens)
        self.updated_at = float(updated_at)
        self._native = native and _native() is not None
        self._struct = _NativeBucket(self.tokens, self.updated_at) if self._native else None

    @property
    def backend(self) -> str:
        return "native" if self._native else "python"

    def sync(self, tokens: float | None = None, updated_at: float | None = None) -> None:
        """Push the Python-side state into the native struct (after a reset)."""
        if tokens is not None:
            self.tokens = float(tokens)
        if updated_at is not None:
            self.updated_at = float(updated_at)
        if self._struct is not None:
            self._struct.tokens = self.tokens
            self._struct.updated_at = self.updated_at

    def charge(self, nbytes: float, rate_bps: float, capacity: float,
               refill_now: float, update_now: float) -> float:
        """Seconds owed for *nbytes*; updates the bucket in place."""
        if self._struct is not None and _LIB is not None:
            wait = float(_LIB.re_bucket_charge(
                ctypes.byref(self._struct), float(nbytes), float(rate_bps),
                float(capacity), float(refill_now), float(update_now)))
            self.tokens = float(self._struct.tokens)
            self.updated_at = float(self._struct.updated_at)
            return wait
        # Reference (pure Python) implementation — identical arithmetic.
        if rate_bps <= 0 or nbytes <= 0:
            return 0.0
        elapsed = max(0.0, refill_now - self.updated_at)
        self.updated_at = refill_now
        tokens = min(capacity, self.tokens + elapsed * rate_bps)
        if nbytes <= tokens:
            self.tokens = tokens - nbytes
            return 0.0
        deficit = nbytes - tokens
        wait = deficit / rate_bps
        self.tokens = 0.0
        self.updated_at = update_now + wait
        return wait


class Governor:
    """FloodWait governor: per-key cooldowns and penalties.

    Keys are plain strings (``"chat:-100123"``, ``"mirror"``, …).  The native
    implementation keeps one hash table behind a mutex and is shared by every
    dump channel, the owner mirror and the giveaway poster.
    """

    def __init__(self, cooldown_ms: int = 3000, *, native: bool = True):
        self.cooldown_ms = int(cooldown_ms)
        self._native = native and _native() is not None
        self._ready_at: dict[str, float] = {}
        self._total_wait_ms = 0

    @property
    def backend(self) -> str:
        return "native" if self._native else "python"

    def pause_ms(self, key: str, now: float, cooldown_ms: int | None = None) -> int:
        """Claim *key*: returns the milliseconds the caller must wait."""
        cooldown = self.cooldown_ms if cooldown_ms is None else int(cooldown_ms)
        if self._native and _LIB is not None:
            return int(_LIB.re_gov_pause_ms(str(key).encode(), float(now), cooldown))
        ready = self._ready_at.get(key, 0.0)
        wait_ms = 0
        if ready > now:
            wait_ms = int((ready - now) * 1000.0 + 0.999)
        base = ready if ready > now else now
        self._ready_at[key] = base + cooldown / 1000.0
        self._total_wait_ms += wait_ms
        return wait_ms

    def penalize(self, key: str, seconds: int) -> None:
        """A FloodWait of *seconds* arrived — block this key for that long."""
        if seconds <= 0:
            return
        if self._native and _LIB is not None:
            _LIB.re_gov_penalize(str(key).encode(), int(seconds))
            return
        self._ready_at[key] = self._ready_at.get(key, 0.0) + float(seconds)
        self._total_wait_ms += int(seconds) * 1000

    def release(self, key: str) -> None:
        if self._native and _LIB is not None:
            _LIB.re_gov_release(str(key).encode())
            return
        self._ready_at.pop(key, None)

    def count(self) -> int:
        if self._native and _LIB is not None:
            return int(_LIB.re_gov_count())
        return len(self._ready_at)

    def total_wait_ms(self) -> int:
        if self._native and _LIB is not None:
            return int(_LIB.re_gov_total_wait_ms())
        return self._total_wait_ms


def benchmark(iterations: int = 200000, threads: int = 1) -> int:
    """Nanoseconds the engine needs for *iterations* escapes."""
    lib = _native()
    if lib is None:
        import time
        start = time.perf_counter()
        for _ in range(max(1, iterations)):
            _py_escape_html("<b>Restriction Advance Bot</b> & \"friends\" — 100% safe: 5000 files")
        return int((time.perf_counter() - start) * 1e9)
    return int(lib.re_bench_escape(int(iterations), int(threads)))


def selftest() -> int:
    """``0`` when the native engine's internal checks pass."""
    lib = _native()
    return 0 if lib is None else int(lib.re_selftest())


def describe() -> dict:
    """Everything the /engine page and the logs need to know."""
    lib = _native()
    info = {
        "backend": "native" if lib is not None else "python",
        "version": None,
        "compiler": None,
        "threads": 1,
        "tasks": 0,
        "governor_keys": 0,
        "governor_wait_ms": 0,
        "log": _LIB_LOG,
        "library": None,
        "commands": len(_COMMAND_NAMES),
        "selftest": 0,
    }
    if lib is None:
        return info
    info.update({
        "version": lib.re_version().decode(),
        "compiler": lib.re_compiler().decode(),
        "threads": int(lib.re_pool_threads()),
        "tasks": int(lib.re_pool_tasks()),
        "governor_keys": int(lib.re_gov_count()),
        "governor_wait_ms": int(lib.re_gov_total_wait_ms()),
        "selftest": int(lib.re_selftest()),
    })
    for name in LIB_NAMES:
        candidate = BUILD_DIR / name
        if candidate.exists():
            info["library"] = str(candidate)
            break
    return info


def startup_report() -> str:
    """One-line status for the startup log."""
    info = describe()
    if info["backend"] == "python":
        return f"🐍 Native C++ engine: not loaded ({info['log']}) — using the Python fallback"
    return (f"⚡ Native C++ engine: v{info['version']} ({info['compiler'].split()[0]}, "
            f"{info['threads']} threads, {info['commands']} commands, "
            f"selftest={'ok' if info['selftest'] == 0 else info['selftest']})")


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    print(startup_report())
    print(f"parse t.me/c/1234567890/5 -> {parse_link('t.me/c/1234567890/5')}")
    print(f"scan  /pin t.me/abcd/1-9  -> {scan('/pin t.me/abcd/1-9')}")
    print(f"bench 200k escapes       -> {benchmark(200000, 1) / 1e6:.2f} ms")
    sys.exit(0 if (selftest() == 0) else 1)
