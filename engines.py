"""Dual execution engines: **Python Standard** ⚙️ and **C++ Turbo** 🚀.

The bot can push an extraction through two different execution paths:

``python`` — **Python Standard**
    Single-stream processing.  One extraction job occupies one stream and the
    links of a bulk batch are handled strictly one after another.  This is the
    default for free and sample users and the cheapest path on the server.

``cpp`` — **C++ Turbo**
    Multi-threaded processing.  A bulk batch is spread over a bounded worker
    pool (``config.ENGINE_TURBO_WORKERS`` slots) so the slow parts — the
    MTProto download and the re-upload — overlap instead of queueing, and the
    downloaded file is handed to the uploader *zero-copy*: the on-disk handle
    is passed straight through, never re-read, re-buffered or copied to a
    second temporary file.  The MTProto cipher itself runs in the native
    TgCrypto C extension, which is what keeps the per-chunk latency low.

What lives where
----------------
* ``config.py`` — engine ids, controller modes, thresholds (single source of truth).
* ``engines.py`` — this module: the registry, the autoscaler and the routing rules.
* ``telemetry.py`` — CPU / RAM / ping sampling and transfer speed maths.
* ``ui.py`` — every piece of user-visible copy, including the telemetry HUD.
* ``database.py`` — the persisted global mode and each user's engine preference.

This module is deliberately free of Telegram and database imports so the whole
routing matrix (lock modes, autoscaler, per-user permission) can be unit tested
with in-memory fakes only.

Global controller modes
-----------------------
``auto``        Dynamic autoscaler (default).  Under a traffic spike — more than
                ``ENGINE_PEAK_THRESHOLD`` concurrent extractions — *every*
                request is routed to C++ Turbo to kill the queue.  When traffic
                returns to normal, free users fall back to Python Standard and
                models holders keep whatever they picked.
``lock_cpp``    Global force: 100% of extractions (free **and** VIP) run on
                C++ Turbo.  The autoscaler is paused.
``lock_python`` Global force: the default traffic is locked to Python Standard
                and the autoscaler is disabled.  Free users cannot leave it.
                Premium users holding the ``models`` permission still choose
                their own engine through /models or /engine.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from config import (
    DEFAULT_ENGINE_MODE, ENGINE_CPP, ENGINE_MODE_AUTO, ENGINE_MODE_LOCK_CPP,
    ENGINE_MODE_LOCK_PYTHON, ENGINE_PEAK_THRESHOLD, ENGINE_PYTHON,
    ENGINE_PYTHON_VERSION, ENGINE_TURBO_VERSION, ENGINE_TURBO_WORKERS, ENGINES,
)

#: Human readable engine names (also used to build the HUD and the switcher).
ENGINE_LABELS = {
    ENGINE_PYTHON: "Python Standard",
    ENGINE_CPP: "C++ Turbo",
}

#: Icon rendered in front of an engine name.
ENGINE_ICONS = {
    ENGINE_PYTHON: "⚙️",
    ENGINE_CPP: "🚀",
}

#: Version string of each engine (``None`` → the HUD omits it).
ENGINE_VERSIONS = {
    ENGINE_PYTHON: ENGINE_PYTHON_VERSION,
    ENGINE_CPP: ENGINE_TURBO_VERSION,
}

#: Controller mode names as shown to the owner.
ENGINE_MODE_LABELS = {
    ENGINE_MODE_AUTO: "Auto (Dynamic Autoscaler)",
    ENGINE_MODE_LOCK_CPP: "Lock to C++ Turbo",
    ENGINE_MODE_LOCK_PYTHON: "Lock to Python",
}


def normalize_engine(value) -> str:
    """Fold any stored/typed engine value onto a known engine id.

    Unknown or missing values fall back to Python Standard, so a corrupted
    document can never route a user onto an engine that does not exist.
    """
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"cpp", "c++", "c", "turbo", "cpp_turbo", "turbo_cpp"}:
        return ENGINE_CPP
    if text in {"python", "py", "standard", "python_standard"}:
        return ENGINE_PYTHON
    return ENGINE_PYTHON


def normalize_mode(value) -> str:
    """Fold any stored mode onto a known controller mode (default ``auto``)."""
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"auto", "autoscale", "autoscaler", "dynamic", "auto_mode"}:
        return ENGINE_MODE_AUTO
    if text in {"lock_cpp", "cpp", "turbo", "force_cpp", "lock_turbo", "cpp_lock"}:
        return ENGINE_MODE_LOCK_CPP
    if text in {"lock_python", "python", "py", "force_python", "lock_py", "python_lock"}:
        return ENGINE_MODE_LOCK_PYTHON
    return DEFAULT_ENGINE_MODE


#: Typed arguments accepted by ``/setengine`` (strict: unknown input is rejected
#: instead of silently falling back to a mode the owner did not ask for).
MODE_ARGUMENTS = {
    "auto": ENGINE_MODE_AUTO, "autoscale": ENGINE_MODE_AUTO,
    "autoscaler": ENGINE_MODE_AUTO, "dynamic": ENGINE_MODE_AUTO,
    "cpp": ENGINE_MODE_LOCK_CPP, "c++": ENGINE_MODE_LOCK_CPP,
    "turbo": ENGINE_MODE_LOCK_CPP, "lock_cpp": ENGINE_MODE_LOCK_CPP,
    "lock_turbo": ENGINE_MODE_LOCK_CPP,
    "python": ENGINE_MODE_LOCK_PYTHON, "py": ENGINE_MODE_LOCK_PYTHON,
    "lock_python": ENGINE_MODE_LOCK_PYTHON, "lock_py": ENGINE_MODE_LOCK_PYTHON,
}


def parse_mode_argument(value) -> str | None:
    """The mode a typed ``/setengine <value>`` argument asks for (``None`` if unknown)."""
    return MODE_ARGUMENTS.get(str(value or "").strip().lower().replace("-", "_"))


@dataclass(frozen=True)
class Engine:
    """One execution engine and the capabilities that distinguish it."""

    key: str
    label: str = ""
    icon: str = ""
    version: str | None = None
    #: Worker slots a bulk batch may occupy at the same time (1 = single stream).
    workers: int = 1
    #: True when the downloaded file is piped to the uploader without a copy.
    zero_copy: bool = False
    #: True when the engine is the multi-threaded high-performance one.
    turbo: bool = False

    def __post_init__(self):
        if self.key not in ENGINES:
            object.__setattr__(self, "key", normalize_engine(self.key))
        object.__setattr__(self, "label", self.label or ENGINE_LABELS.get(self.key, self.key))
        object.__setattr__(self, "icon", self.icon or ENGINE_ICONS.get(self.key, ""))
        if self.version is None:
            object.__setattr__(self, "version", ENGINE_VERSIONS.get(self.key))

    @property
    def name(self) -> str:
        """``"C++ Turbo 🚀"`` — label plus icon, the form used in copy."""
        return f"{self.label} {self.icon}".strip()

    @property
    def version_label(self) -> str:
        """``"v2.4"`` for the turbo engine, empty when the engine has none."""
        return f"v{self.version}" if self.version else ""

    @property
    def thread_model(self) -> str:
        return "multi-thread zero-copy" if self.turbo else "single-stream"


#: The two engines the bot can run, keyed by their id.
ENGINE_REGISTRY: dict[str, Engine] = {
    ENGINE_PYTHON: Engine(
        key=ENGINE_PYTHON, workers=1, zero_copy=False, turbo=False,
    ),
    ENGINE_CPP: Engine(
        key=ENGINE_CPP, workers=max(1, ENGINE_TURBO_WORKERS), zero_copy=True, turbo=True,
    ),
}


def get_engine(key) -> Engine:
    """The :class:`Engine` for *key* (unknown values fall back to Python)."""
    return ENGINE_REGISTRY[normalize_engine(key)]


def engine_label(key) -> str:
    return get_engine(key).label


def engine_name(key) -> str:
    return get_engine(key).name


# --------------------------------------------------------------------------- #
#  Routing rules
# --------------------------------------------------------------------------- #

#: Why a decision was made — surfaced in /stats, /models and the admin panel.
REASON_GLOBAL_LOCK = "global_lock"
REASON_PEAK_AUTOSCALE = "peak_autoscale"
REASON_USER_CHOICE = "user_choice"
REASON_DEFAULT = "default"
REASON_MODELS_LOCKED = "models_locked"

#: Badge text rendered next to the engine on the /start header.
BADGE_PEAK = "Peak Auto-Scale"
BADGE_GLOBAL_LOCK = "Global Lock"
BADGE_USER = "Your Choice"
BADGE_STANDARD = ""


@dataclass(frozen=True)
class EngineDecision:
    """The outcome of one routing decision (fully inspectable, easy to test)."""

    engine: str
    mode: str
    reason: str = REASON_DEFAULT
    #: True while the autoscaler considers the server to be under peak load.
    peak: bool = False
    #: Concurrent extractions the monitor saw when the decision was taken.
    concurrent: int = 0
    threshold: int = ENGINE_PEAK_THRESHOLD
    #: True when the user holds the ``models`` (C++ Turbo) permission.
    has_models: bool = False
    #: The user's stored preference, already normalised.
    preference: str | None = None

    @property
    def turbo(self) -> bool:
        return self.engine == ENGINE_CPP

    @property
    def badge(self) -> str:
        """Short bracket text for the /start header, e.g. ``Peak Auto-Scale``."""
        if self.reason == REASON_PEAK_AUTOSCALE:
            return BADGE_PEAK
        if self.reason == REASON_GLOBAL_LOCK:
            return BADGE_GLOBAL_LOCK
        if self.reason in {REASON_USER_CHOICE, REASON_MODELS_LOCKED}:
            return BADGE_USER
        return BADGE_STANDARD

    @property
    def engine_object(self) -> Engine:
        return get_engine(self.engine)


def is_peak(concurrent: int, threshold: int | None = None) -> bool:
    """True when *concurrent* extractions exceed the autoscaler threshold."""
    limit = ENGINE_PEAK_THRESHOLD if threshold is None else int(threshold)
    return int(concurrent) > limit


def resolve_engine(
    mode=None,
    *,
    concurrent: int = 0,
    threshold: int | None = None,
    has_models: bool = False,
    preference=None,
    peak: bool | None = None,
) -> EngineDecision:
    """Decide which engine runs one extraction — the whole routing matrix.

    ``mode``            the global controller mode (``auto`` / ``lock_cpp`` / ``lock_python``).
    ``concurrent``      live concurrent extractions (the autoscaler input).
    ``threshold``       override of ``config.ENGINE_PEAK_THRESHOLD``.
    ``has_models``      the user holds the ``models`` (C++ Turbo) permission.
    ``preference``      the engine the user picked in /models (may be ``None``).
    ``peak``            force the peak flag instead of deriving it (tests/admin).
    """
    resolved_mode = normalize_mode(mode)
    limit = ENGINE_PEAK_THRESHOLD if threshold is None else int(threshold)
    wanted = normalize_engine(preference) if preference else None
    models = bool(has_models)
    overloaded = is_peak(concurrent, limit) if peak is None else bool(peak)

    # 1) LOCK TO C++ — global force for 100% of extractions, autoscaler paused.
    if resolved_mode == ENGINE_MODE_LOCK_CPP:
        return EngineDecision(
            engine=ENGINE_CPP, mode=resolved_mode, reason=REASON_GLOBAL_LOCK,
            peak=overloaded, concurrent=int(concurrent), threshold=limit,
            has_models=models, preference=wanted,
        )

    # 2) LOCK TO PYTHON — free users are locked; models holders still toggle.
    if resolved_mode == ENGINE_MODE_LOCK_PYTHON:
        if models and wanted == ENGINE_CPP:
            return EngineDecision(
                engine=ENGINE_CPP, mode=resolved_mode, reason=REASON_MODELS_LOCKED,
                peak=False, concurrent=int(concurrent), threshold=limit,
                has_models=models, preference=wanted,
            )
        return EngineDecision(
            engine=ENGINE_PYTHON, mode=resolved_mode, reason=REASON_GLOBAL_LOCK,
            peak=False, concurrent=int(concurrent), threshold=limit,
            has_models=models, preference=wanted,
        )

    # 3) AUTO — the dynamic autoscaler.
    if models and wanted == ENGINE_CPP:
        # A models holder who asked for C++ Turbo keeps it at any traffic level.
        return EngineDecision(
            engine=ENGINE_CPP, mode=resolved_mode, reason=REASON_USER_CHOICE,
            peak=overloaded, concurrent=int(concurrent), threshold=limit,
            has_models=models, preference=wanted,
        )
    if overloaded:
        # Traffic spike: everything moves to C++ Turbo to eliminate the queue.
        return EngineDecision(
            engine=ENGINE_CPP, mode=resolved_mode, reason=REASON_PEAK_AUTOSCALE,
            peak=True, concurrent=int(concurrent), threshold=limit,
            has_models=models, preference=wanted,
        )
    # Normal traffic: free/sample users (and models holders on Python) stay put.
    return EngineDecision(
        engine=ENGINE_PYTHON, mode=resolved_mode, reason=REASON_DEFAULT,
        peak=False, concurrent=int(concurrent), threshold=limit,
        has_models=models, preference=wanted,
    )


def autoscaler_active(mode=None) -> bool:
    """True only in AUTO mode — both lock modes pause the autoscaler."""
    return normalize_mode(mode) == ENGINE_MODE_AUTO


def can_switch_engine(mode=None, *, has_models: bool = False) -> bool:
    """May this user change their own engine right now?

    The switcher needs the ``models`` permission.  It stays usable in every
    mode (including a Python global lock, where the permission is what lets a
    premium user opt back into C++ Turbo), but a C++ global lock already forces
    the turbo engine on everybody, so the choice is reported as fixed.
    """
    if not has_models:
        return False
    return normalize_mode(mode) != ENGINE_MODE_LOCK_CPP


# --------------------------------------------------------------------------- #
#  Live traffic monitor + engine analytics
# --------------------------------------------------------------------------- #

@dataclass
class TrafficMonitor:
    """Real-time concurrent-extraction traffic — the autoscaler's only input.

    The counters are plain integers: the bot runs on one asyncio loop, so no
    locking is needed and reading them can never block an extraction.
    """

    peak_threshold: int = ENGINE_PEAK_THRESHOLD
    started_at: float = field(default_factory=time.monotonic)
    _active: int = 0
    _peak_active: int = 0
    _in_peak: bool = False
    peak_events: int = 0
    #: engine id -> number of extractions routed to it since process start.
    routed: dict = field(default_factory=lambda: {key: 0 for key in ENGINES})
    #: reason -> number of decisions taken for that reason.
    reasons: dict = field(default_factory=dict)
    decisions: int = 0

    # -- concurrency -------------------------------------------------------- #
    @property
    def active(self) -> int:
        """Extractions in flight right now."""
        return self._active

    @property
    def peak_active(self) -> int:
        """Highest concurrency seen since the process started."""
        return self._peak_active

    def enter(self) -> int:
        """Register one more concurrent extraction; returns the new count."""
        self._active += 1
        if self._active > self._peak_active:
            self._peak_active = self._active
        peak_now = self.peak
        if peak_now and not self._in_peak:
            self.peak_events += 1
        self._in_peak = peak_now
        return self._active

    def leave(self) -> int:
        """Release one extraction slot; returns the new count."""
        self._active = max(0, self._active - 1)
        self._in_peak = self.peak
        return self._active

    @property
    def peak(self) -> bool:
        """True while concurrency is above the threshold."""
        return is_peak(self._active, self.peak_threshold)

    @contextmanager
    def slot(self):
        """``with monitor.slot():`` — keeps the concurrency counter honest."""
        self.enter()
        try:
            yield self
        finally:
            self.leave()

    # -- analytics ---------------------------------------------------------- #
    def record(self, decision: EngineDecision) -> None:
        """Count one routed extraction (called by the controller)."""
        self.decisions += 1
        key = normalize_engine(decision.engine)
        self.routed[key] = self.routed.get(key, 0) + 1
        self.reasons[decision.reason] = self.reasons.get(decision.reason, 0) + 1

    def uptime_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def snapshot(self) -> dict:
        """Everything /stats prints about live engine traffic."""
        return {
            "active": self._active,
            "peak_active": self._peak_active,
            "peak": self.peak,
            "peak_events": self.peak_events,
            "threshold": self.peak_threshold,
            "routed": dict(self.routed),
            "reasons": dict(self.reasons),
            "decisions": self.decisions,
            "uptime": self.uptime_seconds(),
        }

    def reset(self) -> None:
        self._active = 0
        self._peak_active = 0
        self._in_peak = False
        self.peak_events = 0
        self.routed = {key: 0 for key in ENGINES}
        self.reasons = {}
        self.decisions = 0
        self.started_at = time.monotonic()


class EngineController:
    """Global engine controller — modes, autoscaler and per-request routing.

    The controller owns exactly one :class:`TrafficMonitor`, so the autoscaler
    always sees the real, process-wide concurrency.  The persisted mode is
    loaded through an injectable async provider, which keeps this class free of
    database imports (and therefore trivially testable).
    """

    def __init__(self, mode=None, monitor: TrafficMonitor | None = None,
                 peak_threshold: int | None = None, mode_provider=None):
        self._mode = normalize_mode(mode)
        self.monitor = monitor or TrafficMonitor(
            peak_threshold=ENGINE_PEAK_THRESHOLD if peak_threshold is None else peak_threshold)
        if peak_threshold is not None:
            self.monitor.peak_threshold = int(peak_threshold)
        #: async callable returning the stored mode (wired to database in main).
        self.mode_provider = mode_provider

    # -- mode --------------------------------------------------------------- #
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_label(self) -> str:
        return ENGINE_MODE_LABELS.get(self._mode, self._mode)

    def set_mode(self, mode) -> str:
        """Apply a controller mode in memory (persistence is the caller's job)."""
        self._mode = normalize_mode(mode)
        return self._mode

    async def load_mode(self) -> str:
        """Read the persisted mode; falls back to the current one on error."""
        if self.mode_provider is None:
            return self._mode
        try:
            stored = await self.mode_provider()
        except Exception:
            return self._mode
        self._mode = normalize_mode(stored)
        return self._mode

    def autoscaler_active(self) -> bool:
        return autoscaler_active(self._mode)

    # -- routing ------------------------------------------------------------ #
    @property
    def peak(self) -> bool:
        return self.monitor.peak

    @property
    def concurrent(self) -> int:
        return self.monitor.active

    def decide(self, *, has_models: bool = False, preference=None,
               concurrent: int | None = None, threshold: int | None = None,
               record: bool = True) -> EngineDecision:
        """Route one extraction for a user with *has_models* / *preference*."""
        decision = resolve_engine(
            self._mode,
            concurrent=self.monitor.active if concurrent is None else concurrent,
            threshold=self.monitor.peak_threshold if threshold is None else threshold,
            has_models=has_models,
            preference=preference,
        )
        if record:
            self.monitor.record(decision)
        return decision

    async def decide_for(self, *, has_models: bool = False, preference=None,
                         record: bool = True) -> EngineDecision:
        """:meth:`decide` after refreshing the persisted mode."""
        await self.load_mode()
        return self.decide(has_models=has_models, preference=preference, record=record)

    def can_switch(self, *, has_models: bool = False) -> bool:
        return can_switch_engine(self._mode, has_models=has_models)

    @contextmanager
    def slot(self, decision: EngineDecision | None = None):
        """Hold one concurrency slot for the duration of an extraction."""
        with self.monitor.slot():
            yield decision

    def snapshot(self) -> dict:
        """Controller + monitor state for /stats and the admin panel."""
        data = self.monitor.snapshot()
        data.update({
            "mode": self._mode,
            "mode_label": self.mode_label,
            "autoscaler": self.autoscaler_active(),
        })
        return data


#: The single process-wide controller used by main.py.
CONTROLLER = EngineController()


def controller() -> EngineController:
    return CONTROLLER
