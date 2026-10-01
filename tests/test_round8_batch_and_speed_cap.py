"""Round 8 — items 1, 2 and 10.

Item 1  Batch parallelism: one shared ``engines.run_engine_batch`` runner used
        by all three batch paths (private multi-link, private range, channel
        dump).  🚀 C++ Turbo gets a bounded worker pool with starts spaced by
        the anti-ban gap; ⚙️ Python Standard stays strictly sequential in the
        order sent; a single item never spawns a pool; ``"cancelled"`` stops the
        batch; the ``Done! N success / M failed`` tally stays exact under
        concurrency; a FloodWait on one item never kills the batch.

Item 2  ⚙️ Python Standard is paced to ``config.ENGINE_PYTHON_SPEED_LIMIT_MBPS``
        (default ~3 MB/s) by a real token bucket inside the download-progress
        path; 🚀 C++ Turbo is uncapped.  Proven with a fake clock, so no test
        ever really waits.  The HUD reports the *throttled* speed, and
        pause/resume plus cancellation keep working.

Item 10 The engine pages only claim what the code actually does: a parallel
        worker pool, zero-copy in-memory piping, an uncapped rate against
        Python Standard's cap, priority routing above the peak threshold — and
        a plain statement of where Turbo changes nothing.  The false
        "native C cipher (TgCrypto)" claim is gone (TgCrypto is bot-wide).

Everything here runs on the in-memory fakes: no Telegram, no MongoDB, no
``/proc``, no sockets.
"""

from __future__ import annotations

import asyncio
import io
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import engines
import main
import telemetry
import ui
from conftest import FakeChat, FakeMessage, FakeUser, sc

CPP = config.ENGINE_CPP
PYTHON = config.ENGINE_PYTHON
MB = 1024 * 1024


def media_message(msg_id=5, size=10 * MB, chat_id=-100888):
    """A downloadable message the FakeBot can serve from ``.messages``."""
    return SimpleNamespace(
        id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
        text=None, caption="Original caption",
        video=SimpleNamespace(file_id="v1", file_size=size),
        document=None, audio=None, photo=None, voice=None, video_note=None,
        sticker=None, animation=None, media=True,
    )


def turbo_decision():
    return engines.resolve_engine("lock_cpp")


def python_decision():
    return engines.resolve_engine("lock_python")


class Overlap:
    """Counts how many runner calls are inside their slow section at once."""

    def __init__(self, delay=0.02, results=None):
        self.now = 0
        self.max = 0
        self.delay = delay
        self.results = results
        self.order: list = []

    async def __call__(self, index, item):
        self.order.append(item)
        self.now += 1
        self.max = max(self.max, self.now)
        await asyncio.sleep(self.delay)
        self.now -= 1
        if self.results is None:
            return True
        return self.results(index, item)


# --------------------------------------------------------------------------- #
#  1a. The shared runner — engines.run_engine_batch
# --------------------------------------------------------------------------- #

def test_single_item_never_spawns_the_pool():
    assert engines.batch_workers(turbo_decision(), 1) == 1
    assert engines.batch_workers(turbo_decision(), 0) == 1
    assert engines.batch_workers(python_decision(), 1) == 1


def test_pool_size_follows_the_engine():
    assert engines.batch_workers(turbo_decision(), 8) == config.ENGINE_TURBO_WORKERS
    assert engines.batch_workers(python_decision(), 8) == 1
    assert config.ENGINE_TURBO_WORKERS > 1


async def test_turbo_overlaps_up_to_the_worker_budget():
    overlap = Overlap()
    items = list(range(1, config.ENGINE_TURBO_WORKERS + 4))
    result = await engines.run_engine_batch(items, overlap, turbo_decision(),
                                            sleeper=AsyncMock(), start_gap=0)
    assert overlap.max == config.ENGINE_TURBO_WORKERS
    assert (result.success, result.failed) == (len(items), 0)
    assert result.ran == len(items) and result.skipped == 0


