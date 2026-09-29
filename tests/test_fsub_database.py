"""Force-sub list storage: real Mongo semantics, no FakeDB."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

import database


@pytest.fixture
def store(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(database, "users_col", db.users)
    monkeypatch.setattr(database, "config_col", db.config)
    return db


def item(**overrides):
    entry = {"chat_id": -100555, "title": "My Channel", "username": "mychannel",
             "invite_link": None, "button_text": "✅ Join My Channel",
             "kind": "channel", "auto_approve": False}
    entry.update(overrides)
    return entry


@pytest.mark.asyncio
async def test_add_list_update_and_remove_entries(store):
    assert await database.add_fsub_item(item()) == 1
    assert await database.add_fsub_item(item(chat_id=-100556, title="Chat Group",
                                             username="group", kind="group",
                                             button_text="Join Chat")) == 2
    items = await database.get_fsub_list()
    assert [i["title"] for i in items] == ["My Channel", "Chat Group"]
    assert [i["order"] for i in items] == [0, 1]
    assert items[1]["kind"] == "group"
    assert items[1]["auto_approve"] is False

    assert await database.update_fsub_item(2, button_text="Join Group", auto_approve=True)
    items = await database.get_fsub_list()
    assert items[1]["button_text"] == "Join Group"
    assert items[1]["auto_approve"] is True
    assert not await database.update_fsub_item(9, button_text="nope")

    removed = await database.remove_fsub_item(1)
    assert removed["title"] == "My Channel"
    items = await database.get_fsub_list()
    assert [i["title"] for i in items] == ["Chat Group"]
    assert items[0]["order"] == 0                     # numbering stays contiguous
    assert await database.remove_fsub_item(7) is None


@pytest.mark.asyncio
async def test_clear_fsub_list_and_the_delete_alias(store):
    for index in range(3):
        await database.add_fsub_item(item(chat_id=-100500 - index, title=f"c{index}"))
    assert await database.clear_fsub_list() == 3
    assert await database.get_fsub_list() == []

    await database.add_fsub_item(item())
    assert await database.delete_fsub() == 1          # back-compat alias
    assert await database.get_fsub_list() == []


@pytest.mark.asyncio
async def test_legacy_single_channel_document_is_migrated(store):
    await database.config_col.update_one({"type": "fsub"},
                                         {"$set": {"channel": "@oldchannel"}}, upsert=True)

    items = await database.get_fsub_list()

    assert len(items) == 1
    assert items[0]["username"] == "oldchannel"
    assert items[0]["button_text"] == "✅ I Joined"
    assert items[0]["order"] == 0
    # the legacy document is consumed so the migration happens exactly once
    assert await database.config_col.find_one({"type": "fsub"}) is None
    assert await database.get_fsub_list() == items
    # the back-compat accessor still answers with the public handle
    assert await database.get_fsub_channel() == "@oldchannel"


@pytest.mark.asyncio
async def test_verify_label_round_trip(store):
    assert await database.get_fsub_verify_label() is None
    await database.set_fsub_verify_label("✅ Verified")
    assert await database.get_fsub_verify_label() == "✅ Verified"
    await database.set_fsub_verify_label(None)
    assert await database.get_fsub_verify_label() is None


@pytest.mark.asyncio
async def test_join_requests_are_recorded_and_updated(store):
    await database.record_join_request(-100555, 1001)
    row = await database.get_join_request(-100555, 1001)
    assert row["status"] == "pending"
    assert row["chat_id"] == -100555 and row["user_id"] == 1001

    await database.set_join_request_status(-100555, 1001, "approved")
    row = await database.get_join_request(-100555, 1001)
    assert row["status"] == "approved"

    # one row per (chat, user) pair
    await database.record_join_request(-100555, 1001, status="declined")
    assert (await database.get_join_request(-100555, 1001))["status"] == "declined"
    assert await database.get_join_request(-100556, 1001) is None
