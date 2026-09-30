"""Live server telemetry for the download HUD.

Three numbers are sampled from the host the bot actually runs on:

* **CPU %** — delta of ``/proc/stat`` between two samples (falls back to the
  normalised load average on hosts without ``/proc``).
* **RAM %** — ``MemTotal``/``MemAvailable`` from ``/proc/meminfo``.
* **Ping ms** — the TCP handshake time to ``config.TELEMETRY_PING_HOST``, the
  endpoint every MTProto call has to reach anyway.  It is *not* an API call and
  never sends credentials.

plus the transfer maths for the file being downloaded right now (percent,
smoothed MB/s and ETA).

Everything here returns **numbers only** — the strings a user sees (the HUD,
the progress bar, the engine badge) are built in :mod:`ui`, because all
bot-facing copy has to go through the ``ui.py`` helpers and ``ui_text()``.

Both the probes and the clock are injectable, so the tests sample a completely
deterministic fake host without touching the network or ``/proc``.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field

from config import (
    TELEMETRY_PING_HOST, TELEMETRY_PING_PORT, TELEMETRY_PING_TTL,
    TELEMETRY_SAMPLE_TTL, TELEMETRY_SPEED_WINDOW,
)

#: Bytes in the units the HUD prints.
KB = 1024.0
MB = 1024.0 * 1024.0
GB = 1024.0 * 1024.0 * 1024.0

#: "Nothing has been measured yet" — used for the cache timestamps so the first
#: reading is always taken regardless of where ``time.monotonic()`` starts.
NEVER = float("-inf")


# --------------------------------------------------------------------------- #
#  Host probes (pure stdlib — no psutil dependency)
# --------------------------------------------------------------------------- #

def read_cpu_times(path: str = "/proc/stat") -> tuple[float, float] | None:
    """``(idle, total)`` jiffies of the aggregate ``cpu`` line, or ``None``."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    parts = line.split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        values = [float(value) for value in parts[1:]]
    except ValueError:
        return None
    if len(values) < 4:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0.0)  # idle + iowait
    return idle, sum(values)


def cpu_percent_from_times(previous, current) -> float | None:
    """CPU usage between two :func:`read_cpu_times` snapshots."""
    if not previous or not current:
        return None
    idle = current[0] - previous[0]
    total = current[1] - previous[1]
    if total <= 0:
        return None
    return max(0.0, min(100.0, (1.0 - idle / total) * 100.0))


def load_average_cpu_percent() -> float | None:
    """Fallback CPU estimate: 1-minute load average normalised by core count."""
    try:
        load = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    cores = os.cpu_count() or 1
    return max(0.0, min(100.0, load / cores * 100.0))