async def test_python_stays_strictly_sequential_and_in_order():
    overlap = Overlap()
    items = list(range(1, 6))
    result = await engines.run_engine_batch(items, overlap, python_decision(),
                                            sleeper=AsyncMock(), start_gap=0)
    assert overlap.max == 1, "the Python engine never overlaps two items"
    assert overlap.order == items, "and it keeps the order the user sent"
    assert result.as_tuple() == (5, 0)


async def test_starts_are_spaced_by_the_anti_ban_gap():
    sleeper = AsyncMock()
    await engines.run_engine_batch([1, 2, 3], Overlap(delay=0), turbo_decision(),
                                   sleeper=sleeper, start_gap=1.5)
    gaps = [call.args[0] for call in sleeper.await_args_list]
    assert gaps.count(1.5) >= 2, f"two of the three starts must wait the gap: {gaps}"


def test_start_gap_defaults_to_the_config_knob():
    assert config.ENGINE_START_GAP_SECONDS == float(
        __import__("os").environ.get("ENGINE_START_GAP_SECONDS", "3.0"))
    assert config.ENGINE_START_GAP_SECONDS > 0


async def test_cancelled_stops_a_sequential_batch_immediately():
    started = []

    async def runner(index, item):
        started.append(index)
        return engines.CANCELLED if index == 2 else True

    result = await engines.run_engine_batch(list(range(1, 7)), runner,
                                            python_decision(), sleeper=AsyncMock(),
                                            start_gap=0)
    assert result.stopped is True
    assert result.success == 1, "the item before the cancel still counts"
    assert result.failed == 0, "a cancel is not a failure"
    assert started == [1, 2], "nothing runs after the batch was stopped"
    #: A cancel lands in ``results`` but counts as neither success nor failed.
    assert len(result.results) == 2 and result.ran == 1


async def test_cancelled_skips_items_that_never_started_in_the_pool():
    #: The first worker cancels without ever suspending, so the pool has already
    #: stopped by the time the remaining workers reach the start gate.
    async def runner(index, item):
        return engines.CANCELLED if index == 1 else True

    result = await engines.run_engine_batch([1, 2, 3], runner, turbo_decision(),
                                            sleeper=AsyncMock(), start_gap=0,
                                            workers=3)
    assert result.stopped is True
    assert result.failed == 0, "a cancel is never counted as a failure"
    assert result.success == 0
    assert result.skipped == 2, "workers that never started are reported skipped"
    #: Every item is accounted for exactly once: ran, cancelled or skipped.
    assert len(result.results) + result.skipped == 3


async def test_tally_is_exact_under_concurrency():
    """Half the items fail while several workers run at once."""
    result = await engines.run_engine_batch(
        list(range(1, 13)),
        lambda index, item: _async_value(index % 2 == 0),
        turbo_decision(), sleeper=AsyncMock(), start_gap=0)
    assert (result.success, result.failed) == (6, 6)
    assert result.ran == 12
    assert len(result.results) == 12


async def _async_value(value):
    await asyncio.sleep(0.005)
    return value


async def test_empty_batch_is_a_no_op():
    result = await engines.run_engine_batch([], Overlap(), turbo_decision())
    assert result.as_tuple() == (0, 0) and result.results == []


# --------------------------------------------------------------------------- #
#  1b. All three batch paths use the same runner
# --------------------------------------------------------------------------- #

async def _private_batch_overlap(db, monkeypatch, message, *, turbo):
    """Run one private-chat batch and measure the real overlap."""
    await db.add_user(1001, "Tester")
    if turbo:
        await db.add_premium(1001, 30, tier="all")
        await db.set_user_engine(1001, CPP)
    overlap = Overlap()

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        return await overlap(0, mid)

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    await main.text_handler(None, message)
    return overlap


