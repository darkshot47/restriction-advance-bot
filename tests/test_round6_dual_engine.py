"""Round 6 acceptance tests — dual engines, live telemetry, granular grants.

Every block of the requested overhaul is covered end to end, with Telegram and
MongoDB replaced by the in-memory fakes from ``conftest``:

1. Dual engine + autoscaling — the ``resolve_engine`` routing matrix, the
   ``TrafficMonitor`` peak detector, the three controller modes, the persisted
   mode, and the real C++ Turbo worker pool (measured, not assumed).
2. Live telemetry — the terminal-style HUD, the ``/start`` engine badge and the
   red **🧠 Models Architecture** footer button.
3. Tiered pricing — base + C++ Turbo add-on straight from ``config``, with the
   owner contact URL button on every plan / pricing / payment screen.
4. Granular VIP grant — tier → flags → duration → stored document → user notice.
5. The redesigned ``/admin`` panel command pairs.
6. The ``/mychannels`` user channel dashboard.
7. The standing constraints: English-only copy, 7×2 mobile budget, ≤28-char
   labels, ASCII-only ``callback_data``, links only inside ``url=`` buttons.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient
from pyrogram.enums import ChatMemberStatus

import config
import database
import engines
import main
import telemetry
import ui
from conftest import (FAKE_BOT_ID, FakeChat, FakeMessage, FakeUser, make_member,
                      make_query, sc)

CPP = config.ENGINE_CPP
PYTHON = config.ENGINE_PYTHON


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def owner_message(text="", **kwargs):
    return FakeMessage(text=text, user=FakeUser(main.OWNER_ID), **kwargs)


class Folded(str):
    """A rendered-message view whose ``in`` check ignores case.

    ``ui.plain_caps`` folds the Unicode small-caps font back to *lowercase*
    ASCII, so keeping the specification's own casing in the expectations below
    needs the needle folded the same way.
    """

    def __contains__(self, needle):
        return str.__contains__(self, str(needle).lower())


def plain(*texts) -> Folded:
    """Rendered bot copy as searchable text (small-caps reversed, case folded)."""
    return Folded("\n".join(ui.plain_caps(text or "") for text in texts).lower())


def unbold(text) -> Folded:
    """The same rendered copy without the Markdown bold markers.

    The HUD is written as ``📊 **Server Load:** CPU …`` — searching it for the
    specification's plain wording needs the ``**`` out of the way.
    """
    return Folded(str(text).replace("**", ""))


def media_message(msg_id=5, size=10 * 1024 * 1024, chat_id=-100888):
    """A downloadable message the FakeBot can serve from ``.messages``."""
    return SimpleNamespace(
        id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
        text=None, caption="Original caption",
        video=SimpleNamespace(file_id="v1", file_size=size),
        document=None, audio=None, photo=None, voice=None, video_note=None,
        sticker=None, animation=None, media=True,
    )


# --------------------------------------------------------------------------- #
#  1. The routing matrix — engines.resolve_engine
# --------------------------------------------------------------------------- #

ROUTING_TABLE = [
    # mode          has_models  preference  peak    engine    reason
    ("auto",        False,      None,       False,  PYTHON,   engines.REASON_DEFAULT),
    ("auto",        False,      None,       True,   CPP,      engines.REASON_PEAK_AUTOSCALE),
    ("auto",        False,      CPP,        False,  PYTHON,   engines.REASON_DEFAULT),
    ("auto",        False,      CPP,        True,   CPP,      engines.REASON_PEAK_AUTOSCALE),
    ("auto",        True,       None,       False,  PYTHON,   engines.REASON_DEFAULT),
    ("auto",        True,       PYTHON,     False,  PYTHON,   engines.REASON_DEFAULT),
    ("auto",        True,       CPP,        False,  CPP,      engines.REASON_USER_CHOICE),
    ("auto",        True,       CPP,        True,   CPP,      engines.REASON_USER_CHOICE),
    ("auto",        True,       PYTHON,     True,   CPP,      engines.REASON_PEAK_AUTOSCALE),
    ("lock_cpp",    False,      None,       False,  CPP,      engines.REASON_GLOBAL_LOCK),
    ("lock_cpp",    True,       PYTHON,     True,   CPP,      engines.REASON_GLOBAL_LOCK),
    ("lock_python", False,      CPP,        True,   PYTHON,   engines.REASON_GLOBAL_LOCK),
    ("lock_python", True,       None,       False,  PYTHON,   engines.REASON_GLOBAL_LOCK),
    ("lock_python", True,       PYTHON,     False,  PYTHON,   engines.REASON_GLOBAL_LOCK),
    ("lock_python", True,       CPP,        True,   CPP,      engines.REASON_MODELS_LOCKED),
]


@pytest.mark.parametrize("mode,has_models,preference,peak,engine,reason", ROUTING_TABLE)
def test_resolve_engine_truth_table(mode, has_models, preference, peak, engine, reason):
    """The whole dual-engine contract, expressed as one table."""
    decision = engines.resolve_engine(mode, has_models=has_models,
                                      preference=preference, peak=peak)
    assert decision.engine == engine
    assert decision.reason == reason
    assert decision.mode == mode
    assert decision.turbo is (engine == CPP)


def test_unknown_modes_and_engines_normalise_instead_of_crashing():
    assert engines.normalize_mode(None) == config.ENGINE_MODE_AUTO
    assert engines.normalize_mode("LOCK-CPP") == config.ENGINE_MODE_LOCK_CPP
    assert engines.normalize_mode("nonsense") == config.ENGINE_MODE_AUTO
    assert engines.normalize_engine("CPP") == CPP
    assert engines.normalize_engine("turbo") == CPP
    assert engines.normalize_engine("std") == PYTHON
    # No preference folds onto the default engine, never onto "unknown".
    assert engines.normalize_engine(None) == PYTHON
    assert engines.normalize_engine("nonsense") == PYTHON


def test_peak_is_strictly_above_the_threshold():
    """``exceed a threshold`` — equal to it is still normal traffic."""
    threshold = config.ENGINE_PEAK_THRESHOLD
    assert engines.is_peak(threshold - 1, threshold) is False
    assert engines.is_peak(threshold, threshold) is False
    assert engines.is_peak(threshold + 1, threshold) is True
    assert engines.is_peak(0) is False


def test_autoscaler_only_runs_in_auto_mode():
    assert engines.autoscaler_active("auto") is True
    assert engines.autoscaler_active("lock_cpp") is False
    assert engines.autoscaler_active("lock_python") is False


def test_switcher_needs_the_models_permission():
    assert engines.can_switch_engine("auto", has_models=False) is False
    assert engines.can_switch_engine("auto", has_models=True) is True
    # A Python lock keeps the premium switch alive; a C++ lock fixes it.
    assert engines.can_switch_engine("lock_python", has_models=True) is True
    assert engines.can_switch_engine("lock_cpp", has_models=True) is False


@pytest.mark.parametrize("mode,has_models,preference,expected_badge", [
    ("auto", False, None, ""),
    ("auto", False, None, engines.BADGE_PEAK),          # via peak below
    ("auto", True, CPP, engines.BADGE_USER),
    ("lock_cpp", False, None, engines.BADGE_GLOBAL_LOCK),
    ("lock_python", True, CPP, engines.BADGE_USER),
])
def test_badge_text_for_the_start_header(mode, has_models, preference, expected_badge):
    peak = expected_badge == engines.BADGE_PEAK
    decision = engines.resolve_engine(mode, has_models=has_models,
                                      preference=preference, peak=peak)
    assert decision.badge == expected_badge


# --------------------------------------------------------------------------- #
#  1b. TrafficMonitor — the autoscaler's only input
# --------------------------------------------------------------------------- #

def test_traffic_monitor_counts_concurrency_and_remembered_peaks():
    monitor = engines.TrafficMonitor(peak_threshold=2)
    assert monitor.active == 0 and monitor.peak is False
    monitor.enter()
    monitor.enter()
    assert monitor.active == 2
    assert monitor.peak is False, "at the threshold traffic is still normal"
    assert monitor.peak_events == 0
    monitor.enter()
    assert monitor.active == 3 and monitor.peak is True
    assert monitor.peak_events == 1, "crossing the threshold is one spike"
    assert monitor.peak_active == 3
    monitor.enter()
    assert monitor.peak_events == 1, "staying in peak is not a second spike"
    monitor.leave()
    monitor.leave()
    monitor.leave()
    monitor.leave()
    assert monitor.active == 0 and monitor.peak is False
    assert monitor.peak_active == 4, "the historical peak is never lowered"


def test_traffic_monitor_slot_restores_the_counter_on_exception():
    monitor = engines.TrafficMonitor(peak_threshold=1)
    with pytest.raises(RuntimeError):
        with monitor.slot():
            assert monitor.active == 1
            raise RuntimeError("upload exploded")
    assert monitor.active == 0, "a failed extraction must free its slot"


def test_traffic_monitor_slot_is_reentrant_across_tasks():
    monitor = engines.TrafficMonitor(peak_threshold=1)
    with monitor.slot():
        with monitor.slot():
            assert monitor.active == 2 and monitor.peak is True
        assert monitor.active == 1
    assert monitor.active == 0


def test_traffic_monitor_records_routing_analytics():
    monitor = engines.TrafficMonitor()
    monitor.record(engines.resolve_engine("auto"))
    monitor.record(engines.resolve_engine("lock_cpp"))
    monitor.record(engines.resolve_engine("lock_cpp"))
    snapshot = monitor.snapshot()
    assert snapshot["routed"] == {PYTHON: 1, CPP: 2}
    assert snapshot["decisions"] == 3
    assert snapshot["reasons"][engines.REASON_GLOBAL_LOCK] == 2
    assert snapshot["threshold"] == config.ENGINE_PEAK_THRESHOLD


def test_monitor_reset_clears_everything():
    monitor = engines.TrafficMonitor()
    monitor.enter()
    monitor.record(engines.resolve_engine("lock_cpp"))
    monitor.reset()
    snapshot = monitor.snapshot()
    assert snapshot["active"] == 0 and snapshot["peak_active"] == 0
    assert snapshot["decisions"] == 0
    assert snapshot["routed"] == {PYTHON: 0, CPP: 0}


# --------------------------------------------------------------------------- #
#  1c. EngineController — modes, persistence, autoscaler pausing
# --------------------------------------------------------------------------- #

def test_controller_mode_labels_are_english():
    controller = engines.EngineController()
    assert controller.mode == config.ENGINE_MODE_AUTO
    assert controller.mode_label == engines.ENGINE_MODE_LABELS["auto"]
    assert controller.set_mode("lock_cpp") == "lock_cpp"
    assert controller.mode_label == engines.ENGINE_MODE_LABELS["lock_cpp"]
    for label in engines.ENGINE_MODE_LABELS.values():
        assert label.isascii() and label


async def test_controller_loads_the_persisted_mode():
    store = FakeModeStore("lock_python")
    controller = engines.EngineController(mode_provider=store.read)
    assert controller.mode == "auto", "in memory it starts on AUTO"
    assert await controller.load_mode() == "lock_python"
    assert controller.mode == "lock_python"
    assert store.reads == 1


async def test_controller_falls_back_when_the_store_is_unreachable():
    async def broken():
        raise RuntimeError("mongo is down")

    controller = engines.EngineController(mode="lock_cpp", mode_provider=broken)
    assert await controller.load_mode() == "lock_cpp"


async def test_controller_decide_for_refreshes_the_mode_first():
    store = FakeModeStore("auto")
    controller = engines.EngineController(mode_provider=store.read)
    decision = await controller.decide_for(has_models=False, record=False)
    assert decision.engine == PYTHON
    store.mode = "lock_cpp"
    decision = await controller.decide_for(has_models=False, record=False)
    assert decision.engine == CPP and decision.reason == engines.REASON_GLOBAL_LOCK


class FakeModeStore:
    """Minimal stand-in for the persisted engine mode."""

    def __init__(self, mode):
        self.mode = mode
        self.reads = 0
        self.writes: list[str] = []

    async def read(self):
        self.reads += 1
        return self.mode

    async def write(self, mode):
        self.writes.append(mode)
        self.mode = mode


def test_lock_modes_pause_the_autoscaler():
    controller = engines.EngineController(mode="lock_cpp")
    assert controller.autoscaler_active() is False
    controller.set_mode("lock_python")
    assert controller.autoscaler_active() is False
    controller.set_mode("auto")
    assert controller.autoscaler_active() is True


def test_lock_cpp_forces_turbo_even_with_zero_traffic_and_a_python_preference():
    controller = engines.EngineController(mode="lock_cpp")
    for has_models in (False, True):
        for preference in (None, PYTHON, CPP):
            decision = controller.decide(has_models=has_models, preference=preference,
                                         record=False)
            assert decision.engine == CPP
            assert decision.reason == engines.REASON_GLOBAL_LOCK
            assert decision.badge == engines.BADGE_GLOBAL_LOCK


def test_lock_python_keeps_free_users_on_python_but_honours_a_models_choice():
    controller = engines.EngineController(mode="lock_python")
    # Peak traffic must not lift a free user onto Turbo: the autoscaler is off.
    for _ in range(controller.monitor.peak_threshold + 3):
        controller.monitor.enter()
    assert controller.monitor.peak is True
    free = controller.decide(has_models=False, preference=CPP, record=False)
    assert free.engine == PYTHON and free.peak is False
    vip = controller.decide(has_models=True, preference=CPP, record=False)
    assert vip.engine == CPP and vip.reason == engines.REASON_MODELS_LOCKED
    undecided_vip = controller.decide(has_models=True, preference=None, record=False)
    assert undecided_vip.engine == PYTHON


def test_controller_snapshot_exposes_the_admin_panel_numbers():
    controller = engines.EngineController(mode="auto")
    controller.monitor.enter()
    controller.decide(has_models=False, record=True)
    snapshot = controller.snapshot()
    assert snapshot["mode"] == "auto" and snapshot["mode_label"]
    assert snapshot["autoscaler"] is True
    assert snapshot["active"] == 1
    assert snapshot["routed"][PYTHON] == 1


# --------------------------------------------------------------------------- #
#  1d. Autoscaling through the real bot path
# --------------------------------------------------------------------------- #

async def test_auto_mode_escalates_to_cpp_under_peak_and_reverts(db):
    """The headline AUTO behaviour: spike → everything on Turbo, calm → Python."""
    await db.add_user(1001, "Tester")
    controller = main.ENGINE_CONTROLLER
    controller.monitor.peak_threshold = 2

    decision = await main.resolve_engine_for(1001)
    assert decision.engine == PYTHON and decision.reason == engines.REASON_DEFAULT

    for _ in range(3):                      # three extractions already in flight
        controller.monitor.enter()
    peak = await main.resolve_engine_for(1001)
    assert peak.engine == CPP
    assert peak.reason == engines.REASON_PEAK_AUTOSCALE
    assert peak.badge == engines.BADGE_PEAK

    for _ in range(3):                      # traffic normalises again
        controller.monitor.leave()
    calm = await main.resolve_engine_for(1001)
    assert calm.engine == PYTHON and calm.reason == engines.REASON_DEFAULT


async def test_models_permission_and_preference_drive_routing(db):
    await db.add_user(1001, "Tester")
    # Without the permission a stored preference is inert.
    await db.set_user_engine(1001, CPP)
    decision = await main.resolve_engine_for(1001)
    assert decision.engine == PYTHON
    assert await main.engine_preference_of(1001) is None

    await db.set_models_access(1001, True)
    assert await main.models_access(1001) is True
    decision = await main.resolve_engine_for(1001)
    assert decision.engine == CPP and decision.reason == engines.REASON_USER_CHOICE

    await db.set_user_engine(1001, PYTHON)
    decision = await main.resolve_engine_for(1001)
    assert decision.engine == PYTHON


async def test_owner_always_holds_the_models_permission(db):
    assert await main.models_access(main.OWNER_ID) is True
    decision = await main.resolve_engine_for(main.OWNER_ID, record=False)
    assert decision.has_models is True


async def test_expired_models_grant_stops_working(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    assert await main.models_access(1001) is True
    db.users[1001]["premium_expiry"] = dt.datetime.now() - dt.timedelta(days=1)
    assert await main.models_access(1001) is False
    assert (await main.resolve_engine_for(1001)).engine == PYTHON


async def test_engine_mode_is_persisted_and_read_back(db):
    assert await db.get_engine_mode() == config.DEFAULT_ENGINE_MODE
    await db.set_engine_mode("lock_cpp")
    assert await main.ENGINE_CONTROLLER.load_mode() == "lock_cpp"
    await db.add_user(1001, "Tester")
    decision = await main.resolve_engine_for(1001)
    assert decision.engine == CPP and decision.reason == engines.REASON_GLOBAL_LOCK


async def test_slot_is_released_when_an_extraction_raises(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")

    async def boom(*args, **kwargs):
        assert main.ENGINE_CONTROLLER.monitor.active == 1, "slot held during the run"
        raise RuntimeError("upload exploded")

    monkeypatch.setattr(main, "_fetch_and_send", boom)
    message = FakeMessage(text="t.me/public/5")
    status = FakeMessage(text="...", message_id=9)
    with pytest.raises(RuntimeError):
        await main.fetch_and_send(message, status, fake_bot, "publicname", 5)
    assert main.ENGINE_CONTROLLER.monitor.active == 0
    assert main.ENGINE_CONTROLLER.monitor.peak_active == 1


async def test_every_extraction_is_counted_in_the_analytics(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="t.me/public/5")
    status = FakeMessage(text="...", message_id=9)
    monkeypatch.setattr(main, "_fetch_and_send", AsyncMock(return_value=False))
    await main.fetch_and_send(message, status, fake_bot, "publicname", 5)
    assert main.ENGINE_CONTROLLER.monitor.snapshot()["routed"][PYTHON] == 1
    assert db.engine_stats.get(PYTHON, 0) == 1
    assert db.engine_stats.get(CPP, 0) == 0


# --------------------------------------------------------------------------- #
#  1e. The C++ Turbo worker pool — measured concurrency
# --------------------------------------------------------------------------- #

def test_engine_registry_describes_both_engines():
    python_engine = engines.get_engine(PYTHON)
    turbo = engines.get_engine(CPP)
    assert python_engine.workers == 1 and python_engine.zero_copy is False
    assert turbo.workers == config.ENGINE_TURBO_WORKERS
    assert turbo.workers > 1, "Turbo is multi-threaded"
    assert turbo.zero_copy is True
    assert turbo.version_label == f"v{config.ENGINE_TURBO_VERSION}"
    assert python_engine.version_label == ""
    assert engines.engine_label(CPP) != engines.engine_label(PYTHON)


async def _run_batch(db, monkeypatch, *, chat_id, user_id, links, tier=None):
    """Post *links* to a dump channel and measure the real overlap."""
    await db.add_user(user_id, "Tester")
    if tier:
        await db.add_premium(user_id, 30, tier=tier)
    await db.set_user_chat(user_id, chat_id, "Dump")
    post = FakeMessage(text="\n".join(f"https://t.me/source/{i}" for i in links),
                       user=FakeUser(user_id))
    post.chat = FakeChat(chat_id, "channel", "Dump")

    live = {"now": 0, "max": 0}

    async def fake_fetch(message, status, client, target, mid, **kwargs):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        await asyncio.sleep(0.02)
        live["now"] -= 1
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))
    success, failed = await main.extract_channel_links(
        post, db.users[user_id], sleeper=AsyncMock())
    return success, failed, live["max"]


async def test_turbo_runs_a_real_worker_pool(db, monkeypatch):
    """Turbo overlaps the slow parts of several files; Python never does."""
    await db.set_user_engine(1001, CPP)
    success, failed, overlap = await _run_batch(
        db, monkeypatch, chat_id=-100777, user_id=1001, links=range(1, 9), tier="all")
    assert (success, failed) == (8, 0)
    assert overlap == config.ENGINE_TURBO_WORKERS
    assert main.ENGINE_CONTROLLER.monitor.snapshot()["routed"][CPP] == 1


async def test_python_engine_stays_single_stream(db, monkeypatch):
    success, failed, overlap = await _run_batch(
        db, monkeypatch, chat_id=-100778, user_id=1001, links=range(1, 5), tier="public")
    assert (success, failed) == (4, 0)
    assert overlap == 1, "the Python engine is strictly sequential"
    assert main.ENGINE_CONTROLLER.monitor.snapshot()["routed"][PYTHON] == 1


async def test_single_link_post_never_spawns_the_pool(db, monkeypatch):
    """One link has nothing to overlap, so Turbo behaves like Python there."""
    await db.set_user_engine(1001, CPP)
    success, failed, overlap = await _run_batch(
        db, monkeypatch, chat_id=-100779, user_id=1001, links=[1], tier="all")
    assert (success, failed) == (1, 0)
    assert overlap == 1


async def test_turbo_pool_applies_to_a_locked_batch(db, monkeypatch):
    """A global C++ lock gives free users the pool too."""
    await db.set_engine_mode("lock_cpp")
    # This user never bought the models feature: the global lock still pools them.
    success, failed, overlap = await _run_batch(
        db, monkeypatch, chat_id=-100780, user_id=1001, links=range(1, 7),
        tier="public")
    assert (success, failed) == (6, 0)
    assert overlap == config.ENGINE_TURBO_WORKERS
    assert await main.models_access(1001) is False


async def test_batch_records_the_channel_file_counter(db, monkeypatch):
    await _run_batch(db, monkeypatch, chat_id=-100781, user_id=1001,
                     links=range(1, 4), tier="public")
    assert await db.get_channel_files(-100781) == 3


# --------------------------------------------------------------------------- #
#  1f. Zero-copy piping — the Turbo transfer really skips the disk
# --------------------------------------------------------------------------- #

def _wire_transfer(fake_bot, monkeypatch, msg, *, payload, expected_in_memory=None):
    """Serve *msg* and record how the bot asked for the bytes.

    ``payload`` is what ``download_media`` hands back: a ``BytesIO`` for the
    in-memory (zero-copy) path, a path string for the streamed-to-disk path —
    exactly Kurigram's contract for ``in_memory=True`` / ``False``.
    """
    fake_bot.messages[msg.id] = msg
    seen = {}

    async def download_media(message, progress=None, **kwargs):
        seen.update(kwargs)
        if progress:
            await progress(msg.video.file_size, msg.video.file_size)
        return payload

    async def copy_message(**kwargs):
        raise RuntimeError("no native copy available")

    fake_bot.download_media = download_media
    fake_bot.copy_message = copy_message
    fake_bot.send_video = AsyncMock()
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    monkeypatch.setattr(main, "TELEMETRY_EDIT_INTERVAL", 0.0)
    if expected_in_memory is not None:
        assert seen.get("in_memory") is expected_in_memory
    return seen


async def test_turbo_pipes_a_small_file_straight_through_memory(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.set_engine_mode("lock_cpp")
    buffer = io.BytesIO(b"payload")
    buffer.name = "file.mp4"
    msg = media_message(11)
    seen = _wire_transfer(fake_bot, monkeypatch, msg, payload=buffer)

    message = FakeMessage(text="t.me/public/11")
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 11) is True

    assert seen["in_memory"] is True, "Turbo asks Kurigram for an in-memory transfer"
    uploaded = fake_bot.send_video.call_args.args[1]
    assert uploaded is buffer, "the downloaded handle goes straight to the uploader"
    assert buffer.closed, "the buffer is released once the upload is done"
    assert msg.video.file_size <= config.ENGINE_ZERO_COPY_MAX_BYTES


async def test_python_standard_always_streams_to_disk(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    msg = media_message(12)
    seen = _wire_transfer(fake_bot, monkeypatch, msg, payload="/tmp/on-disk.mp4")

    message = FakeMessage(text="t.me/public/12")
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 12) is True
    assert seen["in_memory"] is False
    assert fake_bot.send_video.call_args.args[1] == "/tmp/on-disk.mp4"


async def test_turbo_falls_back_to_disk_above_the_zero_copy_budget(db, fake_bot,
                                                                   monkeypatch):
    """A multi-GB premium upload must never be held in RAM."""
    await db.add_user(1001, "Tester")
    await db.set_engine_mode("lock_cpp")
    monkeypatch.setattr(main, "ENGINE_ZERO_COPY_MAX_BYTES", 1024)
    msg = media_message(13, size=4096)
    seen = _wire_transfer(fake_bot, monkeypatch, msg, payload="/tmp/big.mp4")

    message = FakeMessage(text="t.me/public/13")
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 13) is True
    assert seen["in_memory"] is False
    assert fake_bot.send_video.call_args.args[1] == "/tmp/big.mp4"


async def test_an_unknown_file_size_stays_on_disk(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.set_engine_mode("lock_cpp")
    msg = media_message(14, size=0)
    seen = _wire_transfer(fake_bot, monkeypatch, msg, payload="/tmp/unknown.mp4")

    message = FakeMessage(text="t.me/public/14")
    status = FakeMessage(text="...", message_id=9)
    await main.fetch_and_send(message, status, fake_bot, "publicname", 14)
    assert seen["in_memory"] is False


def test_zero_copy_budget_is_configured_and_bounded():
    assert config.ENGINE_ZERO_COPY_MAX_MB > 0
    assert config.ENGINE_ZERO_COPY_MAX_BYTES == config.ENGINE_ZERO_COPY_MAX_MB * 1024 ** 2
    assert engines.get_engine(CPP).zero_copy is True
    assert engines.get_engine(PYTHON).zero_copy is False
    assert "zero-copy" in ui.models_architecture_text(CPP).lower()
    assert str(config.ENGINE_ZERO_COPY_MAX_MB) in ui.models_architecture_text(CPP)


# --------------------------------------------------------------------------- #
#  2. Live telemetry HUD — the exact strings from the specification
# --------------------------------------------------------------------------- #

def test_progress_bar_matches_the_specification():
    assert ui.progress_bar(68) == "[████████░░░░]"
    assert ui.progress_bar(0) == "[░░░░░░░░░░░░]"
    assert ui.progress_bar(100) == "[████████████]"
    assert ui.progress_bar(50) == "[██████░░░░░░]"
    assert ui.progress_bar(None) == "[░░░░░░░░░░░░]"
    assert ui.progress_bar(-20) == "[░░░░░░░░░░░░]"
    assert ui.progress_bar(500) == "[████████████]"
    assert len(ui.progress_bar(37, width=20)) == 22


def test_engine_lines_match_the_specification():
    assert ui.telemetry_engine_line(CPP) == "⚡ **Engine:** C++ Turbo v2.4 [Active]"
    assert ui.telemetry_engine_line(PYTHON) == "⚙️ **Engine:** Python Standard [Active]"
    assert ui.telemetry_engine_line(CPP, "Paused") == \
        "⚡ **Engine:** C++ Turbo v2.4 [Paused]"


def test_server_load_line_matches_the_specification():
    sample = telemetry.ServerSample(cpu_percent=19.2, memory_percent=41.8, ping_ms=11.4)
    assert ui.telemetry_load_line(sample) == \
        "📊 **Server Load:** CPU 19.2% | RAM 41.8% | Ping 11ms"


def test_load_line_degrades_to_dashes_instead_of_inventing_numbers():
    assert ui.telemetry_load_line(None) == \
        "📊 **Server Load:** CPU -- | RAM -- | Ping --"
    partial = telemetry.ServerSample(cpu_percent=7.0)
    assert ui.telemetry_load_line(partial) == \
        "📊 **Server Load:** CPU 7.0% | RAM -- | Ping --"


def test_progress_line_matches_the_specification():
    assert ui.telemetry_progress_line(68) == \
        "📥 **Downloading:** 68% [████████░░░░]"
    assert ui.telemetry_progress_line(None) == \
        "📥 **Downloading:** -- [░░░░░░░░░░░░]"
    assert ui.telemetry_progress_line(42, stage="Uploading") == \
        "📥 **Uploading:** 42% [█████░░░░░░░]"
    assert ui.telemetry_progress_line(42, paused=True) == \
        "📥 **Paused:** 42% [█████░░░░░░░]"


def test_speed_and_eta_line_matches_the_specification():
    state = telemetry.TransferState(percent=68, speed=44.23 * telemetry.MB, eta=3.0)
    assert ui.telemetry_speed_line(state) == "🚀 **Speed:** 44.2 MB/s • **ETA:** 00:03"
    assert ui.telemetry_speed_line(None) == "🚀 **Speed:** -- • **ETA:** --:--"


@pytest.mark.parametrize("mbps,expected", [
    (None, "--"), (0, "0.0 MB/s"), (44.23, "44.2 MB/s"),
    (1023.9, "1023.9 MB/s"), (1024, "1.00 GB/s"), (1536, "1.50 GB/s"),
])
def test_format_speed(mbps, expected):
    assert ui.format_speed(mbps) == expected


@pytest.mark.parametrize("seconds,expected", [
    (None, "--:--"), (-5, "--:--"), (0, "00:00"), (3, "00:03"),
    (59, "00:59"), (60, "01:00"), (605, "10:05"), (3600, "1:00:00"),
    (3725, "1:02:05"),
])
def test_format_eta(seconds, expected):
    assert ui.format_eta(seconds) == expected


@pytest.mark.parametrize("value,expected", [(None, "--"), (19.234, "19.2%"),
                                            (0, "0.0%"), (100, "100.0%")])
def test_format_percent(value, expected):
    assert ui.format_percent(value) == expected


@pytest.mark.parametrize("value,expected", [(None, "--"), (11.4, "11ms"),
                                            (0.4, "0ms"), (250, "250ms")])
def test_format_ping(value, expected):
    assert ui.format_ping(value) == expected


def test_full_hud_is_the_four_specification_lines():
    sample = telemetry.ServerSample(cpu_percent=19.2, memory_percent=41.8, ping_ms=11)
    state = telemetry.TransferState(percent=68, speed=44.2 * telemetry.MB, eta=3)
    hud = ui.telemetry_hud(CPP, 68, sample=sample, state=state)
    assert hud.split("\n") == [
        "⚡ **Engine:** C++ Turbo v2.4 [Active]",
        "📥 **Downloading:** 68% [████████░░░░]",
        "📊 **Server Load:** CPU 19.2% | RAM 41.8% | Ping 11ms",
        "🚀 **Speed:** 44.2 MB/s • **ETA:** 00:03",
    ]
    python_hud = ui.telemetry_hud(PYTHON, 68, sample=sample, state=state)
    assert python_hud.startswith("⚙️ **Engine:** Python Standard [Active]")


def test_hud_drops_the_load_line_when_telemetry_is_off(monkeypatch):
    monkeypatch.setattr(config, "TELEMETRY_ENABLED", False)
    hud = ui.telemetry_hud(CPP, 12, sample=telemetry.ServerSample(cpu_percent=5.0))
    assert "Server Load" not in hud
    assert hud.split("\n")[0].startswith("⚡")
    assert "12%" in hud


def test_channel_notice_can_carry_the_hud():
    hud = ui.telemetry_hud(PYTHON, 30)
    notice = ui.channel_download_notice(hud=hud)
    assert notice.startswith(hud)
    assert config.BOT_USERNAME in notice
    assert "Downloading" in notice
    # The legacy notice is still the body — the HUD is prepended, not merged.
    assert ui.channel_download_public_text() in notice
    assert "paused" in ui.channel_download_public_text(30, True)


# --------------------------------------------------------------------------- #
#  2b. HostMonitor — cached, injectable, never blocking
# --------------------------------------------------------------------------- #

async def test_host_monitor_reads_through_the_injected_probes(fake_host):
    sample = await main.HOST_MONITOR.sample()
    assert sample.cpu_percent == pytest.approx(19.2, abs=0.6)
    assert sample.memory_percent == pytest.approx(41.8)
    assert sample.ping_ms == pytest.approx(11.0)
    assert sample.known is True


async def test_host_monitor_caches_readings_within_the_ttl():
    host = SimpleNamespace(calls=0, pings=0)

    def cpu():
        host.calls += 1
        return 900.0, 1000.0 * host.calls

    async def ping(host_name=None, port=None):
        host.pings += 1
        return 12.0

    clock = SimpleNamespace(now=0.0)
    monitor = telemetry.HostMonitor(cpu_probe=cpu, memory_probe=lambda: 50.0,
                                    ping_probe=ping, clock=lambda: clock.now,
                                    sample_ttl=1.0, ping_ttl=5.0)
    await monitor.sample()
    primed = host.calls
    assert host.pings == 1, "the first reading always pings"
    await monitor.sample()
    await monitor.sample()
    assert host.calls == primed, "CPU is read once per TTL, not once per HUD tick"
    assert monitor.samples_taken == 1
    clock.now = 1.5
    await monitor.sample()
    assert host.calls == primed + 1, "the sample TTL expired"
    assert host.pings == 1, "the ping lives on its own, longer TTL"
    clock.now = 6.0
    await monitor.sample()
    assert host.pings == 2


async def test_host_monitor_survives_probes_that_fail():
    def broken_cpu():
        raise OSError("/proc is not here")

    async def broken_ping(host_name=None, port=None):
        raise OSError("no route")

    monitor = telemetry.HostMonitor(cpu_probe=broken_cpu,
                                    memory_probe=lambda: None,
                                    ping_probe=broken_ping,
                                    sample_ttl=0.0, ping_ttl=0.0)
    sample = await monitor.sample()
    assert sample.cpu_percent is None and sample.ping_ms is None
    assert ui.telemetry_load_line(sample).count("--") == 3


def test_cpu_percent_from_times_is_guarded():
    assert telemetry.cpu_percent_from_times(None, None) is None
    assert telemetry.cpu_percent_from_times((0, 0), (0, 0)) is None
    # 25 idle out of 100 total ticks => 75% busy.
    assert telemetry.cpu_percent_from_times((1000, 1000), (1025, 1100)) == \
        pytest.approx(75.0)


def test_load_average_fallback_never_exceeds_100_percent(monkeypatch):
    monkeypatch.setattr(telemetry.os, "getloadavg", lambda: (4.0, 3.0, 2.0))
    monkeypatch.setattr(telemetry.os, "cpu_count", lambda: 4)
    assert telemetry.load_average_cpu_percent() == pytest.approx(100.0)
    monkeypatch.setattr(telemetry.os, "getloadavg", lambda: (1.0, 1.0, 1.0))
    assert telemetry.load_average_cpu_percent() == pytest.approx(25.0)
    monkeypatch.setattr(telemetry.os, "getloadavg",
                        lambda: (_ for _ in ()).throw(OSError("no loadavg")))
    assert telemetry.load_average_cpu_percent() is None


# --------------------------------------------------------------------------- #
#  2c. TransferMeter — percent, smoothed speed and ETA
# --------------------------------------------------------------------------- #

def test_transfer_meter_computes_percent_speed_and_eta():
    clock = SimpleNamespace(now=0.0)
    meter = telemetry.TransferMeter(100, clock=lambda: clock.now)
    assert meter.state.percent == 0

    clock.now = 1.0
    state = meter.update(50, 100)
    assert state.percent == 50
    assert state.speed == pytest.approx(50.0)
    assert state.eta == pytest.approx(1.0)
    assert state.speed_mbps == pytest.approx(50.0 / telemetry.MB)

    clock.now = 2.0
    state = meter.update(100, 100)
    assert state.percent == 100 and state.complete is True
    assert state.eta == pytest.approx(0.0)
    assert meter.finished_at == 2.0


def test_transfer_meter_grows_when_telegram_reports_a_bigger_total():
    clock = SimpleNamespace(now=0.0)
    meter = telemetry.TransferMeter(10, clock=lambda: clock.now)
    clock.now = 1.0
    state = meter.update(40, 80)
    assert meter.total == 80
    assert state.percent == 50


def test_transfer_meter_never_divides_by_zero():
    meter = telemetry.TransferMeter(0)
    state = meter.update(0, 0)
    assert state.percent == 0
    assert state.speed in (None, 0) or state.speed >= 0


def test_transfer_meter_drops_the_gap_after_a_pause():
    clock = SimpleNamespace(now=0.0)
    meter = telemetry.TransferMeter(1000, clock=lambda: clock.now)
    clock.now = 1.0
    meter.update(100, 1000)
    clock.now = 600.0                     # ten minutes paused
    meter.pause()
    meter.resume()
    state = meter.update(200, 1000)
    assert state.percent == 20
    assert state.speed is None or state.speed < 1000, "no bogus post-pause speed"


def test_transfer_meter_finish_reports_a_full_bar():
    meter = telemetry.TransferMeter(2048)
    meter.update(1024, 2048)
    state = meter.finish()
    assert state.percent == 100 and state.current == 2048


# --------------------------------------------------------------------------- #
#  2d. The HUD inside a real download
# --------------------------------------------------------------------------- #

def _wire_download(fake_bot, monkeypatch, msg, *, progress_steps=(20, 68, 100)):
    """Make the FakeBot serve *msg* and drive a scripted progress callback."""
    fake_bot.messages[msg.id] = msg
    calls = []

    async def download_media(message, progress=None, **kwargs):
        for step in progress_steps:
            await progress(int(msg.video.file_size * step / 100), msg.video.file_size)
        return "/tmp/fake.mp4"

    async def copy_message(**kwargs):
        raise RuntimeError("no native copy available")

    fake_bot.download_media = download_media
    fake_bot.copy_message = copy_message
    fake_bot.send_video = AsyncMock()
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    monkeypatch.setattr(main, "TELEMETRY_EDIT_INTERVAL", 0.0)
    return calls


async def test_python_download_renders_the_python_hud(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    msg = media_message(5)
    _wire_download(fake_bot, monkeypatch, msg)
    message = FakeMessage(text="t.me/public/5")
    status = FakeMessage(text="...", message_id=9)

    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 5) is True
    joined = unbold(plain(*[edit["text"] for edit in status.edits]))
    assert "Engine: Python Standard [Active]" in joined
    assert "Server Load: CPU" in joined and "RAM" in joined and "Ping" in joined
    assert "Downloading: 68% [████████░░░░]" in joined
    assert "ETA:" in joined and "Speed:" in joined
    assert "MB/s" in joined or "GB/s" in joined


async def test_turbo_download_renders_the_turbo_hud(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    await db.set_engine_mode("lock_cpp")
    msg = media_message(6)
    _wire_download(fake_bot, monkeypatch, msg)
    message = FakeMessage(text="t.me/public/6")
    status = FakeMessage(text="...", message_id=9)

    await main.fetch_and_send(message, status, fake_bot, "publicname", 6)
    joined = unbold(plain(*[edit["text"] for edit in status.edits]))
    assert f"Engine: C++ Turbo v{config.ENGINE_TURBO_VERSION} [Active]" in joined
    assert "Downloading:" in joined
    assert db.engine_stats[CPP] == 1


async def test_hud_starts_at_zero_percent_with_the_download_controls(db, fake_bot,
                                                                     monkeypatch):
    await db.add_user(1001, "Tester")
    msg = media_message(7)
    _wire_download(fake_bot, monkeypatch, msg, progress_steps=(100,))
    message = FakeMessage(text="t.me/public/7")
    status = FakeMessage(text="...", message_id=9)
    await main.fetch_and_send(message, status, fake_bot, "publicname", 7)

    first = status.edits[0]
    assert "0% [░░░░░░░░░░░░]" in plain(first["text"])
    controls = [b.callback_data for row in first["reply_markup"].inline_keyboard
                for b in row]
    assert any(str(data).startswith("dl:") for data in controls)


async def test_telemetry_never_breaks_a_download(db, fake_bot, monkeypatch):
    await db.add_user(1001, "Tester")
    msg = media_message(8)
    _wire_download(fake_bot, monkeypatch, msg)

    async def broken_sample():
        raise RuntimeError("no /proc in this container")

    monkeypatch.setattr(main.HOST_MONITOR, "sample", broken_sample)
    message = FakeMessage(text="t.me/public/8")
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 8) is True
    joined = unbold(plain(*[edit["text"] for edit in status.edits]))
    assert "Server Load: CPU -- | RAM -- | Ping --" in joined


# --------------------------------------------------------------------------- #
#  2e. The /start badge and the red Models Architecture button
# --------------------------------------------------------------------------- #

def test_start_badge_strings_match_the_specification():
    peak = engines.resolve_engine("auto", has_models=False, peak=True)
    assert ui.engine_status_line(peak) == \
        "⚡ **Active Engine:** [C++ Turbo 🚀 (Peak Auto-Scale)]"
    lock = engines.resolve_engine("lock_cpp")
    assert ui.engine_status_line(lock) == \
        "⚡ **Active Engine:** [C++ Turbo 🚀 (Global Lock)]"
    idle = engines.resolve_engine("auto")
    assert ui.engine_status_line(idle) == \
        "🟢 **Active Engine:** [Python Standard ⚙️]"


def test_models_architecture_button_is_red_and_lives_in_the_start_footer():
    button = ui.models_architecture_button()
    assert button.callback_data == "models_info"
    assert button.text == sc("🧠 Models Architecture")
    if ui.styles_enabled():
        assert button.style == ui.BUTTON_DANGER, "the footer button must be RED"

    rows = ui.start_keyboard().inline_keyboard
    assert len(rows) == 7, rows
    assert rows[-1] == [button], "the red button owns the last row of /start"
    assert rows[-1][0].text == sc("🧠 Models Architecture")


def test_start_text_carries_the_engine_badge():
    text = ui.start_text("Tester", False, ui.engine_status_line(
        engines.resolve_engine("lock_cpp")))
    assert "Active Engine:" in text and "Global Lock" in text
    # The positional signature used by the older tests still works.
    assert "Tester" in ui.start_text("Tester", True)


async def test_start_shows_the_live_engine_badge(db, press):
    await db.add_user(1001, "Tester")
    await db.set_engine_mode("lock_cpp")
    message = FakeMessage(text="/start")
    await main.start_handler(None, message)
    assert "Global Lock" in plain(message.shown_text)
    assert "C++ Turbo" in plain(message.shown_text)

    await db.set_engine_mode("auto")
    message2 = FakeMessage(text="/start")
    await main.start_handler(None, message2)
    assert "Python Standard" in plain(message2.shown_text)
    assert "Peak Auto-Scale" not in plain(message2.shown_text)


async def test_start_menu_button_opens_the_architecture_page(db, press):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="/start")
    await main.start_handler(None, message)
    assert "models_info" in message.callback_data()

    await press(message, "models_info")
    text = plain(message.shown_text)
    assert "MODELS ARCHITECTURE" in text
    assert "PYTHON STANDARD" in text and "C++ TURBO" in text
    assert "TRAFFIC HANDLING" in text
    assert "HOW TO UNLOCK" in text or "unlock" in text.lower()
    # Pricing of the add-on is quoted from config.
    assert f"{config.RUPEE}149" in text
    # Links only live in url= buttons: the page mentions, never prints, a URL.
    assert "https://" not in text
    assert f"@{config.PAYMENT_CONTACT}" in text
    urls = [b.url for b in flat(message.shown_markup) if b.url]
    assert config.PAYMENT_CONTACT in "".join(urls)
    # A free user is offered the upgrade, not the switcher.
    assert "premium_plans" in message.callback_data()


async def test_architecture_page_offers_the_switcher_to_a_models_holder(db, press):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    message = FakeMessage(text="/start")
    await press(message, "models_info")
    assert "cmd_models" in message.callback_data()
    assert "premium_plans" not in message.callback_data()


# --------------------------------------------------------------------------- #
#  3. Tiered pricing with the C++ Turbo add-on
# --------------------------------------------------------------------------- #

def test_shipped_prices_are_the_requested_ones():
    plans = config.PREMIUM_PLANS
    assert (config.plan_base_price(plans["month"]),
            config.plan_addon_price(plans["month"]),
            config.plan_total_price(plans["month"])) == (99, 50, 149)
    assert (config.plan_base_price(plans["quarter"]),
            config.plan_addon_price(plans["quarter"]),
            config.plan_total_price(plans["quarter"])) == (249, 100, 349)
    assert (config.plan_base_price(plans["year"]),
            config.plan_addon_price(plans["year"]),
            config.plan_total_price(plans["year"])) == (700, 149, 849)
    assert plans["month"]["days"] == 30
    assert plans["quarter"]["days"] == 90
    assert plans["year"]["days"] == 365


def test_config_is_the_single_source_of_truth_for_the_contact_link():
    assert config.PAYMENT_CONTACT == "XyrDeveloper"
    assert ui.contact_owner_url() == f"https://t.me/{config.PAYMENT_CONTACT}"
    assert config.OWNER_CONTACT_URL == ui.contact_owner_url()
    button = ui.owner_contact_button()
    assert button.url == ui.contact_owner_url()
    assert button.callback_data is None
    assert button.text == sc("💬 Contact Owner")


def test_contact_button_follows_a_changed_owner(monkeypatch):
    monkeypatch.setattr(config, "PAYMENT_CONTACT", "SomeoneElse")
    monkeypatch.setattr(config, "OWNER_CONTACT_URL", "")
    assert ui.contact_owner_url() == "https://t.me/SomeoneElse"
    assert ui.owner_contact_button().url == "https://t.me/SomeoneElse"
    assert "@SomeoneElse" in ui.plans_text()
    assert "@SomeoneElse" in ui.payment_text(config.PREMIUM_PLANS["month"])
    assert "@SomeoneElse" in ui.models_upsell_text() or "SomeoneElse" in \
        ui.models_architecture_text()


def test_plans_table_shows_base_plus_addon_equals_total():
    table = ui.plans_table()
    for key, plan in config.PREMIUM_PLANS.items():
        base = config.plan_base_price(plan)
        addon = config.plan_addon_price(plan)
        line = next(line for line in table.split("\n") if plan["title"] in line)
        assert f"{config.RUPEE}{base} Standard" in line
        assert f"+{config.RUPEE}{addon} C++ Turbo" in line
        assert f"{config.RUPEE}{base + addon}" in line


def test_plans_screen_lists_every_price_and_the_contact_button():
    text = ui.plans_text()
    for amount in ("99", "149", "249", "349", "700", "849"):
        assert amount in text
    assert f"@{config.PAYMENT_CONTACT}" in text
    assert "https://" not in text

    buttons = flat(ui.plans_keyboard())
    data = [b.callback_data for b in buttons]
    for key in config.PREMIUM_PLANS:
        assert f"buy:{key}" in data
        assert f"buy:{key}:turbo" in data
    assert any(b.url == ui.contact_owner_url() for b in buttons)


def test_payment_wizard_amount_follows_the_chosen_variant():
    month = config.PREMIUM_PLANS["month"]
    standard = ui.payment_text(month, turbo=False)
    turbo = ui.payment_text(month, turbo=True)
    assert f"{config.RUPEE}99" in standard and "₹149" not in standard
    assert f"{config.RUPEE}149" in turbo
    assert f"{config.RUPEE}99 base + {config.RUPEE}50 C++ Turbo add-on" in turbo
    assert "Python Standard" in standard and "C++ Turbo" in turbo
    assert f"@{config.PAYMENT_CONTACT}" in turbo
    assert any(b.url == ui.contact_owner_url() for b in flat(ui.payment_keyboard("tok")))


def test_turbo_benefits_are_listed_where_the_addon_is_sold():
    upsell = ui.models_upsell_text()
    assert "C++ TURBO ENGINE" in upsell
    assert "Multi-threaded" in upsell or "multi-threaded" in upsell.lower()
    assert "Zero-copy" in upsell or "zero-copy" in upsell.lower()
    assert f"{config.RUPEE}149" in upsell
    assert any(b.callback_data == "premium_plans"
               for b in flat(ui.models_upsell_keyboard()))
    assert any(b.url == ui.contact_owner_url()
               for b in flat(ui.models_upsell_keyboard()))


async def test_buying_the_turbo_variant_charges_the_addon_and_grants_models(db, press):
    await db.add_user(1001, "Tester")
    await db.set_qr("owner-qr")
    message = FakeMessage(text="/premium")
    await main.premium_handler(None, message)
    await press(message, "premium_plans")
    assert "buy:month:turbo" in message.callback_data()

    await press(message, "buy:month:turbo")
    text = plain(message.shown_text)
    assert "149" in text and "C++ Turbo" in text
    pending = main.payment_pending[1001]
    assert pending["turbo"] is True and pending["plan"] == "month"

    # Owner approves -> the models flag is set by the tier, not by hand.
    review = owner_message(text="/payments")
    await press(review, "payok:1001:month:turbo")
    user = db.users[1001]
    assert user["is_premium"] is True
    assert user["has_models_access"] is True
    assert user["premium_tier"] == "all"
    assert user["premium_source"] == config.PREMIUM_SOURCE_MANUAL


async def test_buying_the_standard_variant_grants_no_models(db, press):
    await db.add_user(1001, "Tester")
    await db.set_qr("owner-qr")
    message = FakeMessage(text="/premium")
    await press(message, "premium_plans")
    await press(message, "buy:month")
    assert main.payment_pending[1001]["turbo"] is False
    review = owner_message(text="/payments")
    await press(review, "payok:1001:month")
    user = db.users[1001]
    assert user["is_premium"] is True
    assert user["has_models_access"] is False
    assert user["has_private_access"] is True
    assert user["premium_tier"] == "private"


# --------------------------------------------------------------------------- #
#  4. Granular admin VIP grant (/addpremium)
# --------------------------------------------------------------------------- #

TIER_FLAGS = {
    "public":  (False, False),
    "models":  (False, True),
    "private": (True, False),
    "all":     (True, True),
}


def test_config_grant_tiers_match_the_requested_four_steps():
    assert config.GRANT_TIER_KEYS == ("public", "models", "private", "all")
    numbers = [config.GRANT_TIERS[key]["number"] for key in config.GRANT_TIER_KEYS]
    assert numbers == ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    labels = [config.GRANT_TIERS[key]["label"] for key in config.GRANT_TIER_KEYS]
    assert labels == ["Only Public", "Public + Models", "Public + Private", "All-in-One"]
    for key, (private, models) in TIER_FLAGS.items():
        assert config.GRANT_TIERS[key]["has_private_access"] is private
        assert config.GRANT_TIERS[key]["has_models_access"] is models


def test_grant_tier_keyboard_offers_the_four_tiers():
    buttons = flat(ui.grant_tier_keyboard())
    data = [b.callback_data for b in buttons]
    assert data[:4] == [f"grant_tier:{key}" for key in config.GRANT_TIER_KEYS]
    assert "cancel_action" in data
    text = ui.grant_tier_text(1001, "Tester", 45)
    for key in config.GRANT_TIER_KEYS:
        assert config.GRANT_TIERS[key]["label"] in text
        assert config.GRANT_TIERS[key]["description"].split(" ")[0] in text
    assert "Step 1 of 2" in text


def test_grant_duration_keyboard_offers_every_requested_duration():
    buttons = flat(ui.grant_duration_keyboard("all"))
    data = [b.callback_data for b in buttons]
    for key in ("month", "quarter", "year", "lifetime", "custom"):
        assert f"grant_dur:all:{key}" in data
    assert "grant_back:all" in data and "cancel_action" in data
    # A duration typed in the command becomes a one-tap button.
    typed = [b.callback_data for b in flat(ui.grant_duration_keyboard("all", 45))]
    assert "grant_dur:all:typed:45" in typed
    text = ui.grant_duration_text(1001, "all", "Tester", 45)
    assert "Step 2 of 2" in text and "All-in-One" in text
    assert "no expiry" in text and "365 days" in text


@pytest.mark.parametrize("key,state,days", [
    ("month", "ok", 30), ("quarter", "ok", 90), ("year", "ok", 365),
    ("lifetime", "ok", None), ("custom", "custom", None),
    ("typed:45", "ok", 45), ("TYPED:7", "ok", 7),
    ("nonsense", "invalid", None), ("typed:0", "invalid", None),
    ("typed:-3", "invalid", None), ("typed:99999", "invalid", None),
    ("", "invalid", None),
])
def test_parse_grant_duration(key, state, days):
    assert main.parse_grant_duration(key) == (state, days)


@pytest.mark.parametrize("value,expected", [
    ("public", "public"), ("models", "models"), ("private", "private"), ("all", "all"),
    ("ALL", "all"), ("all-in-one", "all"), ("All in One", "all"),
    ("public + models", "models"), ("Only Public", "public"),
    ("Public + Private", "private"), ("full", "private"), ("nope", None),
    ("", None), (None, None),
])
def test_normalize_tier_including_the_legacy_alias(value, expected):
    assert main.normalize_tier(value) == expected


async def test_addpremium_step_one_lists_the_tiers(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    assert "GRANULAR VIP GRANT" in plain(message.shown_text)
    assert message.callback_data()[:4] == [f"grant_tier:{key}"
                                           for key in config.GRANT_TIER_KEYS]
    assert main.premium_tier_pending[main.OWNER_ID]["user_id"] == 1001
    assert db.users[1001]["is_premium"] is False, "nothing is granted in step 1"


async def test_addpremium_rejects_bad_arguments(db):
    message = owner_message(text="/addpremium")
    await main.addpremium_handler(None, message)
    assert "Usage" in plain(message.shown_text)

    message = owner_message(text="/addpremium notanumber")
    await main.addpremium_handler(None, message)
    assert "Invalid" in plain(message.shown_text)

    message = owner_message(text=f"/addpremium 1001 {config.GRANT_MAX_DAYS + 1}")
    await main.addpremium_handler(None, message)
    assert str(config.GRANT_MAX_DAYS) in plain(message.shown_text)

    message = owner_message(text="/addpremium 4242")
    await main.addpremium_handler(None, message)
    assert "/start" in plain(message.shown_text)
    assert main.premium_tier_pending == {}


@pytest.mark.parametrize("tier,duration,days", [
    ("public", "month", 30),
    ("models", "quarter", 90),
    ("private", "year", 365),
    ("all", "lifetime", None),
])
async def test_full_grant_flow_stores_the_tier_flags(db, tier, duration, days):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, f"grant_tier:{tier}",
                                                 FakeUser(main.OWNER_ID)))
    await main.callback_handler(None, make_query(message, f"grant_dur:{tier}:{duration}",
                                                 FakeUser(main.OWNER_ID)))

    user = db.users[1001]
    private, models = TIER_FLAGS[tier]
    assert user["is_premium"] is True
    assert user["has_private_access"] is private
    assert user["has_models_access"] is models
    assert user["premium_tier"] == tier
    assert user["premium_source"] == config.GRANT_TIERS[tier]["source"]
    if days is None:
        assert user["premium_expiry"] is None
    else:
        assert user["premium_expiry"] > dt.datetime.now()
        assert (user["premium_expiry"] - dt.datetime.now()).days in (days - 1, days)

    owner_text = plain(message.shown_text)
    assert "VIP GRANTED" in owner_text
    assert config.GRANT_TIERS[tier]["label"] in owner_text
    # The granted user is told exactly what they received.
    notices = [entry for entry in fake_bot_sent() if entry["chat_id"] == 1001]
    assert notices
    notice = plain(notices[-1]["text"])
    assert "VIP ACTIVATED" in notice
    assert config.GRANT_TIERS[tier]["label"] in notice
    if models:
        assert "/models" in notice or "C++ Turbo" in notice
    else:
        assert "Python Standard" in notice
    assert main.premium_tier_pending == {}


def fake_bot_sent():
    return main.bot.sent


async def test_models_only_grant_does_not_unlock_private_channels(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, "grant_tier:models",
                                                 FakeUser(main.OWNER_ID)))
    await main.callback_handler(None, make_query(message, "grant_dur:models:month",
                                                 FakeUser(main.OWNER_ID)))
    assert await main.models_access(1001) is True
    assert await main.private_access(1001) is False
    decision = await main.resolve_engine_for(1001, record=False)
    assert decision.has_models is True


async def test_custom_days_are_typed_then_granted(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, "grant_tier:all",
                                                 FakeUser(main.OWNER_ID)))
    await main.callback_handler(None, make_query(message, "grant_dur:all:custom",
                                                 FakeUser(main.OWNER_ID)))
    assert main.pending_action[main.OWNER_ID] == "grant_custom_days"
    assert "Custom duration" in plain(message.shown_text) or \
        "Custom duration" in plain(message.replies[-1]["text"])

    typed = FakeMessage(text="45", user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, typed)
    user = db.users[1001]
    assert user["is_premium"] is True and user["premium_tier"] == "all"
    remaining = (user["premium_expiry"] - dt.datetime.now()).days
    assert remaining in (44, 45)
    assert main.pending_action == {}


async def test_custom_days_rejects_garbage_and_keeps_the_prompt(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, "grant_tier:public",
                                                 FakeUser(main.OWNER_ID)))
    await main.callback_handler(None, make_query(message, "grant_dur:public:custom",
                                                 FakeUser(main.OWNER_ID)))

    typed = FakeMessage(text="banana", user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, typed)
    assert main.pending_action[main.OWNER_ID] == "grant_custom_days"
    assert db.users[1001]["is_premium"] is False

    typed = FakeMessage(text=str(config.GRANT_MAX_DAYS + 1), user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, typed)
    assert main.pending_action[main.OWNER_ID] == "grant_custom_days"

    typed = FakeMessage(text="12", user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, typed)
    assert db.users[1001]["is_premium"] is True
    assert main.pending_action == {}


async def test_typed_days_in_the_command_become_a_one_tap_button(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001 45")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, "grant_tier:private",
                                                 FakeUser(main.OWNER_ID)))
    assert "grant_dur:private:typed:45" in message.callback_data()
    await main.callback_handler(None, make_query(message, "grant_dur:private:typed:45",
                                                 FakeUser(main.OWNER_ID)))
    remaining = (db.users[1001]["premium_expiry"] - dt.datetime.now()).days
    assert remaining in (44, 45)


async def test_grant_back_returns_to_step_one_without_granting(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    await main.callback_handler(None, make_query(message, "grant_tier:all",
                                                 FakeUser(main.OWNER_ID)))
    await main.callback_handler(None, make_query(message, "grant_back:all",
                                                 FakeUser(main.OWNER_ID)))
    assert "Step 1 of 2" in plain(message.shown_text)
    assert db.users[1001]["is_premium"] is False


async def test_grant_callbacks_are_owner_only(db):
    await db.add_user(1001, "Tester")
    db.admins.add(2002)
    message = FakeMessage(text="/addpremium 1001", user=FakeUser(2002))
    query = make_query(message, "grant_tier:all", FakeUser(2002))
    await main.callback_handler(None, query)
    assert db.users[1001]["is_premium"] is False
    assert "Owner" in plain(" ".join(query.answer.texts))


async def test_stale_grant_callback_is_refused(db):
    message = owner_message(text="/addpremium 1001")
    query = make_query(message, "grant_dur:all:month", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query)
    assert "expired" in plain(" ".join(query.answer.texts)).lower()


async def test_unknown_tier_is_reported_not_guessed(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/addpremium 1001")
    await main.addpremium_handler(None, message)
    query = make_query(message, "grant_tier:supervip", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query)
    assert db.users[1001]["is_premium"] is False
    assert "Unknown tier" in plain(" ".join(query.answer.texts)) or \
        "Unknown" in plain(message.shown_text)


async def test_removepremium_clears_every_flag(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, None, tier="all")
    assert await main.models_access(1001) is True
    message = owner_message(text="/removepremium 1001")
    await main.removepremium_handler(None, message)
    user = db.users[1001]
    assert user["is_premium"] is False
    assert user["has_models_access"] is False
    assert user["has_private_access"] is False
    assert user["premium_tier"] is None
    assert "VIP REVOKED" in plain(message.shown_text)
    assert await main.models_access(1001) is False


# --------------------------------------------------------------------------- #
#  5. /models and /engine — the user switcher
# --------------------------------------------------------------------------- #

async def test_models_shows_the_upsell_to_a_free_user(db):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    text = plain(message.shown_text)
    assert "C++ TURBO ENGINE" in text
    assert f"{config.RUPEE}149" in text
    assert "engine_set:cpp" not in message.callback_data()
    assert "premium_plans" in message.callback_data()
    assert "models_info" in message.callback_data()


async def test_engine_is_an_alias_of_models(db):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="/engine")
    await main.models_handler(None, message)
    assert "C++ TURBO ENGINE" in plain(message.shown_text)


async def test_models_shows_the_switcher_to_an_authorised_user(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    text = plain(message.shown_text)
    assert "ENGINE SWITCHER" in text
    labels = [plain(label) for label in message.button_texts()]
    assert any("Python Standard" in label for label in labels)
    assert any("C++ Turbo" in label for label in labels)
    assert "engine_set:python" in message.callback_data()
    assert "engine_set:cpp" in message.callback_data()


async def test_switching_persists_the_preference_and_applies_everywhere(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="all")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    await main.callback_handler(None, make_query(message, "engine_set:cpp"))

    assert await db.get_user_engine(1001) == CPP
    assert "Your Choice" in plain(message.shown_text)
    assert "✅" in message.button_texts()[1] or \
        "✅" in plain(message.button("engine_set:cpp").text)
    # Private-chat extraction and the dump-channel batch read the same value.
    private = await main.resolve_engine_for(1001, record=False)
    assert private.engine == CPP and private.reason == engines.REASON_USER_CHOICE

    await main.callback_handler(None, make_query(message, "engine_set:python"))
    assert await db.get_user_engine(1001) == PYTHON
    assert (await main.resolve_engine_for(1001, record=False)).engine == PYTHON


async def test_switcher_is_refused_once_the_permission_is_revoked(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    await db.remove_premium(1001)
    query = make_query(message, "engine_set:cpp")
    await main.callback_handler(None, query)
    assert await db.get_user_engine(1001) is None
    assert "paid add-on" in plain(" ".join(query.answer.texts))
    assert "C++ TURBO ENGINE" in plain(message.shown_text)


async def test_switcher_reports_the_global_cpp_lock(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    await db.set_engine_mode("lock_cpp")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    text = plain(message.shown_text)
    assert "Global Lock" in text
    assert "engine_set:cpp" not in message.callback_data()
    assert "global lock" in text


async def test_switcher_survives_the_python_lock_for_models_holders(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    await db.set_engine_mode("lock_python")
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    assert "engine_set:cpp" in message.callback_data()
    await main.callback_handler(None, make_query(message, "engine_set:cpp"))
    decision = await main.resolve_engine_for(1001, record=False)
    assert decision.engine == CPP
    assert decision.reason == engines.REASON_MODELS_LOCKED


async def test_switcher_shows_live_traffic(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    main.ENGINE_CONTROLLER.monitor.peak_threshold = 1
    main.ENGINE_CONTROLLER.monitor.enter()
    main.ENGINE_CONTROLLER.monitor.enter()
    message = FakeMessage(text="/models")
    await main.models_handler(None, message)
    text = plain(message.shown_text)
    assert "2 concurrent" in text
    assert "peak above 1" in text
    assert "above the autoscaler threshold" in text


def test_models_switcher_keyboard_marks_the_active_engine():
    buttons = flat(ui.models_switcher_keyboard(CPP))
    by_data = {b.callback_data: b for b in buttons}
    assert "✅" in plain(by_data["engine_set:cpp"].text)
    assert "✅" not in plain(by_data["engine_set:python"].text)
    if ui.styles_enabled():
        assert by_data["engine_set:cpp"].style == ui.BUTTON_SUCCESS
        assert by_data["engine_set:python"].style == ui.BUTTON_PRIMARY
    # With the choice fixed there are no engine buttons at all.
    fixed = [b.callback_data for b in flat(ui.models_switcher_keyboard(CPP,
                                                                      can_switch=False))]
    assert "engine_set:cpp" not in fixed and "models_info" in fixed


# --------------------------------------------------------------------------- #
#  6. /setengine — the owner's global engine controller
# --------------------------------------------------------------------------- #

async def test_setengine_shows_the_controller_panel(db):
    message = owner_message(text="/setengine")
    await main.setengine_handler(None, message)
    text = plain(message.shown_text)
    assert "GLOBAL ENGINE CONTROLLER" in text
    assert "Autoscaler" in text and "running" in text
    assert "Peak threshold" in text
    data = message.callback_data()
    assert "engine_mode:auto" in data
    assert "engine_mode:lock_cpp" in data
    assert "engine_mode:lock_python" in data


async def test_setengine_accepts_short_arguments(db):
    for argument, mode in (("auto", "auto"), ("cpp", "lock_cpp"),
                           ("c++", "lock_cpp"), ("turbo", "lock_cpp"),
                           ("python", "lock_python"), ("py", "lock_python")):
        message = owner_message(text=f"/setengine {argument}")
        await main.setengine_handler(None, message)
        assert await db.get_engine_mode() == mode, argument
        assert main.ENGINE_CONTROLLER.mode == mode


async def test_setengine_rejects_an_unknown_argument(db):
    await db.set_engine_mode("auto")
    message = owner_message(text="/setengine quantum")
    await main.setengine_handler(None, message)
    assert "Unknown engine mode" in plain(message.shown_text)
    assert await db.get_engine_mode() == "auto"


async def test_setengine_lock_cpp_routes_everyone_and_pauses_the_scaler(db):
    await db.add_user(1001, "Tester")
    message = owner_message(text="/setengine")
    await main.setengine_handler(None, message)
    await main.callback_handler(None, make_query(message, "engine_mode:lock_cpp",
                                                 FakeUser(main.OWNER_ID)))
    assert await db.get_engine_mode() == "lock_cpp"
    assert main.ENGINE_CONTROLLER.mode == "lock_cpp"
    assert main.ENGINE_CONTROLLER.autoscaler_active() is False
    assert "Engine mode updated" in plain(message.shown_text)

    # A free user with no preference is forced onto Turbo.
    for _ in range(main.ENGINE_CONTROLLER.monitor.peak_threshold + 2):
        main.ENGINE_CONTROLLER.monitor.enter()
    decision = await main.resolve_engine_for(1001)
    assert decision.engine == CPP
    assert decision.badge == engines.BADGE_GLOBAL_LOCK


async def test_setengine_lock_python_turns_the_scaler_off(db):
    await db.add_user(1001, "Tester")
    await db.add_premium(1001, 30, tier="models")
    await db.set_user_engine(1001, CPP)
    message = owner_message(text="/setengine python")
    await main.setengine_handler(None, message)
    assert main.ENGINE_CONTROLLER.autoscaler_active() is False

    for _ in range(main.ENGINE_CONTROLLER.monitor.peak_threshold + 2):
        main.ENGINE_CONTROLLER.monitor.enter()
    free = await main.resolve_engine_for(2002)
    assert free.engine == PYTHON, "free users are locked to Python"
    vip = await main.resolve_engine_for(1001)
    assert vip.engine == CPP, "a models holder keeps the manual /models toggle"


async def test_setengine_auto_restores_the_scaler(db):
    message = owner_message(text="/setengine lock_cpp")
    await main.setengine_handler(None, message)
    assert main.ENGINE_CONTROLLER.autoscaler_active() is False
    message = owner_message(text="/setengine auto")
    await main.setengine_handler(None, message)
    assert main.ENGINE_CONTROLLER.autoscaler_active() is True
    assert "Auto" in plain(message.shown_text)


async def test_engine_mode_callback_is_owner_only(db):
    db.admins.add(2002)
    message = FakeMessage(text="/setengine", user=FakeUser(2002))
    query = make_query(message, "engine_mode:lock_cpp", FakeUser(2002))
    await main.callback_handler(None, query)
    assert await db.get_engine_mode() == "auto"
    assert "Owner only" in plain(" ".join(query.answer.texts))


async def test_admin_may_open_the_controller_but_not_lock_it(db):
    db.admins.add(2002)
    message = FakeMessage(text="/admin", user=FakeUser(2002))
    query = make_query(message, "cmd_setengine", FakeUser(2002))
    await main.callback_handler(None, query)
    assert "GLOBAL ENGINE CONTROLLER" in plain(message.shown_text)


async def test_controller_screen_survives_a_database_write_failure(db, monkeypatch):
    async def broken(mode):
        raise RuntimeError("mongo is down")

    monkeypatch.setattr(main, "set_engine_mode", broken)
    message = owner_message(text="/setengine cpp")
    await main.setengine_handler(None, message)
    assert "Could not save the engine mode" in plain(message.shown_text)
    assert main.ENGINE_CONTROLLER.mode == "auto", "nothing is applied on failure"


def test_engine_controller_text_explains_all_three_modes():
    text = ui.engine_controller_text("auto", {
        "active": 3, "threshold": 8, "peak": False, "peak_active": 12,
        "peak_events": 2, "routed": {PYTHON: 40, CPP: 7}, "autoscaler": True,
    })
    assert "Auto (Dynamic Autoscaler)" in text
    assert "Lock to C++ Turbo" in text
    assert "Lock to Python" in text
    assert "3 concurrent" in text and "🟢 normal" in text
    assert "12 concurrent" in text and "2 spike(s)" in text
    assert "Routed to Python:** 40" in text
    assert "Routed to C++ Turbo:** 7" in text
    assert "running" in text

    locked = ui.engine_controller_text("lock_cpp", {"autoscaler": False, "peak": True})
    assert "paused" in locked and "⚡ PEAK" in locked


# --------------------------------------------------------------------------- #
#  7. /mychannels — the user channel dashboard
# --------------------------------------------------------------------------- #

async def test_mychannels_empty_state_offers_to_connect(db):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    text = plain(message.shown_text)
    assert "MY CHANNELS" in text
    assert "not connected a dump channel" in text
    assert "cmd_setchat" in message.callback_data()
    assert "mych_test" not in "".join(message.callback_data())


async def test_mychannels_lists_title_id_rights_and_file_counter(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump", "mydump")
    await db.increment_channel_files(-100777, 7)
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)

    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    text = plain(message.shown_text)
    assert "My Dump" in text
    assert "-100777" in text
    assert "@mydump" in text
    assert "Files extracted here: **7**" in text
    assert "Active Engine" in text
    data = message.callback_data()
    assert "mych_test:-100777" in data
    assert "mych_verify:-100777" in data
    assert "mych_del:-100777" in data
    assert "cmd_setchat" in data


async def test_mychannels_reports_missing_posting_rights(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=False)

    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    query = make_query(message, "mych_test:-100777")
    await main.callback_handler(None, query)
    text = plain(message.shown_text)
    assert "Permissions problem" in text
    assert "Post Messages" in text
    assert "Re-verify Admin" in text


async def test_mychannels_test_permissions_succeeds(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)

    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    query = make_query(message, "mych_test:-100777")
    await main.callback_handler(None, query)
    assert "Permissions OK" in plain(message.shown_text)
    assert "Checking bot permissions" in plain(" ".join(query.answer.texts))


async def test_mychannels_reports_a_plain_member(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(ChatMemberStatus.MEMBER)
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    await main.callback_handler(None, make_query(message, "mych_test:-100777"))
    assert "not an admin" in plain(message.shown_text)


async def test_mychannels_reverify_refreshes_the_stored_title(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "Old Name")
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)
    fake_bot.chats[-100777] = SimpleNamespace(id=-100777, title="Renamed Dump",
                                              username="renamed", type="channel")
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    await main.callback_handler(None, make_query(message, "mych_verify:-100777"))
    entry = await db.get_user_chat(1001)
    assert entry["title"] == "Renamed Dump"
    assert entry["username"] == "renamed"


async def test_mychannels_reverify_keeps_the_old_title_when_rights_are_missing(
        db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "Old Name")
    fake_bot.members[(-100777, FAKE_BOT_ID)] = make_member(ChatMemberStatus.MEMBER)
    fake_bot.chats[-100777] = SimpleNamespace(id=-100777, title="Renamed Dump",
                                              username=None, type="channel")
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    await main.callback_handler(None, make_query(message, "mych_verify:-100777"))
    assert (await db.get_user_chat(1001))["title"] == "Old Name"


async def test_mychannels_disconnect_clears_the_channel(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    query = make_query(message, "mych_del:-100777")
    await main.callback_handler(None, query)
    assert await db.get_user_chat(1001) is None
    assert "Channel disconnected" in plain(message.shown_text)
    assert "My Dump" in plain(message.shown_text)
    assert "cmd_setchat" in message.callback_data()


async def test_mychannels_ignores_a_forged_channel_id(db, fake_bot):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    message = FakeMessage(text="/mychannels")
    await main.mychannels_handler(None, message)
    query = make_query(message, "mych_del:-100999")
    await main.callback_handler(None, query)
    assert await db.get_user_chat(1001) is not None, "another user's chat is untouched"
    assert "no longer connected" in plain(" ".join(query.answer.texts))


async def test_mychandles_rejects_a_malformed_callback(db):
    await db.add_user(1001, "Tester")
    await db.set_user_chat(1001, -100777, "My Dump")
    message = FakeMessage(text="/mychannels")
    query = make_query(message, "mych_test:notanumber")
    await main.callback_handler(None, query)
    assert "out of date" in plain(" ".join(query.answer.texts))
    assert await db.get_user_chat(1001) is not None


async def test_mychannels_is_reachable_from_the_main_menu(db):
    await db.add_user(1001, "Tester")
    message = FakeMessage(text="/start")
    await main.start_handler(None, message)
    assert "cmd_mychannels" in message.callback_data()
    await main.callback_handler(None, make_query(message, "cmd_mychannels"))
    assert "MY CHANNELS" in plain(message.shown_text)


def test_mychannels_text_renders_every_rights_state():
    entry = {"chat_id": -100777, "title": "Dump", "username": "dump"}
    assert "Not checked yet" in ui.mychannels_text(entry)
    assert "Admin with posting rights" in ui.mychannels_text(entry, admin_ok=True)
    assert "not an admin" in ui.mychannels_text(entry, admin_ok=False,
                                                admin_reason="not_admin")
    assert "Post Messages" in ui.mychannels_text(entry, admin_ok=False,
                                                 admin_reason="no_post_rights")
    assert "did not answer" in ui.mychannels_text(entry, admin_ok=False,
                                                  admin_reason="error")
    assert "Channel -100777" in ui.mychannels_text({"chat_id": -100777})


# --------------------------------------------------------------------------- #
#  8. /stats — global and engine analytics
# --------------------------------------------------------------------------- #

async def test_stats_includes_the_engine_block(db):
    await db.add_user(1001, "Tester")
    await db.add_user(2002, "Other")
    await db.add_premium(2002, 30, tier="models")
    await db.record_engine_use(CPP, 3)
    main.ENGINE_CONTROLLER.monitor.record(engines.resolve_engine("lock_cpp"))

    message = owner_message(text="/stats")
    await main.stats_handler(None, message)
    text = plain(message.shown_text)
    assert "BOT STATISTICS" in text
    assert "ENGINE ANALYTICS" in text
    assert "C++ Turbo models: `1`" in text
    assert "Private channels: `0`" in text
    assert "Routed all time" in text and "3" in text
    assert "Controller mode" in text


def test_engine_analytics_text_computes_the_turbo_share():
    text = ui.engine_analytics_text({
        "mode": "auto", "autoscaler": True, "active": 2, "threshold": 8,
        "peak_active": 9, "peak_events": 1,
        "routed": {PYTHON: 30, CPP: 10},
        "stored": {PYTHON: 100, CPP: 50},
    })
    assert "C++ Turbo share: 25.0% of 40 extractions" in text
    assert "running" in text and "9 concurrent" in text
    assert "Python Standard: 100" in text
    assert "/setengine" in text


def test_engine_analytics_text_handles_an_empty_snapshot():
    text = ui.engine_analytics_text(None)
    assert "share" not in text
    assert "In flight now:** 0 concurrent" in text


# --------------------------------------------------------------------------- #
#  9. The redesigned /admin panel
# --------------------------------------------------------------------------- #

ADMIN_PAIRS = [
    ("📢", "/setfsub"), ("📋", "/fsublist"), ("🗑️", "/delfsub"),
    ("⚙️", "/setchat"), ("🧠", "/setengine"), ("💎", "/addpremium"),
    ("❌", "/removepremium"), ("📊", "/stats"), ("📢", "/broadcast"),
    ("🚫", "/ban & /unban"), ("💳", "/payments"), ("🛠️", "/maintenance"),
]


def test_admin_panel_lists_the_twelve_requested_command_pairs():
    lines = [line for line in ui.admin_featured_text().split("\n") if line.strip()]
    assert len(lines) == 12
    for line, (icon, commands) in zip(lines, ADMIN_PAIRS):
        assert line.startswith(icon), line
        assert commands in line, line
        assert "—" in line, "each pair carries a descriptive English label"
        description = line.split("—", 1)[1].strip()
        assert description and description.isascii()


def test_every_featured_command_is_described_in_plain_english():
    for group in ui.ADMIN_FEATURED_PAIRS:
        for command in group:
            label = ui.admin_command_label(command)
            assert label and label.isascii()
            assert len(label.split()) >= 2, f"{command} needs a descriptive label"
            assert command in main.ADMIN_PANEL_COMMANDS or command in main.COMMAND_NAMES


def test_setengine_and_addpremium_are_in_the_admin_panel(db):
    assert "setengine" in main.ADMIN_PANEL_COMMANDS
    assert "addpremium" in main.ADMIN_PANEL_COMMANDS
    assert "setengine" in main.COMMAND_NAMES
    assert "models" in main.COMMAND_NAMES
    assert "mychannels" in main.COMMAND_NAMES
    panel = "\n".join(main.admin_panel_text(page)
                       for page in range(len(main.ADMIN_PAGES)))
    assert "/setengine" in panel and "/addpremium" in panel
    assert "🧠 Engine & Channels" in panel


async def test_admin_panel_buttons_reach_the_new_screens(db):
    message = owner_message(text="/admin")
    await main.admin_handler(None, message)
    await main.callback_handler(None, make_query(message, "admin:setengine",
                                                 FakeUser(main.OWNER_ID)))
    assert "GLOBAL ENGINE CONTROLLER" in plain(message.shown_text)

    await db.add_user(1001, "Tester")
    message = owner_message(text="/admin")
    await main.admin_handler(None, message)
    await main.callback_handler(None, make_query(message, "admin:addpremium",
                                                 FakeUser(main.OWNER_ID)))
    assert "addpremium" in plain(message.shown_text).lower()


def test_admin_help_mentions_the_new_commands():
    text = main.admin_help_text()
    for command in ("setengine", "addpremium", "removepremium", "stats", "payments",
                    "maintenance", "setfsub", "fsublist", "delfsub", "setchat",
                    "broadcast"):
        assert f"/{command}" in text, command


# --------------------------------------------------------------------------- #
#  10. Standing constraints: English copy, mobile budget, ASCII callbacks
# --------------------------------------------------------------------------- #

NEW_KEYBOARDS = [
    ("start", lambda: ui.start_keyboard()),
    ("start_admin", lambda: ui.start_keyboard(show_admin=True)),
    ("models_switcher", lambda: ui.models_switcher_keyboard(CPP)),
    ("models_switcher_fixed", lambda: ui.models_switcher_keyboard(None,
                                                                  can_switch=False)),
    ("models_upsell", lambda: ui.models_upsell_keyboard()),
    ("models_architecture", lambda: ui.models_architecture_keyboard(CPP,
                                                                    has_models=True)),
    ("engine_controller", lambda: ui.engine_controller_keyboard("auto")),
    ("grant_tier", lambda: ui.grant_tier_keyboard()),
    ("grant_duration", lambda: ui.grant_duration_keyboard("all", 45)),
    ("mychannels", lambda: ui.mychannels_keyboard(-100777)),
    ("mychannels_empty", lambda: ui.mychannels_keyboard(None, connected=False)),
    ("plans", lambda: ui.plans_keyboard()),
    ("payment", lambda: ui.payment_keyboard("tok")),
    ("payment_review", lambda: ui.payment_review_keyboard(7, "month", turbo=True)),
]


@pytest.mark.parametrize("name,build", NEW_KEYBOARDS, ids=[n for n, _ in NEW_KEYBOARDS])
def test_mobile_budget_holds_for_every_new_keyboard(name, build):
    rows = build().inline_keyboard
    assert 1 <= len(rows) <= 7, f"{name}: {len(rows)} rows"
    for row in rows:
        assert 1 <= len(row) <= 2, f"{name}: row of {len(row)}"
        for button in row:
            label = plain(button.text)
            assert len(label) <= 28, f"{name}: {label!r} is {len(label)} chars"


@pytest.mark.parametrize("name,build", NEW_KEYBOARDS, ids=[n for n, _ in NEW_KEYBOARDS])
def test_callback_data_is_ascii_and_links_only_live_in_url_buttons(name, build):
    for button in flat(build()):
        if button.callback_data is not None:
            assert button.callback_data.isascii(), button.callback_data
            assert button.callback_data == button.callback_data.strip()
            assert button.url is None
        if button.url is not None:
            assert button.url.startswith("https://"), button.url
            assert button.callback_data is None


NEW_SCREENS = [
    ("models_upsell", lambda: ui.models_upsell_text()),
    ("models_architecture", lambda: ui.models_architecture_text(CPP)),
    ("models_switcher", lambda: ui.models_switcher_text(CPP, "auto", concurrency=2,
                                                        peak=False, threshold=8)),
    ("models_locked", lambda: ui.models_locked_text("lock_cpp")),
    ("engine_controller", lambda: ui.engine_controller_text("auto", {})),
    ("engine_mode_set", lambda: ui.engine_mode_set_text("lock_cpp")),
    ("grant_tier", lambda: ui.grant_tier_text(1001, "Tester", 45)),
    ("grant_duration", lambda: ui.grant_duration_text(1001, "all", "Tester", 45)),
    ("grant_custom", lambda: ui.grant_custom_days_text(1001, "all")),
    ("grant_done", lambda: ui.grant_done_text(1001, "all", 30, "Tester")),
    ("grant_activated", lambda: ui.grant_activated_user_text("all", 30, "Tester")),
    ("grant_revoked", lambda: ui.grant_revoked_text(1001, "Tester")),
    ("mychannels_empty", lambda: ui.mychannels_empty_text()),
    ("mychannels", lambda: ui.mychannels_text({"chat_id": -100777, "title": "Dump"},
                                              admin_ok=True, files=3, engine=CPP)),
    ("mychannels_test", lambda: ui.mychannels_test_text("Dump", True)),
    ("mychannels_disconnected", lambda: ui.mychannels_disconnected_text("Dump")),
    ("stats", lambda: ui.stats_text({"total": 1}, 0, ui.engine_analytics_text({}))),
    ("engine_analytics", lambda: ui.engine_analytics_text({})),
    ("plans", lambda: ui.plans_text()),
    ("payment", lambda: ui.payment_text(config.PREMIUM_PLANS["month"], turbo=True)),
    ("admin_featured", lambda: ui.admin_featured_text()),
    ("help", lambda: ui.help_text()),
    ("hud", lambda: ui.telemetry_hud(CPP, 68)),
]

#: Devanagari block — nothing in the new copy may use it.
DEVANAGARI = tuple(chr(code) for code in range(0x0900, 0x0980))


@pytest.mark.parametrize("name,build", NEW_SCREENS, ids=[n for n, _ in NEW_SCREENS])
def test_new_copy_is_english_only_and_link_free(name, build):
    text = build()
    assert text.strip(), f"{name} rendered nothing"
    assert not any(char in text for char in DEVANAGARI), f"{name} contains Devanagari"
    assert "http://" not in text and "https://" not in text, \
        f"{name} prints a raw link — links belong in url= buttons"
    #: An inline-code span documents a link *format* (`t.me/ch/1-20`); it is
    #: not a clickable link, so only the prose is checked.
    prose = re.sub(r"`[^`]*`", "", text)
    assert "t.me/" not in prose.replace(f"t.me/{config.BOT_USERNAME}", ""), \
        f"{name} prints a Telegram link outside a button"


def test_help_menu_documents_the_new_commands():
    text = ui.help_text()
    assert "/models" in text
    assert "/mychannels" in text


# --------------------------------------------------------------------------- #
#  11. The real database layer (mongomock) for the new fields
# --------------------------------------------------------------------------- #

@pytest.fixture
def store(monkeypatch):
    """The genuine ``database`` module against an in-memory Mongo."""
    mongo = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(database, "db", mongo)
    for name in ("users_col", "config_col", "downloads_col", "channel_files_col",
                 "engine_stats_col", "payments_col", "fsub_col"):
        if hasattr(database, name):
            monkeypatch.setattr(database, name, getattr(mongo, name))
    return mongo


async def test_database_round_trips_the_new_user_fields(store):
    await database.add_user(1001, "Tester", "tester")
    await database.set_models_access(1001, True)
    await database.set_private_access(1001, True)
    await database.set_user_engine(1001, "cpp")
    assert await database.has_models_access(1001) is True
    assert await database.has_private_access(1001) is True
    assert await database.get_user_engine(1001) == "cpp"
    assert await database.get_engine_preference(1001) == "cpp"
    # An unknown engine id is folded onto a known one, never stored raw.
    await database.set_user_engine(1001, "quantum")
    assert await database.get_user_engine(1001) in config.ENGINES


async def test_database_add_premium_applies_the_tier_flags(store):
    await database.add_user(1001, "Tester", "tester")
    await database.add_premium(1001, 30, tier="models")
    row = await database.get_user(1001)
    assert row["is_premium"] is True
    assert row["has_models_access"] is True
    assert row["has_private_access"] is False
    assert row["premium_source"] == config.PREMIUM_SOURCE_MODELS
    assert row["premium_tier"] == "models"
    assert row["premium_expiry"] is not None

    await database.add_premium(1001, None, tier="all")
    row = await database.get_user(1001)
    assert row["has_private_access"] is True and row["has_models_access"] is True
    assert row["premium_expiry"] is None, "days=None means lifetime"


async def test_database_remove_premium_clears_the_flags(store):
    await database.add_user(1001, "Tester", "tester")
    await database.add_premium(1001, 30, tier="all")
    await database.remove_premium(1001)
    row = await database.get_user(1001)
    assert row["is_premium"] is False
    assert row["has_models_access"] is False
    assert row["has_private_access"] is False
    assert await database.has_models_access(1001) is False
    assert await database.get_user_engine(1001) is None or \
        await database.has_models_access(1001) is False


async def test_database_persists_the_engine_mode(store):
    assert await database.get_engine_mode() == config.DEFAULT_ENGINE_MODE
    await database.set_engine_mode("lock_cpp")
    assert await database.get_engine_mode() == "lock_cpp"
    await database.set_engine_mode("nonsense")
    assert await database.get_engine_mode() == config.DEFAULT_ENGINE_MODE


async def test_database_counts_engine_use_and_channel_files(store):
    await database.record_engine_use("cpp")
    await database.record_engine_use("cpp", 2)
    await database.record_engine_use("python")
    stats = await database.get_engine_stats()
    assert stats == {PYTHON: 1, CPP: 3}

    await database.increment_channel_files(-100777)
    await database.increment_channel_files(-100777, 4)
    await database.increment_channel_files(-100888)
    assert await database.get_channel_files(-100777) == 5
    assert await database.get_channel_files(-100888) == 1
    assert await database.get_channel_files(-100999) == 0
    await database.set_channel_files(-100777, 0)
    assert await database.get_channel_files(-100777) == 0


async def test_database_stats_count_the_feature_grants(store):
    await database.add_user(1001, "A", "a")
    await database.add_user(1002, "B", "b")
    await database.add_premium(1001, 30, tier="all")
    await database.add_premium(1002, 30, tier="public")
    stats = await database.get_bot_stats()
    assert stats["models_access"] == 1
    assert stats["private_access"] == 1
    assert stats["premium"] == 2


async def test_legacy_documents_keep_working_without_the_new_flags(store):
    """A user written before this change has no flags at all."""
    await database.add_user(1001, "Tester", "tester")
    await database.users_col.update_one({"user_id": 1001}, {"$unset": {
        "has_private_access": "", "has_models_access": "", "engine_preference": "",
        "premium_tier": ""}})
    await database.users_col.update_one({"user_id": 1001}, {"$set": {
        "is_premium": True, "premium_source": config.PREMIUM_SOURCE_MANUAL,
        "premium_expiry": dt.datetime.now() + dt.timedelta(days=10)}})
    # main.private_access falls back to the legacy source when no flag exists.
    assert await main.private_access(1001) is True
    assert await main.models_access(1001) is False