def read_memory_percent(path: str = "/proc/meminfo") -> float | None:
    """Used RAM in percent from ``/proc/meminfo``, or ``None`` when unknown."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            rows = handle.read()
    except OSError:
        return None
    info: dict[str, float] = {}
    for line in rows.splitlines():
        key, _, rest = line.partition(":")
        value = rest.strip().split(" ")
        if not value:
            continue
        try:
            info[key.strip()] = float(value[0])
        except ValueError:
            continue
    total = info.get("MemTotal")
    if not total:
        return None
    available = info.get("MemAvailable")
    if available is None:
        # Older kernels: free + buffers + cache is the usable memory.
        available = info.get("MemFree", 0.0) + info.get("Buffers", 0.0) + info.get("Cached", 0.0)
    return max(0.0, min(100.0, (total - available) / total * 100.0))


async def measure_ping_ms(host: str = TELEMETRY_PING_HOST, port: int = TELEMETRY_PING_PORT,
                          timeout: float = 2.0) -> float | None:
    """TCP handshake time to *host*:*port* in milliseconds (``None`` on failure).

    A plain connect/close: no TLS, no API call, no credentials — just the
    round-trip latency the MTProto streams are subject to.
    """
    started = time.monotonic()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout)
    except (OSError, asyncio.TimeoutError, ValueError):
        return None
    elapsed = (time.monotonic() - started) * 1000.0
    try:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    except Exception:  # pragma: no cover - closing is best effort
        pass
    return max(0.0, elapsed)


# --------------------------------------------------------------------------- #
#  Sampled host state
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ServerSample:
    """One telemetry reading. ``None`` fields are rendered as unknown."""

    cpu_percent: float | None = None
    memory_percent: float | None = None
    ping_ms: float | None = None
    taken_at: float = field(default_factory=time.monotonic)

    @property
    def known(self) -> bool:
        return any(value is not None for value in
                   (self.cpu_percent, self.memory_percent, self.ping_ms))


#: Reading used when the host exposes nothing measurable at all.
EMPTY_SAMPLE = ServerSample()


class HostMonitor:
    """Cached, non-blocking host sampler used while a download is in flight.

    The HUD is edited several times per download, so raw readings are reused
    for ``TELEMETRY_SAMPLE_TTL`` seconds and pings for ``TELEMETRY_PING_TTL``
    seconds — the numbers stay live without hammering ``/proc`` or the network.
    Every probe is replaceable, which is how the tests drive it deterministically.
    """

    def __init__(self, *, cpu_probe=None, memory_probe=None, ping_probe=None,
                 clock=time.monotonic, sample_ttl: float = TELEMETRY_SAMPLE_TTL,
                 ping_ttl: float = TELEMETRY_PING_TTL,
                 ping_host: str = TELEMETRY_PING_HOST, ping_port: int = TELEMETRY_PING_PORT):
        self.cpu_probe = cpu_probe or read_cpu_times
        self.memory_probe = memory_probe or read_memory_percent
        self.ping_probe = ping_probe or measure_ping_ms
        self.clock = clock
        self.sample_ttl = sample_ttl
        self.ping_ttl = ping_ttl
        self.ping_host = ping_host
        self.ping_port = ping_port
        self._cpu_previous = None
        self._cpu_value: float | None = None
        self._memory_value: float | None = None
        self._ping_value: float | None = None
        #: ``-inf`` (not 0.0) so the very first reading is always taken, even
        #: on a host where ``time.monotonic()`` starts close to zero.
        self._sampled_at = NEVER
        self._pinged_at = NEVER
        self.samples_taken = 0
        self.pings_taken = 0
        self.last: ServerSample = EMPTY_SAMPLE
        # Prime the CPU baseline: a percentage needs two /proc/stat reads, and
        # without this the very first HUD of the process would show no CPU.
        try:
            self._read_cpu()
        except Exception:  # pragma: no cover - a probe must never break a download
            pass

    # -- individual readings ------------------------------------------------ #
    def _read_cpu(self) -> float | None:
        """CPU percent, or the last known value when the probe cannot answer.

        A probe that raises (a sandboxed ``/proc``, a seccomp filter, a mocked
        reader) must degrade to ``--`` in the HUD — telemetry never breaks a
        download.
        """
        try:
            current = self.cpu_probe()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[TELEMETRY] cpu probe failed: {exc}", flush=True)
            return self._cpu_value
        if current is None:
            # No /proc on this host — fall back to the load average once.
            if self._cpu_value is None:
                self._cpu_value = load_average_cpu_percent()
            return self._cpu_value
        value = cpu_percent_from_times(self._cpu_previous, current)
        self._cpu_previous = current
        if value is not None:
            self._cpu_value = value
        return self._cpu_value

    def _read_memory(self) -> float | None:
        try:
            value = self.memory_probe()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[TELEMETRY] memory probe failed: {exc}", flush=True)
            return self._memory_value
        if value is not None:
            self._memory_value = value
        return self._memory_value

    async def _read_ping(self) -> float | None:
        try:
            value = await self.ping_probe(self.ping_host, self.ping_port)
        except TypeError:
            # A simple (host-less) fake probe is accepted too.
            value = await self.ping_probe()
        except Exception:
            value = None
        if value is not None:
            self._ping_value = float(value)
            self.pings_taken += 1
        return self._ping_value

    # -- public API --------------------------------------------------------- #
    async def sample(self, *, force: bool = False) -> ServerSample:
        """A fresh (or cached) :class:`ServerSample`."""
        now = self.clock()
        if not force and self.last.known and (now - self._sampled_at) < self.sample_ttl:
            return self.last
        cpu = self._read_cpu()
        memory = self._read_memory()
        if force or (now - self._pinged_at) >= self.ping_ttl:
            await self._read_ping()
            self._pinged_at = now
        self._sampled_at = now
        self.samples_taken += 1
        self.last = ServerSample(cpu_percent=cpu, memory_percent=memory,
                                 ping_ms=self._ping_value, taken_at=now)
        return self.last

    def sample_sync(self) -> ServerSample:
        """CPU/RAM only, for the code paths that must not await (log lines)."""
        self.last = ServerSample(cpu_percent=self._read_cpu(),
                                 memory_percent=self._read_memory(),
                                 ping_ms=self._ping_value,
                                 taken_at=self.clock())
        self.samples_taken += 1
        return self.last

    def reset(self) -> None:
        self._cpu_previous = None
        self._cpu_value = None
        self._memory_value = None
        self._ping_value = None
        self._sampled_at = NEVER
        self._pinged_at = NEVER
        self.last = EMPTY_SAMPLE


#: Process-wide monitor (main.py reads it, tests replace the probes).
MONITOR = HostMonitor()


def monitor() -> HostMonitor:
    return MONITOR


# --------------------------------------------------------------------------- #
#  Transfer maths (percent / speed / ETA)
# --------------------------------------------------------------------------- #

@dataclass
class TransferState:
    """The numbers behind one line of the HUD."""

    percent: int = 0
    current: int = 0
    total: int = 0
    #: Smoothed transfer speed in bytes per second (``None`` until measurable).
    speed: float | None = None
    #: Remaining seconds at the current speed (``None`` when not estimable).
    eta: float | None = None
    paused: bool = False

    @property
    def speed_mbps(self) -> float | None:
        return None if self.speed is None else self.speed / MB

    @property
    def complete(self) -> bool:
        return self.percent >= 100


class TransferMeter:
    """Tracks one download: percent, windowed speed and remaining time.

    ``update()`` is called from the pyrogram progress callback, so it must stay
    cheap: a bounded deque of ``(timestamp, bytes)`` samples over
    ``TELEMETRY_SPEED_WINDOW`` seconds is all it keeps.
    """

    def __init__(self, total: int = 0, *, window: float = TELEMETRY_SPEED_WINDOW,
                 clock=time.monotonic):
        self.window = max(0.1, float(window))
        self.clock = clock
        self.total = max(0, int(total or 0))
        self.current = 0
        self.paused = False
        self._samples: deque = deque()
        self.started_at = clock()
        self.finished_at: float | None = None
        self.state = TransferState(total=self.total)

    # -- input -------------------------------------------------------------- #
    def set_total(self, total: int) -> None:
        self.total = max(0, int(total or 0))

    def update(self, current: int, total: int | None = None) -> TransferState:
        """Record progress and return the derived :class:`TransferState`."""
        if total is not None:
            self.set_total(total)
        now = self.clock()
        self.current = max(0, int(current or 0))
        if self.current > self.total and self.current:
            self.total = self.current
        self._samples.append((now, self.current))
        cutoff = now - self.window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
        if len(self._samples) == 1:
            # First tick of a transfer: fall back to the whole-run average.
            self._samples.appendleft((self.started_at, 0))
        self.state = self._compute(now)
        if self.state.percent >= 100 and self.finished_at is None:
            self.finished_at = now
        return self.state

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        # Drop the gap so a paused transfer does not report a bogus speed.
        self._samples.clear()
        self.started_at = self.clock()

    def finish(self) -> TransferState:
        self.finished_at = self.clock()
        if self.total:
            self.current = self.total
        self.state = self._compute(self.finished_at)
        return self.state

    # -- maths -------------------------------------------------------------- #
    def _speed(self, now: float) -> float | None:
        if len(self._samples) < 2:
            return None
        first_time, first_bytes = self._samples[0]
        last_time, last_bytes = self._samples[-1]
        elapsed = last_time - first_time
        if elapsed <= 0:
            # A non-monotonic clock (or a sample from before the transfer
            # started) can never produce a meaningful speed: report "unknown"
            # instead of dividing by a fake epsilon and printing GB/s nonsense.
            return None
        moved = last_bytes - first_bytes
        if moved <= 0:
            return 0.0
        return moved / elapsed

    def _compute(self, now: float) -> TransferState:
        percent = 0
        if self.total > 0:
            percent = int(min(100, max(0, round(self.current * 100 / self.total))))
        elif self.current:
            percent = 100
        speed = self._speed(now)
        eta = None
        if speed and speed > 0 and self.total > 0:
            # A finished transfer has zero seconds left, not "unknown".
            eta = max(0.0, (self.total - self.current) / speed)
        return TransferState(
            percent=percent, current=self.current, total=self.total,
            speed=speed, eta=eta, paused=self.paused,
        )

    @property
    def percent(self) -> int:
        return self.state.percent

    @property
    def speed_mbps(self) -> float | None:
        return self.state.speed_mbps

    @property
    def eta_seconds(self) -> float | None:
        return self.state.eta