async def test_private_multi_link_path_pools_on_turbo(db, monkeypatch):
    text = "\n".join(f"https://t.me/source/{i}" for i in range(1, 9))
    overlap = await _private_batch_overlap(
        db, monkeypatch, FakeMessage(text=text, user=FakeUser(1001)), turbo=True)
    assert overlap.max == config.ENGINE_TURBO_WORKERS


async def test_private_multi_link_path_is_sequential_on_python(db, monkeypatch):
    #: ``turbo=False`` still buys premium: without it the free daily quota
    #: (3/day) stops a 4-link batch before the engine is ever consulted.
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="public")
    overlap = Overlap()

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        return await overlap(0, mid)

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    text = "\n".join(f"https://t.me/source/{i}" for i in range(1, 5))
    await main.text_handler(None, FakeMessage(text=text, user=FakeUser(1001)))
    assert overlap.max == 1
    assert overlap.order == [1, 2, 3, 4]


def _seed_range(fake_bot, ids, *, media=True):
    """Put messages into the fake store so the pre-flight finds them."""
    for msg_id in ids:
        fake_bot.messages[msg_id] = SimpleNamespace(
            id=msg_id, empty=False, text=None,
            caption="caption" if media else None,
            media=media, photo=None, video=media, document=None, audio=None,
            voice=None, video_note=None, sticker=None, animation=None,
            chat=SimpleNamespace(id=fake_bot.channel_id),
        )


