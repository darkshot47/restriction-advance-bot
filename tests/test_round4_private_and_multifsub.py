"""Private channels, multi force-sub, custom labels and join requests.

Everything here uses **real** Kurigram types (``ChatMember``,
``ChatAdministratorRights``, ``ChatJoiner``, raw MTProto objects) — the
``SimpleNamespace`` fakes of the past hid a production bug where the admin
check read a ``can_post_messages`` attribute that ``ChatMember`` does not have.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram import raw
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import ChatAdministratorRights, ChatMember

import main
import ui
from conftest import (FAKE_BOT_ID, FAKE_PRIVATE_CHAT_ID, FakeMessage, FakeUser,
                      make_joiner, make_member, make_query, sc)


def fsub_item(**overrides):
    """A force-sub entry the way ``database.normalize_fsub_item`` stores it."""
    item = {"chat_id": -100555, "title": "My Channel", "username": "mychannel",
            "invite_link": None, "button_text": "✅ Join My Channel",
            "kind": "channel", "auto_approve": False, "order": 0}
    item.update(overrides)
    return item


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def url_buttons(markup):
    return [b for b in flat(markup) if b.url]


# --------------------------------------------------------------------------- #
#  TASK 1 — the admin check reads privileges, not a missing attribute
# --------------------------------------------------------------------------- #

def test_chat_member_has_no_can_post_messages_attribute():
    """Guard: nobody may "simplify" the fix back to the broken attribute."""
    member = ChatMember(status=ChatMemberStatus.ADMINISTRATOR,
                        privileges=ChatAdministratorRights(can_post_messages=True))
    assert hasattr(member, "can_post_messages") is False
    assert hasattr(member, "can_send_messages") is False
    assert member.privileges.can_post_messages is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status,can_post,expected,reason", [
    (ChatMemberStatus.ADMINISTRATOR, True, True, "ok"),
    (ChatMemberStatus.ADMINISTRATOR, False, False, "no_post_rights"),
    (ChatMemberStatus.MEMBER, None, False, "not_admin"),
    (ChatMemberStatus.OWNER, None, True, "ok"),
    (ChatMemberStatus.ADMINISTRATOR, None, True, "ok"),   # privileges is None
])
async def test_admin_check_with_real_chat_members(db, fake_bot, status, can_post, expected, reason):
    privileges = None
    if can_post is not None or status == ChatMemberStatus.ADMINISTRATOR:
        privileges = ChatAdministratorRights(can_post_messages=bool(can_post),
                                             can_manage_chat=True)
    if status == ChatMemberStatus.ADMINISTRATOR and can_post is None:
        privileges = None
    fake_bot.members[FAKE_BOT_ID] = make_member(status, privileges=privileges)

    ok, why = await main.describe_channel_admin(-100123)

    assert ok is expected
    assert why == reason
    assert await main.verify_channel_admin(-100123) is expected


@pytest.mark.asyncio
async def test_admin_check_reports_telegram_errors_as_error(db, fake_bot):
    async def boom(*args, **kwargs):
        raise ChatAdminRequired("no access")

    fake_bot.get_chat_member = boom
    ok, reason = await main.describe_channel_admin(-100123)
    assert (ok, reason) == (False, "error")


@pytest.mark.asyncio
async def test_admin_failure_copy_matches_the_reason():
    assert sc("Admin check failed") in sc(ui.setchat_admin_failed_text())
    assert sc("Post Messages") in sc(ui.setchat_admin_failed_text("no_post_rights"))
    assert sc("administrator बनाओ") in sc(ui.setchat_admin_failed_text("not_admin"))
    assert sc("जवाब नहीं दिया") in sc(ui.setchat_admin_failed_text("error"))


# --------------------------------------------------------------------------- #
#  TASK 2 — /setchat accepts private invite links, groups and bare message ids
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_setchat_with_a_private_invite_link(db, fake_bot, press):
    fake_bot.invites["AbCdEf"] = "join"
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    fake_bot.messages[15] = SimpleNamespace(empty=False, id=15)

    message = FakeMessage(text="/setchat t.me/+AbCdEf", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    pending = main.setchat_pending[1001]
    assert pending["chat_id"] == FAKE_PRIVATE_CHAT_ID
    assert pending["username"] is None            # private chat: no public handle
    assert pending["step"] == "await_check"
    assert fake_bot.joined_chats == ["t.me/+AbCdEf"]

    await press(message, "setchat:check")
    assert sc("Admin verified") in message.shown_text
    assert main.setchat_pending[1001]["step"] == "await_sample"

    # a bare message number is accepted while the wizard waits for the sample
    sample = FakeMessage(text="15", user=FakeUser(1001))
    await main.text_handler(None, sample)
    assert sc("Channel dump enabled") in sample.shown_text
    assert await db.get_user_chat(1001) == {
        "chat_id": FAKE_PRIVATE_CHAT_ID, "title": "Private Channel", "username": None,
    }


@pytest.mark.asyncio
async def test_setchat_already_inside_the_private_channel(db, fake_bot, press):
    fake_bot.invites["Already1"] = "already"
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    message = FakeMessage(text="/setchat t.me/joinchat/Already1", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    assert fake_bot.joined_chats == []            # no unnecessary join attempt
    assert main.setchat_pending[1001]["chat_id"] == FAKE_PRIVATE_CHAT_ID
    assert main.setchat_pending[1001]["title"] == "Private Channel"


@pytest.mark.asyncio
async def test_setchat_expired_and_invalid_invite_links(db, fake_bot):
    for behaviour, expected in (("expired", "expire"), ("invalid", "सही नहीं")):
        fake_bot.invites["Gone123"] = behaviour
        message = FakeMessage(text="/setchat t.me/+Gone123", user=FakeUser(1001))
        await main.setchat_handler(None, message)
        assert sc(expected) in message.shown_text, behaviour
        assert 1001 not in main.setchat_pending
        assert main.pending_action[1001] == "setchat"   # wizard stays on step 1


@pytest.mark.asyncio
async def test_setchat_approval_only_invite_keeps_the_wizard_alive(db, fake_bot, press):
    """``InviteRequestSent``: nothing is stored, the retry path still works."""
    fake_bot.invites["ZzZzzz"] = "approval"
    message = FakeMessage(text="/setchat t.me/+ZzZzzz", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    assert sc("join request भेज दी") in message.shown_text
    assert sc("approve") in message.shown_text
    assert message.button("setchat:check")           # retry button is offered
    assert await db.get_user_chat(1001) is None      # nothing stored yet
    assert main.setchat_pending[1001]["chat_id"] is None

    # the owner of that chat approved us meanwhile
    fake_bot.invites["ZzZzzz"] = "already"
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    await press(message, "setchat:check")
    assert main.setchat_pending[1001]["chat_id"] == FAKE_PRIVATE_CHAT_ID
    await press(message, "setchat:check")
    assert sc("Admin verified") in message.shown_text


@pytest.mark.asyncio
async def test_setchat_accepts_a_supergroup_and_an_in_channel_command(db, fake_bot):
    fake_bot.chats[-100999] = SimpleNamespace(id=-100999, title="Movies Group",
                                              username=None, type="supergroup")
    message = FakeMessage(text="/setchat -100999", user=FakeUser(1001))
    await main.setchat_handler(None, message)
    assert main.setchat_pending[1001]["chat_id"] == -100999
    assert main.setchat_pending[1001]["title"] == "Movies Group"

    inside = FakeMessage(text="/setchat", user=FakeUser(1001))
    inside.chat = SimpleNamespace(id=-100888, title="Dump Group", username=None,
                                  type="supergroup")
    await main.setchat_handler(None, inside)
    assert main.setchat_pending[1001]["chat_id"] == -100888
    assert main.setchat_pending[1001]["username"] is None


@pytest.mark.asyncio
async def test_setchat_never_crashes_on_a_missing_title(db, fake_bot):
    fake_bot.chats[-100444] = SimpleNamespace(id=-100444, title=None, username=None,
                                              type="channel")
    message = FakeMessage(text="/setchat -100444", user=FakeUser(1001))
    await main.setchat_handler(None, message)
    assert main.setchat_pending[1001]["title"] == "Channel -100444"


@pytest.mark.asyncio
async def test_setchat_public_message_link_strips_the_message_id(db, fake_bot):
    message = FakeMessage(text="/setchat t.me/mychannel/15", user=FakeUser(1001))
    await main.setchat_handler(None, message)
    assert main.setchat_pending[1001]["chat_id"] == fake_bot.channel_id


# --------------------------------------------------------------------------- #
#  TASK 4 — join requests / approve list
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize("pending,expected", [(True, "pending"), (False, "approved")])
async def test_join_request_state_reads_the_approve_list(db, fake_bot, pending, expected):
    chat_id, user_id = -100555, 1001
    fake_bot.not_members.add((chat_id, user_id))
    fake_bot.join_requests[chat_id] = [make_joiner(user_id, pending=pending)]
    assert await main.join_request_state(chat_id, user_id) == expected


@pytest.mark.asyncio
async def test_join_request_state_membership_wins(db, fake_bot):
    chat_id, user_id = -100555, 1001
    fake_bot.members[(chat_id, user_id)] = make_member(ChatMemberStatus.MEMBER)
    fake_bot.join_requests[chat_id] = [make_joiner(user_id, pending=True)]
    assert await main.join_request_state(chat_id, user_id) == "member"


@pytest.mark.asyncio
async def test_join_request_state_none_when_nothing_is_found(db, fake_bot):
    chat_id, user_id = -100555, 1001
    fake_bot.not_members.add((chat_id, user_id))
    fake_bot.join_requests[chat_id] = [make_joiner(4242, pending=True)]
    assert await main.join_request_state(chat_id, user_id) == "none"


@pytest.mark.asyncio
async def test_join_request_state_swallows_chat_admin_required(db, fake_bot):
    chat_id, user_id = -100555, 1001
    fake_bot.not_members.add((chat_id, user_id))

    async def boom(chat_id, limit=0, query=""):
        raise ChatAdminRequired("bot is not an admin there")
        yield  # pragma: no cover - makes this an async generator

    fake_bot.get_chat_join_requests = boom
    assert await main.join_request_state(chat_id, user_id) == "none"


@pytest.mark.asyncio
async def test_join_request_state_raw_fallback(db, fake_bot, monkeypatch):
    """Forks without the high-level helper still read the approve list."""
    chat_id, user_id = -100555, 1001
    fake_bot.not_members.add((chat_id, user_id))
    monkeypatch.setattr(fake_bot, "get_chat_join_requests", None)

    async def fake_invoke(query, *args, **kwargs):
        assert isinstance(query, raw.functions.messages.GetChatInviteImporters)
        return SimpleNamespace(importers=[SimpleNamespace(user_id=SimpleNamespace(user_id=user_id))])

    monkeypatch.setattr(fake_bot, "invoke", fake_invoke)
    monkeypatch.setattr(fake_bot, "resolve_peer", AsyncMock(return_value="peer"))
    assert await main.join_request_state(chat_id, user_id) == "pending"


# --------------------------------------------------------------------------- #
#  fsub:check — membership *and* join requests
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_fsub_check_auto_approves_a_pending_request(db, fake_bot, press):
    db.fsub_items = [fsub_item(invite_link="https://t.me/+secret", username=None,
                               auto_approve=True)]
    fake_bot.not_members.add((-100555, 1001))
    fake_bot.join_requests[-100555] = [make_joiner(1001, pending=True)]

    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "fsub:check")

    assert fake_bot.approved == [(-100555, 1001)]
    assert db.join_requests[(-100555, 1001)]["status"] == "approved"
    assert sc("approve हो गई") in " ".join(query.answer.texts)
    assert message.deleted is True


@pytest.mark.asyncio
async def test_fsub_check_reports_a_pending_request_without_auto_approve(db, fake_bot, press):
    db.fsub_items = [fsub_item(invite_link="https://t.me/+secret", username=None)]
    fake_bot.not_members.add((-100555, 1001))
    fake_bot.join_requests[-100555] = [make_joiner(1001, pending=True)]

    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "fsub:check")

    assert fake_bot.approved == []
    assert sc("request pending है") in " ".join(query.answer.texts)
    assert query.answer.calls[-1]["show_alert"] is True


@pytest.mark.asyncio
async def test_fsub_check_explains_the_next_step(db, fake_bot, press):
    db.fsub_items = [fsub_item()]
    fake_bot.not_members.add((-100555, 1001))

    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "fsub:check")
    assert sc("पहले Join करो") in " ".join(query.answer.texts)

    db.fsub_items = [fsub_item(invite_link="https://t.me/+secret", username=None)]
    query = await press(message, "fsub:check")
    assert sc("join request भेजो") in " ".join(query.answer.texts)


@pytest.mark.asyncio
async def test_fsub_check_verifies_every_entry_before_clearing(db, fake_bot, press):
    db.fsub_items = [fsub_item(chat_id=-100555, username="one"),
                     fsub_item(chat_id=-100556, username="two", order=1)]
    fake_bot.members[(-100555, 1001)] = make_member(ChatMemberStatus.MEMBER)
    fake_bot.not_members.add((-100556, 1001))

    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "fsub:check")

    assert message.deleted is False
    assert sc("पहले Join करो") in " ".join(query.answer.texts)

    fake_bot.not_members.discard((-100556, 1001))
    fake_bot.members[(-100556, 1001)] = make_member(ChatMemberStatus.MEMBER)
    await press(message, "fsub:check")
    assert message.deleted is True


@pytest.mark.asyncio
async def test_fsub_check_without_entries_is_a_noop(db, fake_bot, press):
    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "fsub:check")
    assert sc("कोई channel ज़रूरी नहीं") in " ".join(query.answer.texts)


# --------------------------------------------------------------------------- #
#  Incoming join requests reach the owner with owner-only buttons
# --------------------------------------------------------------------------- #

def join_request(chat_id, user_id, name="Joiner"):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id),
                           from_user=SimpleNamespace(id=user_id, first_name=name),
                           date=None, bio=None, invite_link=None, query_id=1)


@pytest.mark.asyncio
async def test_inbound_join_request_is_stored_and_auto_approved(db, fake_bot):
    db.fsub_items = [fsub_item(auto_approve=True)]
    await main.fsub_join_request_handler(None, join_request(-100555, 1001))

    assert fake_bot.approved == [(-100555, 1001)]
    assert db.join_requests[(-100555, 1001)]["status"] == "approved"
    assert [m["chat_id"] for m in fake_bot.sent] == [1001]      # the user is told
    assert sc("join request approve हो गई") in fake_bot.sent[0]["text"]


@pytest.mark.asyncio
async def test_inbound_join_request_notifies_the_owner(db, fake_bot):
    db.fsub_items = [fsub_item()]
    await db.add_user(1001, "Joiner")
    await main.fsub_join_request_handler(None, join_request(-100555, 1001))

    owner_messages = [m for m in fake_bot.sent if m["chat_id"] == main.OWNER_ID]
    assert len(owner_messages) == 1
    assert sc("Join request") in owner_messages[0]["text"]
    assert sc("Joiner") in owner_messages[0]["text"]            # name read fresh
    data = [b.callback_data for row in owner_messages[0]["reply_markup"].inline_keyboard
            for b in row]
    assert data == [f"fsub:approve:1001:-100555", f"fsub:decline:1001:-100555"]


@pytest.mark.asyncio
async def test_join_request_from_an_unknown_chat_is_ignored(db, fake_bot):
    db.fsub_items = [fsub_item(chat_id=-100555)]
    await main.fsub_join_request_handler(None, join_request(-100999, 1001))
    assert fake_bot.sent == []
    assert fake_bot.approved == []


@pytest.mark.asyncio
async def test_only_the_owner_can_review_a_join_request(db, fake_bot, press):
    db.fsub_items = [fsub_item()]
    message = FakeMessage(text="🔔 Join request", user=FakeUser(main.OWNER_ID))

    outsider = make_query(message, "fsub:approve:1001:-100555", FakeUser(4242))
    await main.callback_handler(None, outsider)
    assert outsider.answer.calls[-1]["show_alert"] is True
    assert sc("Owner only") in outsider.answer.calls[-1]["text"]
    assert fake_bot.approved == []
    assert db.join_requests == {}

    owner = make_query(message, "fsub:approve:1001:-100555", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, owner)
    assert fake_bot.approved == [(-100555, 1001)]
    assert db.join_requests[(-100555, 1001)]["status"] == "approved"
    assert sc("Approved by Owner") in " ".join(owner.answer.texts)

    decline = make_query(message, "fsub:decline:1001:-100555", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, decline)
    assert fake_bot.declined == [(-100555, 1001)]
    assert db.join_requests[(-100555, 1001)]["status"] == "declined"


# --------------------------------------------------------------------------- #
#  TASK 3 / 6 — multi force-sub with custom labels
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_fsub_keyboard_shows_every_custom_label_in_order(db):
    items = [fsub_item(chat_id=-100555, title="Announcement", username="announce",
                       button_text="📢 Join Update"),
             fsub_item(chat_id=-100556, title="Chat Group", username="chatgroup",
                       kind="group", button_text="Join Chat", order=1)]
    markup = ui.fsub_keyboard(items)

    buttons = url_buttons(markup)
    assert [b.url for b in buttons] == ["https://t.me/announce", "https://t.me/chatgroup"]
    assert [b.text for b in buttons] == [sc("📢 Join Update"), sc("Join Chat")]
    assert [b for b in flat(markup) if b.callback_data == "fsub:check"]
    # one item per row, labels stay inside the mobile budget
    assert all(len(row) == 1 for row in markup.inline_keyboard[:-1])
    assert all(len(b.text) <= 28 for b in flat(markup))


@pytest.mark.asyncio
async def test_fsub_keyboard_uses_invite_links_for_private_chats(db):
    markup = ui.fsub_keyboard([fsub_item(username=None,
                                         invite_link="https://t.me/+AbCdEf")])
    assert url_buttons(markup)[0].url == "https://t.me/+AbCdEf"


@pytest.mark.asyncio
async def test_fsub_keyboard_honours_the_global_verify_label(db):
    markup = ui.fsub_keyboard([fsub_item()], verify_label="✅ Verified")
    assert [b.text for b in flat(markup) if b.callback_data == "fsub:check"] == [sc("✅ Verified")]


@pytest.mark.asyncio
async def test_setfsub_wizard_asks_for_the_label_and_stores_it(db, fake_bot):
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    message = FakeMessage(text="/setfsub @mychannel", user=FakeUser(main.OWNER_ID))
    await main.setfsub_handler(None, message)

    assert sc("Join button पर क्या लिखा दिखे") in message.shown_text
    assert main.fsub_pending[main.OWNER_ID]["step"] == "await_label"
    assert db.fsub_items == []                     # nothing stored before the label

    label = FakeMessage(text="📢 Join Update", user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, label)

    items = await db.get_fsub_list()
    assert len(items) == 1
    assert items[0]["button_text"] == "📢 Join Update"
    assert items[0]["chat_id"] == fake_bot.channel_id
    assert items[0]["username"] == "mychannel"
    assert main.OWNER_ID not in main.fsub_pending
    assert any(sc("Force sub add हो गई") in reply["text"] for reply in label.replies)


@pytest.mark.asyncio
async def test_setfsub_default_label_when_the_owner_sends_a_dash(db, fake_bot):
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    message = FakeMessage(text="/setfsub @mychannel", user=FakeUser(main.OWNER_ID))
    await main.setfsub_handler(None, message)

    for typed in ("-", "   "):
        label = FakeMessage(text=typed, user=FakeUser(main.OWNER_ID))
        await main.text_handler(None, label)
        items = await db.get_fsub_list()
        assert items[-1]["button_text"] == ui.default_fsub_label("mychannel"), typed


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["x" * 25, "join t.me/mychannel", "join @mychannel",
                                   "line one\nline two"])
async def test_setfsub_rejects_unusable_labels(db, fake_bot, typed):
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    message = FakeMessage(text="/setfsub @mychannel", user=FakeUser(main.OWNER_ID))
    await main.setfsub_handler(None, message)

    label = FakeMessage(text=typed, user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, label)

    assert await db.get_fsub_list() == []                     # nothing stored
    assert sc("use नहीं हो सकता") in label.shown_text
    assert main.fsub_pending[main.OWNER_ID]["step"] == "await_label"   # wizard stays open


@pytest.mark.asyncio
async def test_setfsub_reports_a_truthful_admin_failure(db, fake_bot):
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=False)
    message = FakeMessage(text="/setfsub @mychannel", user=FakeUser(main.OWNER_ID))
    await main.setfsub_handler(None, message)

    assert sc("Post Messages") in message.shown_text
    assert await db.get_fsub_list() == []
    assert main.OWNER_ID not in main.fsub_pending


@pytest.mark.asyncio
async def test_fsublist_numbers_every_entry(db):
    db.fsub_items = [fsub_item(title="Announcement", button_text="📢 Join Update"),
                     fsub_item(chat_id=-100556, title="Chat Group", username="group",
                               kind="group", button_text="Join Chat", order=1)]
    message = FakeMessage(text="/fsublist", user=FakeUser(main.OWNER_ID))
    await main.fsublist_handler(None, message)

    text = message.shown_text
    assert sc("1.") in text and sc("Announcement") in text
    assert sc("📢 Join Update") in text
    assert sc("2.") in text and sc("Chat Group") in text
    assert sc("Join Chat") in text
    assert "t.me/" not in text and "http" not in text
    data = message.callback_data()
    assert "fsub_rename:1" in data and "fsub_del:2" in data and "fsub_del_all" in data


@pytest.mark.asyncio
async def test_delfsub_removes_one_entry_then_all_of_them(db, press):
    db.fsub_items = [fsub_item(title="One"), fsub_item(chat_id=-100556, title="Two", order=1)]

    message = FakeMessage(text="/delfsub 1", user=FakeUser(main.OWNER_ID))
    await main.delfsub_handler(None, message)
    items = await db.get_fsub_list()
    assert [i["title"] for i in items] == ["Two"]

    confirm = FakeMessage(text="/delfsub all", user=FakeUser(main.OWNER_ID))
    await main.delfsub_handler(None, confirm)
    assert sc("साफ") in confirm.shown_text or sc("हटा दें") in confirm.shown_text
    assert confirm.button("fsub_del_all_confirm")

    await press(confirm, "fsub_del_all_confirm")
    assert await db.get_fsub_list() == []


@pytest.mark.asyncio
async def test_delfsub_reports_an_unknown_number(db):
    db.fsub_items = [fsub_item()]
    message = FakeMessage(text="/delfsub 7", user=FakeUser(main.OWNER_ID))
    await main.delfsub_handler(None, message)
    assert sc("No entry number 7") in message.shown_text
    assert len(await db.get_fsub_list()) == 1


@pytest.mark.asyncio
async def test_fsublabel_renames_an_entry_and_the_verify_button(db):
    db.fsub_items = [fsub_item(title="One"), fsub_item(chat_id=-100556, title="Two", order=1)]

    message = FakeMessage(text="/fsublabel 2 Join Chat", user=FakeUser(main.OWNER_ID))
    await main.fsublabel_handler(None, message)
    items = await db.get_fsub_list()
    assert items[1]["button_text"] == "Join Chat"
    assert items[0]["button_text"] == "✅ Join My Channel"   # untouched

    verify = FakeMessage(text="/fsublabel verify ✅ Verified", user=FakeUser(main.OWNER_ID))
    await main.fsublabel_handler(None, verify)
    assert await db.get_fsub_verify_label() == "✅ Verified"
    assert [b.text for b in flat(ui.fsub_keyboard(items, verify_label="✅ Verified"))
            if b.callback_data == "fsub:check"] == [sc("✅ Verified")]


@pytest.mark.asyncio
async def test_rename_button_asks_for_the_new_label(db, press):
    db.fsub_items = [fsub_item(title="One")]
    message = FakeMessage(user=FakeUser(main.OWNER_ID))
    query = await press(message, "fsub_rename:1")
    assert sc("क्या लिखा दिखे") in " ".join(query.answer.texts) or message.shown_text
    assert main.fsub_pending[main.OWNER_ID] == {"step": "await_rename", "number": 1}

    typed = FakeMessage(text="Join Now", user=FakeUser(main.OWNER_ID))
    await main.text_handler(None, typed)
    assert (await db.get_fsub_list())[0]["button_text"] == "Join Now"


@pytest.mark.asyncio
async def test_fsubcheck_toggles_auto_approve(db):
    db.fsub_items = [fsub_item(title="One"), fsub_item(chat_id=-100556, title="Two", order=1)]

    message = FakeMessage(text="/fsubcheck 1 on", user=FakeUser(main.OWNER_ID))
    await main.fsubcheck_handler(None, message)
    items = await db.get_fsub_list()
    assert items[0]["auto_approve"] is True and items[1]["auto_approve"] is False

    message = FakeMessage(text="/fsubcheck all off", user=FakeUser(main.OWNER_ID))
    await main.fsubcheck_handler(None, message)
    assert all(i["auto_approve"] is False for i in await db.get_fsub_list())

    bad = FakeMessage(text="/fsubcheck 9 on", user=FakeUser(main.OWNER_ID))
    await main.fsubcheck_handler(None, bad)
    assert sc("No entry number 9") in bad.shown_text


@pytest.mark.asyncio
async def test_setfsub_is_repeatable_without_a_limit(db, fake_bot):
    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    for index in range(6):
        start = FakeMessage(text=f"/setfsub @channel{index}", user=FakeUser(main.OWNER_ID))
        await main.setfsub_handler(None, start)
        label = FakeMessage(text=f"Join {index}", user=FakeUser(main.OWNER_ID))
        await main.text_handler(None, label)
    items = await db.get_fsub_list()
    assert len(items) == 6
    assert [i["button_text"] for i in items] == [f"Join {i}" for i in range(6)]


# --------------------------------------------------------------------------- #
#  Pagination — unlimited entries, still inside the mobile budget
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_twelve_entries_paginate_the_keyboard_and_the_text(db):
    items = [fsub_item(chat_id=-100500 - index, title=f"Channel {index}",
                       username=f"channel{index}", button_text=f"Join {index}",
                       order=index) for index in range(12)]

    markup = ui.fsub_keyboard(items)
    rows = markup.inline_keyboard
    assert len(rows) <= 7
    assert all(len(row) <= 2 for row in rows)
    assert sum(1 for row in rows if any(b.url for b in row)) == 5     # 5 per page
    page_row = rows[-2]
    assert [b.callback_data for b in page_row] == ["fsub_page:2", "fsub_page:1"]

    text = ui.fsub_text(items)
    assert "Page 1/3" in text
    assert "Channel 0" in text and "Channel 11" in text                # all titles listed
    assert "t.me/" not in text and "http" not in text

    # every page stays inside the budget and carries the verify button
    for page in range(3):
        markup = ui.fsub_keyboard(items, page)
        assert len(markup.inline_keyboard) <= 7
        assert any(b.callback_data == "fsub:check" for b in flat(markup))
    assert [b.url for b in url_buttons(ui.fsub_keyboard(items, 2))] == [
        f"https://t.me/channel{i}" for i in range(10, 12)]


@pytest.mark.asyncio
async def test_page_buttons_browse_the_join_screen(db, press):
    items = [fsub_item(chat_id=-100500 - index, title=f"Channel {index}",
                       username=f"channel{index}", button_text=f"Join {index}",
                       order=index) for index in range(7)]
    db.fsub_items = items

    message = FakeMessage(user=FakeUser(1001))
    await press(message, "fsub_page:1")
    assert sc("Page 2/2") in message.shown_text
    assert sc("Channel 5") in message.shown_text
    assert [b.url for b in url_buttons(message.shown_markup)] == [
        "https://t.me/channel5", "https://t.me/channel6"]


@pytest.mark.asyncio
async def test_owner_list_pagination_stays_inside_the_budget(db):
    items = [fsub_item(chat_id=-100500 - index, title=f"Channel {index}",
                       username=f"channel{index}", button_text=f"Join {index}",
                       order=index) for index in range(12)]
    for page in range(ui.fsub_list_pages(items)):
        markup = ui.fsub_list_keyboard(items, page)
        assert len(markup.inline_keyboard) <= 7
        assert all(len(row) <= 2 for row in markup.inline_keyboard)
        assert all(len(b.text) <= 28 for row in markup.inline_keyboard for b in row)
        assert any(b.callback_data == "fsub_del_all" for b in flat(markup))


# --------------------------------------------------------------------------- #
#  check_access with several entries
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_check_access_requires_every_entry(db, fake_bot):
    db.fsub_items = [fsub_item(chat_id=-100555, username="one"),
                     fsub_item(chat_id=-100556, username="two", order=1)]
    fake_bot.members[(-100555, 1001)] = make_member(ChatMemberStatus.MEMBER)
    fake_bot.not_members.add((-100556, 1001))

    message = FakeMessage(user=FakeUser(1001))
    assert await main.check_access(message) is False
    assert sc("Join required") in message.shown_text
    assert url_buttons(message.shown_markup)

    fake_bot.not_members.discard((-100556, 1001))
    fake_bot.members[(-100556, 1001)] = make_member(ChatMemberStatus.MEMBER)
    assert await main.check_access(message) is True


@pytest.mark.asyncio
async def test_check_access_fails_open_on_a_telegram_error(db, fake_bot, monkeypatch):
    db.fsub_items = [fsub_item(chat_id=-100555, username="one"),
                     fsub_item(chat_id=-100556, username="two", order=1)]
    fake_bot.members[(-100555, 1001)] = make_member(ChatMemberStatus.MEMBER)
    real = fake_bot.get_chat_member

    async def flaky(chat_id, user_id):
        if int(chat_id) == -100556:
            raise ChatAdminRequired("bot is not an admin there")
        return await real(chat_id, user_id)

    monkeypatch.setattr(fake_bot, "get_chat_member", flaky)
    assert await main.check_access(FakeMessage(user=FakeUser(1001))) is True


@pytest.mark.asyncio
async def test_check_access_accepts_a_pending_join_request(db, fake_bot):
    db.fsub_items = [fsub_item(username=None, invite_link="https://t.me/+secret")]
    fake_bot.not_members.add((-100555, 1001))
    fake_bot.join_requests[-100555] = [make_joiner(1001, pending=True)]
    assert await main.check_access(FakeMessage(user=FakeUser(1001))) is True


@pytest.mark.asyncio
async def test_owner_bypasses_force_sub(db, fake_bot):
    db.fsub_items = [fsub_item(username="one")]
    fake_bot.not_members.add((-100555, main.OWNER_ID))
    assert await main.check_access(FakeMessage(user=FakeUser(main.OWNER_ID))) is True


# --------------------------------------------------------------------------- #
#  TASK 5 — links only inside buttons
# --------------------------------------------------------------------------- #

LINK_SNIPPETS = ("t.me/", "http://", "https://", "telegram.me/", "joinchat/")


@pytest.mark.parametrize("screen", [
    ui.fsub_text([fsub_item(), fsub_item(chat_id=-100556, title="Two", order=1)]),
    ui.fsub_list_text([fsub_item(), fsub_item(chat_id=-100556, title="Two", order=1)]),
    ui.fsub_button_prompt_text("My Channel"),
    ui.fsub_label_invalid_text(),
    ui.fsub_admin_failed_text("not_admin", "My Channel"),
    ui.fsub_join_pending_text("Private Chat"),
    ui.fsub_request_notify_text("Joiner", 1001, "My Channel"),
    ui.setchat_prompt_text(),
    ui.setchat_admin_hint_text("My Channel"),
    ui.setchat_admin_ok_text("My Channel"),
    ui.setchat_admin_failed_text("not_admin"),
    ui.setchat_admin_failed_text("no_post_rights"),
    ui.setchat_admin_failed_text("error"),
    ui.setchat_join_request_text("Private Chat"),
    ui.setchat_resolve_failed_text("no_access"),
    ui.setchat_resolve_failed_text("expired"),
    ui.setchat_done_text("My Channel", -100777),
    ui.setchat_sample_failed_text(),
    ui.setchat_usage_text(),
    # owner confirmations (never echo the invite link back)
    ui.fsub_added_text(fsub_item(username=None, invite_link="https://t.me/+AbCdEf")),
    ui.fsub_removed_text(fsub_item(username=None, invite_link="https://t.me/+AbCdEf")),
    ui.fsub_cleared_text(3),
    ui.fsub_verified_text(),
    ui.fsub_auto_approved_text(),
    ui.fsub_pending_text(),
    ui.fsub_join_instruction_text(True),
    ui.fsub_join_instruction_text(False),
    ui.fsub_request_approved_text(),
    ui.fsub_request_verdict_text("👤 **Joiner** (`1001`) · My Channel", "✅ Approved by Owner"),
    ui.fsub_delete_all_confirm_text(4),
    ui.fsub_empty_text(),
])
def test_no_screen_copy_contains_a_link(screen):
    for snippet in LINK_SNIPPETS:
        assert snippet not in screen, f"{snippet!r} leaked into {screen[:80]!r}"


@pytest.mark.asyncio
async def test_rendered_fsub_and_setchat_screens_keep_links_in_buttons(db, fake_bot):
    db.fsub_items = [fsub_item(username="mychannel"),
                     fsub_item(chat_id=-100556, title="Private", username=None,
                               invite_link="https://t.me/+AbCdEf", order=1)]
    message = FakeMessage(user=FakeUser(1001))
    await main.show_fsub_screen(message)
    assert "t.me/" not in message.shown_text and "http" not in message.shown_text
    assert len(url_buttons(message.shown_markup)) == 2

    fake_bot.members[FAKE_BOT_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                                can_post_messages=True)
    wizard = FakeMessage(text="/setchat @mychannel", user=FakeUser(1001))
    await main.setchat_handler(None, wizard)
    assert "t.me/" not in wizard.shown_text and "http" not in wizard.shown_text


# --------------------------------------------------------------------------- #
#  TASK 7 — admin panel, command registry
# --------------------------------------------------------------------------- #

def test_new_commands_are_registered_everywhere():
    for command in ("setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck"):
        assert command in main.ADMIN_PANEL_COMMANDS, command
        assert command in main.COMMAND_NAMES, command
        assert command in main.ADMIN_INLINE_HANDLERS, command
        assert command in main.ADMIN_OWNER_COMMANDS, command
        assert f"/{command}" in main.admin_help_text(), command
    assert main.ADMIN_VALUE_EXAMPLES["setfsub"] == "t.me/+AbCdEf"
    assert main.ADMIN_VALUE_EXAMPLES["fsublabel"].startswith("1 ")
    assert main.ADMIN_VALUE_EXAMPLES["fsubcheck"] == "1 on"
    assert main.ADMIN_VALUE_EXAMPLES["delfsub"] == "1"


def test_force_sub_page_fits_the_mobile_budget():
    page = main.ADMIN_PAGES.index(next(p for p in main.ADMIN_PAGES if p[0] == "📢 Force Sub"))
    markup = main.admin_panel_keyboard(page)
    assert len(markup.inline_keyboard) <= 7
    assert all(len(row) <= 2 for row in markup.inline_keyboard)
    assert all(len(b.text) <= 28 for row in markup.inline_keyboard for b in row)
    assert {b.callback_data for b in flat(markup)} >= {
        "admin:setfsub", "admin:fsublist", "admin:delfsub", "admin:fsublabel",
        "admin:fsubcheck"}


def test_new_commands_are_excluded_from_the_text_handler():
    """A typed /fsublabel must run the command, never be treated as input."""
    source = Path(main.__file__).read_text()
    block = source.split("async def text_handler")[0]
    block = block.split("filters.command([")[-1].split("])")[0]
    for command in ("setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck"):
        assert f'"{command}"' in block, command


@pytest.mark.asyncio
async def test_panel_buttons_route_to_the_same_handlers(db, press):
    owner = FakeUser(main.OWNER_ID)
    for command in ("fsublist", "fsublabel", "fsubcheck", "delfsub"):
        message = FakeMessage(user=owner)
        await press(message, f"admin:{command}")
        assert message.shown_text, command
        if command in main.ADMIN_VALUE_EXAMPLES:
            assert main.admin_pending[main.OWNER_ID] == command
        else:
            assert main.OWNER_ID not in main.admin_pending

    # the typed value runs the very same handler
    typed = FakeMessage(text="/fsublabel 1 Join Now", user=owner)
    await main.fsublabel_handler(None, typed)
    assert sc("Usage") in typed.shown_text or sc("No entry") in typed.shown_text