async def test_private_range_path_pools_on_turbo(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    await db.set_user_engine(1001, CPP)
    _seed_range(fake_bot, range(1, 9))
    overlap = Overlap()

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        return await overlap(0, mid)

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    await main.text_handler(None, FakeMessage(text="https://t.me/source/1-8",
                                              user=FakeUser(1001)))
    assert overlap.max == config.ENGINE_TURBO_WORKERS


async def test_private_range_path_is_sequential_on_python(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")   # premium: no daily-quota stop
    _seed_range(fake_bot, range(1, 6))
    overlap = Overlap()

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        return await overlap(0, mid)

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    await main.text_handler(None, FakeMessage(text="https://t.me/source/1-5",
                                              user=FakeUser(1001)))
    assert overlap.max == 1
    assert overlap.order == [1, 2, 3, 4, 5], "a range is extracted in order"


async def test_channel_dump_path_shares_the_same_runner(db, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    await db.set_user_engine(1001, CPP)
    await db.set_user_chat(1001, -100777, "Dump")
    post = FakeMessage(text="\n".join(f"https://t.me/source/{i}" for i in range(1, 9)),
                       user=FakeUser(1001))
    post.chat = FakeChat(-100777, "channel", "Dump")
    overlap = Overlap()

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        return await overlap(0, mid)

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))
    success, failed = await main.extract_channel_links(
        post, db.users[1001], sleeper=AsyncMock())
    assert (success, failed) == (8, 0)
    assert overlap.max == config.ENGINE_TURBO_WORKERS


# --------------------------------------------------------------------------- #
#  1c. run_private_batch — status messages, tally and FloodWait isolation
# --------------------------------------------------------------------------- #

async def test_batch_reports_one_status_per_item_and_an_exact_tally(db, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    await db.set_user_engine(1001, CPP)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        await asyncio.sleep(0.01)
        return mid != 3          # one item fails

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    message = FakeMessage(text="\n".join(f"https://t.me/source/{i}" for i in range(1, 6)),
                          user=FakeUser(1001))
    await main.text_handler(None, message)

    #: Every item opened its own per-item status message, so nothing interleaves.
    per_item = [row["text"] for row in message.replies]
    for index in range(1, 6):
        assert per_item.count(ui.batch_item_text(index)) == 1

    #: The shared progress message counts finished items and never goes back.
    done_values = [int(match.group(1))
                   for match in (re.match(rf"^{re.escape(sc('⏳'))} (\d+)/", edit["text"])
                                 for edit in message.edits) if match]
    assert done_values == sorted(done_values), done_values
    assert done_values[-1] == 5

    #: The final tally is exact: 4 succeeded, 1 failed.
    assert sc(ui.batch_done_text(4, 1)) in message.shown_text


async def test_floodwait_on_one_item_does_not_kill_the_batch(db, monkeypatch):
    from pyrogram.errors import FloodWait
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    sleeper = AsyncMock()
    seen = []

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        seen.append(mid)
        if mid == 2:
            raise FloodWait(7)
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    items = [(index, f"https://t.me/source/{index}") for index in range(1, 5)]
    message = FakeMessage(user=FakeUser(1001))
    batch = await main.run_private_batch(message, items, sleeper=sleeper)

    assert seen == [1, 2, 3, 4], "the batch continued past the throttled item"
    assert batch.as_tuple() == (3, 1)
    #: main.floodwait_seconds() sleeps value + 1 as headroom.
    assert main.floodwait_seconds(FloodWait(7)) in \
        [call.args[0] for call in sleeper.await_args_list]
    assert any(sc("Telegram rate limit") in edit["text"] for edit in message.edits)


async def test_an_item_that_raises_is_counted_as_failed(db, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)

    async def fake_fetch(msg, status, client, target, mid, **kwargs):
        if mid == 1:
            raise RuntimeError("upload exploded")
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    items = [(index, f"https://t.me/source/{index}") for index in range(1, 4)]
    batch = await main.run_private_batch(FakeMessage(user=FakeUser(1001)), items)
    assert batch.as_tuple() == (2, 1)


async def test_run_private_batch_resolves_one_engine_for_the_whole_batch(db, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    await db.set_user_engine(1001, CPP)
    decisions = []
    real = main.resolve_engine_for

    async def spy(user_id, **kwargs):
        decision = await real(user_id, **kwargs)
        decisions.append(decision.engine)
        return decision

    monkeypatch.setattr(main, "resolve_engine_for", spy)
    monkeypatch.setattr(main, "fetch_and_send", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    items = [(index, f"https://t.me/source/{index}") for index in range(1, 5)]
    await main.run_private_batch(FakeMessage(user=FakeUser(1001)), items)
    assert decisions == [CPP], "one batch, one engine decision"


# --------------------------------------------------------------------------- #
#  2a. The token bucket itself
# --------------------------------------------------------------------------- #

class FakeClock:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self, start=1000.0):
        self.start = start
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        #: Yield once so a test can interleave with the transfer (pause it,
        #: cancel it) while the *measured* time stays exactly the fake clock's.
        await asyncio.sleep(0)

    @property
    def elapsed(self):
        return self.now - self.start

    @property
    def waited(self):
        return sum(self.sleeps)


@pytest.mark.parametrize("value", [0, 0.0, None])
def test_a_zero_or_missing_cap_disables_the_throttle(value):
    throttle = telemetry.SpeedThrottle(value)
    assert throttle.enabled is False
    assert throttle.delay_for(50 * MB) == 0.0


def test_throttle_rate_matches_the_configured_mbps():
    throttle = telemetry.SpeedThrottle(config.ENGINE_PYTHON_SPEED_LIMIT_MBPS,
                                       burst_seconds=0)
    assert throttle.enabled is True
    assert throttle.rate == pytest.approx(config.ENGINE_PYTHON_SPEED_LIMIT_MBPS * MB)
    assert throttle.capacity == 0.0, "no burst credit by default"


def test_delay_for_is_pure_maths_at_exactly_the_cap():
    clock = FakeClock()
    throttle = telemetry.SpeedThrottle(3.0, burst_seconds=0, clock=clock)
    #: 3 MB at 3 MB/s is exactly one second, and nothing was slept yet.
    assert throttle.delay_for(3 * MB) == pytest.approx(1.0)
    #: The bucket is empty now, so the next 1.5 MB needs half a second.
    assert throttle.delay_for(int(1.5 * MB), now=clock.now + 1.0) == pytest.approx(0.5)


def test_a_full_bucket_costs_nothing():
    clock = FakeClock()
    throttle = telemetry.SpeedThrottle(3.0, burst_seconds=2.0, clock=clock)
    assert throttle.capacity == pytest.approx(6 * MB)
    assert throttle.delay_for(5 * MB, now=clock.now + 10) == 0.0


async def test_pace_to_charges_only_the_delta():
    clock = FakeClock()
    throttle = telemetry.SpeedThrottle(3.0, burst_seconds=0, clock=clock,
                                       sleeper=clock.sleep)
    await throttle.pace_to(3 * MB)
    assert clock.waited == pytest.approx(1.0)
    await throttle.pace_to(3 * MB)      # repeated position: nothing to charge
    await throttle.pace_to(6 * MB)
    assert clock.waited == pytest.approx(2.0)
    await throttle.pace_to(5 * MB)      # backwards position: nothing to charge
    assert clock.waited == pytest.approx(2.0)
    #: The high-water mark is kept, so a restart never under-charges the user.
    assert throttle.bytes_seen == 6 * MB


def test_resume_drops_the_accrued_credit():
    clock = FakeClock()
    throttle = telemetry.SpeedThrottle(3.0, burst_seconds=2.0, clock=clock)
    throttle.tokens = throttle.capacity
    throttle.resume()
    assert throttle.tokens == pytest.approx(throttle.capacity)
    throttle.tokens = 0.0
    clock.now += 60          # a long pause must not bank a minute of credit
    throttle.resume()
    assert throttle.tokens <= throttle.capacity


# --------------------------------------------------------------------------- #
#  2b. Which engine is capped
# --------------------------------------------------------------------------- #

def test_only_python_standard_is_capped():
    assert main.engine_speed_limit(python_decision()) == \
        pytest.approx(config.ENGINE_PYTHON_SPEED_LIMIT_MBPS)
    assert main.engine_speed_limit(turbo_decision()) == 0.0


def test_the_cap_is_a_documented_env_overridable_knob():
    assert config.ENGINE_PYTHON_SPEED_LIMIT_MBPS == 3.0
    assert config.ENGINE_PYTHON_SPEED_BURST_SECONDS == 0.0


def test_engine_speed_limit_survives_a_bogus_cap(monkeypatch):
    monkeypatch.setattr(main, "ENGINE_PYTHON_SPEED_LIMIT_MBPS", "not-a-number")
    assert main.engine_speed_limit(python_decision()) == 0.0


# --------------------------------------------------------------------------- #
#  2c. The cap inside a real download — proven with a fake clock
# --------------------------------------------------------------------------- #

async def _no_hook(_chunk_number):
    return None


def _wire_chunked_transfer(fake_bot, monkeypatch, msg, *, payload, chunk, on_chunk=None):
    """Serve *msg* and report progress in *chunk*-sized steps.

    ``on_chunk(n)`` runs just before the *n*-th progress callback, which is how
    a test pauses or cancels a transfer from the inside — the job only exists
    once the download has started, so polling from outside races it.
    """
    fake_bot.messages[msg.id] = msg
    hook = on_chunk or _no_hook
    state = {"chunks": 0}

    async def download_media(message, progress=None, **kwargs):
        size = msg.video.file_size
        position = 0
        while position < size:
            position = min(size, position + chunk)
            state["chunks"] += 1
            await hook(state["chunks"])
            if progress:
                await progress(position, size)
        return payload

    async def copy_message(**kwargs):
        raise RuntimeError("no native copy available")

    fake_bot.download_media = download_media
    fake_bot.copy_message = copy_message
    fake_bot.send_video = AsyncMock()
    fake_bot.send_document = AsyncMock()
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    monkeypatch.setattr(main, "TELEMETRY_EDIT_INTERVAL", 0.0)


def live_job():
    """The one download job currently registered (the tests run a single one)."""
    jobs = list(main.active_downloads.values())
    assert jobs, "no download job was registered"
    return jobs[0]


async def _run_capped_transfer(db, fake_bot, monkeypatch, *, turbo, size=6 * MB):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    if turbo:
        await db.set_engine_mode("lock_cpp")
    clock = FakeClock()
    monkeypatch.setattr(main, "TRANSFER_CLOCK", clock)
    monkeypatch.setattr(main, "TRANSFER_SLEEPER", clock.sleep)
    msg = media_message(21, size=size)
    payload = io.BytesIO(b"payload") if turbo else "/tmp/on-disk.mp4"
    _wire_chunked_transfer(fake_bot, monkeypatch, msg, payload=payload, chunk=MB)

    message = FakeMessage(text="t.me/public/21")
    status = FakeMessage(text="...", message_id=9)
    ok = await main.fetch_and_send(message, status, fake_bot, "publicname", 21)
    assert ok is True
    return clock, status


async def test_python_standard_is_paced_to_about_three_megabytes_per_second(
        db, fake_bot, monkeypatch):
    clock, _status = await _run_capped_transfer(db, fake_bot, monkeypatch, turbo=False)
    expected = (6 * MB) / (config.ENGINE_PYTHON_SPEED_LIMIT_MBPS * MB)
    assert clock.waited == pytest.approx(expected, rel=1e-6)
    assert clock.waited == pytest.approx(2.0), "6 MB at 3 MB/s takes 2 seconds"
    #: No busy-wait: exactly one sleep per chunk that needed budget.
    assert len(clock.sleeps) == 6


async def test_cpp_turbo_is_never_paced(db, fake_bot, monkeypatch):
    clock, _status = await _run_capped_transfer(db, fake_bot, monkeypatch, turbo=True)
    assert clock.sleeps == [], "Turbo runs uncapped"
    assert clock.elapsed == 0.0


async def test_the_hud_shows_the_throttled_speed(db, fake_bot, monkeypatch):
    _clock, status = await _run_capped_transfer(db, fake_bot, monkeypatch, turbo=False)
    speeds = [sc("3.0 MB/s") in edit["text"] for edit in status.edits]
    assert any(speeds), "the HUD must report the capped rate, not the line rate"
    assert sc("Speed") in status.shown_text


async def test_disabling_the_cap_removes_every_delay(db, fake_bot, monkeypatch):
    monkeypatch.setattr(main, "ENGINE_PYTHON_SPEED_LIMIT_MBPS", 0.0)
    clock, _status = await _run_capped_transfer(db, fake_bot, monkeypatch, turbo=False)
    assert clock.sleeps == []


async def test_the_progress_contract_and_cancellation_survive_the_throttle(
        db, fake_bot, monkeypatch):
    """A cancelled job still stops immediately with the pacer installed."""
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    clock = FakeClock()
    monkeypatch.setattr(main, "TRANSFER_CLOCK", clock)
    monkeypatch.setattr(main, "TRANSFER_SLEEPER", clock.sleep)
    msg = media_message(22, size=4 * MB)

    async def cancel_on_second_chunk(number):
        if number == 2:
            live_job()["cancelled"] = True

    _wire_chunked_transfer(fake_bot, monkeypatch, msg, payload="/tmp/x.mp4",
                           chunk=MB, on_chunk=cancel_on_second_chunk)

    message = FakeMessage(text="t.me/public/22")
    status = FakeMessage(text="...", message_id=9)
    result = await main.fetch_and_send(message, status, fake_bot, "publicname", 22)
    #: A cancelled download reports the batch-stopping sentinel, never a success.
    assert result == engines.CANCELLED
    assert fake_bot.send_video.await_count == 0, "nothing is uploaded after a cancel"
    #: The first chunk was still paced, so the pacer ran before the cancel hit.
    assert clock.sleeps == [pytest.approx(1 / 3)]


async def test_pause_and_resume_keep_working_with_the_pacer(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    clock = FakeClock()
    monkeypatch.setattr(main, "TRANSFER_CLOCK", clock)
    monkeypatch.setattr(main, "TRANSFER_SLEEPER", clock.sleep)
    msg = media_message(23, size=3 * MB)
    paused_at = {}

    async def pause_on_second_chunk(number):
        if number == 2:
            job = live_job()
            job["paused"] = True
            job["event"].clear()
            paused_at["chunks"] = number

    _wire_chunked_transfer(fake_bot, monkeypatch, msg, payload="/tmp/y.mp4",
                           chunk=MB, on_chunk=pause_on_second_chunk)

    async def resume_shortly():
        while "chunks" not in paused_at:
            await asyncio.sleep(0.005)
        job = live_job()
        job["paused"] = False
        job["event"].set()

    message = FakeMessage(text="t.me/public/23")
    status = FakeMessage(text="...", message_id=9)
    resumer = asyncio.create_task(resume_shortly())
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 23) is True
    await resumer
    assert paused_at == {"chunks": 2}, "the transfer really did pause mid-flight"
    #: Pausing costs nothing and refunds nothing: still exactly 3 MB / 3 MB/s.
    assert clock.waited == pytest.approx(1.0), "3 MB at 3 MB/s is one second"


# --------------------------------------------------------------------------- #
#  10. The engine pages only claim what the code really does
# --------------------------------------------------------------------------- #

ENGINE_PAGES = [
    ("architecture", lambda: ui.models_architecture_text(CPP)),
    ("upsell", ui.models_upsell_text),
    ("switcher", lambda: ui.models_locked_text(CPP)),
]


@pytest.mark.parametrize("name,render", ENGINE_PAGES, ids=[n for n, _ in ENGINE_PAGES])
def test_no_page_claims_a_native_c_cipher_as_a_turbo_feature(name, render):
    text = render().lower()
    assert "tgcrypto" not in text
    assert "native c cipher" not in text
    assert "native c " not in text


def test_architecture_page_lists_the_real_turbo_differences():
    text = ui.models_architecture_text(CPP)
    lowered = text.lower()
    #: A parallel worker pool on batches — Python Standard is single-stream.
    assert "parallel worker pool" in lowered
    assert str(config.ENGINE_TURBO_WORKERS) in text
    assert "single-stream" in lowered
    #: Zero-copy in-memory piping up to the configured budget.
    assert "zero-copy" in lowered
    assert str(config.ENGINE_ZERO_COPY_MAX_MB) in text
    #: Uncapped speed, stated against Python Standard's real cap.
    assert "uncapped" in lowered
    assert ui.speed_cap_label() in text
    #: Priority routing above the peak threshold.
    assert str(config.ENGINE_PEAK_THRESHOLD) in text


def test_architecture_page_says_plainly_where_turbo_changes_nothing():
    lowered = ui.models_architecture_text(CPP).lower()
    assert "where turbo does not change anything" in lowered
    assert "one mtproto stream on both engines" in lowered


def test_the_speed_cap_is_visible_where_the_addon_is_sold():
    cap = ui.speed_cap_label()
    assert cap == "~3 MB/s"
    assert cap in ui.models_upsell_text()
    assert "uncapped" in ui.models_upsell_text().lower()
    assert cap in ui.models_architecture_text(PYTHON)


def test_speed_cap_label_reports_uncapped_when_disabled():
    assert ui.speed_cap_label(0) == "uncapped"
    assert ui.speed_cap_label(None) == ui.speed_cap_label(
        config.ENGINE_PYTHON_SPEED_LIMIT_MBPS)


def test_engine_copy_stays_english_and_link_free():
    for _name, render in ENGINE_PAGES:
        text = render()
        assert text.strip()
        assert not any("\u0900" <= ch <= "\u0980" for ch in text)
        assert "http://" not in text and "https://" not in text
        assert "t.me/" not in text
