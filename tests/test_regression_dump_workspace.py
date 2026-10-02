"""PR #14 regressions: exercise real callback identity and workspace boundaries."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import main
import ui
from conftest import FakeMessage, FakeUser, FakeChat, make_query, sc


@pytest.mark.asyncio
async def test_owner_disconnect_button_uses_clicker_not_bot_author(db):
    await main.set_dump_channel(-10088, 'Workspace', None, 'channel')
    message = FakeMessage(user=FakeUser(999), text='Dump status')  # bot-authored menu
    message.chat = FakeChat(main.OWNER_ID, 'private')
    query = make_query(message, 'dump:off', FakeUser(main.OWNER_ID))
    await main.cb_dump_off(None, query)
    assert await main.get_dump_channel() is None
    assert sc('Owner only') not in message.shown_text


@pytest.mark.asyncio
async def test_disconnect_ack_precedes_cleanup(db, monkeypatch):
    await main.set_dump_channel(-10088, 'Workspace', None, 'channel')
    async def slow_flush():
        await asyncio.sleep(.15)
        return 0
    monkeypatch.setattr(main.DUMP_MIRROR, 'flush', slow_flush)
    message = FakeMessage('/deldump', FakeUser(main.OWNER_ID))
    started = time.perf_counter()
    task = asyncio.create_task(main.deldump_handler(None, message))
    await asyncio.sleep(.03)
    elapsed = time.perf_counter() - started
    acknowledged = bool(message.replies)
    await task
    print(f'ack probe at {elapsed:.3f}s: {acknowledged}')
    assert acknowledged, 'cleanup blocks the first command response'


@pytest.mark.asyncio
async def test_login_entry_rejects_channel_even_when_called_directly(db, monkeypatch):
    monkeypatch.setattr(main, 'get_user_client', AsyncMock(return_value=None))
    message = FakeMessage('/login')
    message.chat = FakeChat(-10088, 'channel')
    await main.login_handler(None, message)
    assert not message.replies and not message.edits
    assert message.from_user.id not in main.login_pending

from conftest import make_member, FAKE_BOT_ID, drain_background
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid

DUMP = -10088
DESTINATION = -10099


async def connect_workspace(fake_bot):
    await main.add_user(1001, 'Reader', None)
    await main.set_dump_channel(DUMP, 'Workspace', None, 'channel')
    fake_bot.members[(DUMP, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=True, can_delete_messages=True)


@pytest.mark.parametrize('media', [False, True])
@pytest.mark.parametrize('destination', [1001, DESTINATION])
@pytest.mark.parametrize('user_session', [False, True])
async def test_native_stage_edit_copy_delete_order(db, fake_bot, media, destination, user_session):
    await connect_workspace(fake_bot)
    await main.set_prefix(1001, 'Prefix')
    await main.set_suffix(1001, 'Suffix')
    source = SimpleNamespace(id=77, chat=FakeChat(-100123), empty=False,
                             text=None if media else 'Body', caption='Body' if media else None,
                             video=object() if media else None)
    events = []
    async def copy(chat_id, from_chat_id, message_id, **kwargs):
        events.append(('copy', chat_id, from_chat_id, message_id))
        result = SimpleNamespace(id=500 if chat_id == DUMP else 600)
        async def edit(body, **kw):
            assert 'Prefix' in body and 'Suffix' in body
            events.append(('edit', chat_id))
        result.edit_text = result.edit_caption = edit
        return result
    async def delete(chat_id, message_id):
        events.append(('delete', chat_id, message_id))
    fake_bot.copy_message = copy
    fake_bot.delete_messages = delete
    fake_bot.messages[77] = source
    client = fake_bot
    if user_session:
        client = SimpleNamespace(is_user_client=True, get_messages=AsyncMock(return_value=source),
                                 copy_message=copy)
        main.user_clients[1001] = client
    request = FakeMessage('link')
    request.chat = FakeChat(destination, 'channel' if destination < 0 else 'private')
    assert await main.try_native_copy(request, client, -100123, 77) == main.DUMP_STAGED_COPY
    assert events == [('copy', DUMP, -100123, 77), ('edit', DUMP),
                      ('copy', destination, DUMP, 500), ('delete', DUMP, 500)]
    assert source.caption == ('Body' if media else None)
    assert not main.DUMP_MIRROR.pending


@pytest.mark.parametrize('destination', [1001, DESTINATION])
@pytest.mark.parametrize('media', [False, True])
async def test_fallback_upload_or_text_still_uses_workspace(db, fake_bot, tmp_path, destination, media):
    await connect_workspace(fake_bot)
    await main.set_prefix(1001, 'Prefix')
    source = SimpleNamespace(id=77, empty=False, chat=FakeChat(-100123),
        text=None if media else 'Body', caption='Body' if media else None, media=media,
        video=SimpleNamespace(file_id='v', file_size=100) if media else None,
        photo=None, document=None, audio=None, voice=None, video_note=None, sticker=None, animation=None)
    fake_bot.messages[77] = source
    original_copy = fake_bot.copy_message
    async def copy(chat_id, from_chat_id, message_id, **kw):
        if from_chat_id == -100123:
            raise RuntimeError('source cannot be copied')
        return await original_copy(chat_id, from_chat_id, message_id, **kw)
    fake_bot.copy_message = copy
    file = tmp_path / 'video.mp4'
    file.write_bytes(b'content')
    fake_bot.download_media = AsyncMock(return_value=str(file))
    uploads = []
    async def upload(chat_id, path, **kw):
        uploads.append((chat_id, kw['caption']))
        return SimpleNamespace(id=800)
    fake_bot.send_video = upload
    request = FakeMessage('link')
    request.chat = FakeChat(destination, 'channel' if destination < 0 else 'private')
    assert await main.fetch_and_send(request, FakeMessage(), fake_bot, "example", 77, enforce_fsub=False)
    assert all(row[0] == destination and row[1] == DUMP for row in fake_bot.copies)
    assert fake_bot.deleted and not main.DUMP_MIRROR.pending
    if media:
        assert uploads[0][0] == DUMP and 'Prefix' in uploads[0][1]
    else:
        assert fake_bot.sent[0]['chat_id'] == DUMP and 'Prefix' in fake_bot.sent[0]['text']
    assert not fake_bot.edited


@pytest.mark.parametrize('failure', ['permission', 'edit', 'final_copy'])
async def test_workspace_failures_never_edit_or_send_direct(db, fake_bot, failure):
    await connect_workspace(fake_bot)
    source = SimpleNamespace(id=77, chat=FakeChat(-100123), text='Body', empty=False)
    fake_bot.messages[77] = source
    if failure == 'permission':
        fake_bot.members[(DUMP, FAKE_BOT_ID)] = make_member(
            ChatMemberStatus.ADMINISTRATOR, can_post_messages=False, can_delete_messages=True)
    calls = []
    async def copy(chat_id, from_chat_id, message_id, **kw):
        calls.append((chat_id, from_chat_id))
        if failure == 'final_copy' and chat_id != DUMP:
            raise ChatAdminRequired()
        async def edit(*args, **kwargs):
            if failure == 'edit':
                raise ChatAdminRequired()
        return SimpleNamespace(id=500, edit_text=edit)
    fake_bot.copy_message = copy
    with pytest.raises(main.DumpWorkspaceError):
        await main.try_native_copy(FakeMessage(), fake_bot, -100123, 77)
    assert all(dest == DUMP or src == DUMP for dest, src in calls)
    assert not fake_bot.sent


async def test_immediate_delete_failure_keeps_ttl_retry(db, fake_bot):
    await connect_workspace(fake_bot)
    fake_bot.delete_messages = AsyncMock(side_effect=ChatAdminRequired())
    main.DUMP_MIRROR.schedule_delete(DUMP, 5)
    assert not await main.DUMP_MIRROR.delete_now(DUMP, 5)
    assert f'{DUMP}:5' in main.DUMP_MIRROR.tasks
    fake_bot.delete_messages = AsyncMock(return_value=True)
    await main.DUMP_MIRROR._delete_later(DUMP, 5, delay=0)
    assert not main.DUMP_MIRROR.pending


@pytest.mark.parametrize('step,text', [('waiting_phone', '+15551234567'), ('waiting_otp', '1 2 3 4 5'), ('waiting_2fa', 'secret')])
async def test_login_continuations_and_bot_authored_callbacks_are_private(db, fake_bot, step, text):
    request = FakeMessage(text)
    request.chat = FakeChat(DUMP, 'channel')
    main.login_pending[1001] = {'step': step}
    await main.text_handler(None, request)
    await main.dispatch_channel_command(None, FakeMessage('/login'))
    menu = FakeMessage(user=FakeUser(FAKE_BOT_ID))
    menu.chat = FakeChat(DUMP, 'channel')
    query = make_query(menu, 'cmd_login', FakeUser(1001))
    await main.callback_handler(None, query)
    assert not request.replies and not menu.edits and not menu.replies
    assert main.login_pending[1001] == {'step': step}
    assert not fake_bot.sent and not fake_bot.copies


async def test_nonowner_cannot_disconnect_by_command_or_callback(db, fake_bot):
    await connect_workspace(fake_bot)
    request = FakeMessage('/deldump', FakeUser(1001))
    await main.deldump_handler(None, request)
    await main.cb_dump_off(None, make_query(request, 'dump:off'))
    assert (await main.get_dump_channel())['chat_id'] == DUMP
    assert sc('Owner only') in request.shown_text


@pytest.mark.parametrize('post,delete', [(True, True), (False, True), (True, False), (False, False)])
async def test_dump_reports_each_current_permission(db, fake_bot, post, delete):
    await connect_workspace(fake_bot)
    fake_bot.members[(DUMP, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=post, can_delete_messages=delete)
    request = FakeMessage('/dump', FakeUser(main.OWNER_ID))
    await main.dump_status_handler(None, request)
    assert sc('Post Messages: ' + ('allowed' if post else 'missing')) in request.shown_text
    assert sc('Delete Messages: ' + ('allowed' if delete else 'missing')) in request.shown_text
    assert (sc('NOT ready') in request.shown_text) is not (post and delete)


async def test_dump_permission_lookup_failure_not_ready(db, fake_bot):
    await connect_workspace(fake_bot)
    fake_bot.get_chat_member = AsyncMock(side_effect=RuntimeError())
    request = FakeMessage('/dump', FakeUser(main.OWNER_ID))
    await main.dump_status_handler(None, request)
    assert sc('unknown (check failed)') in request.shown_text and sc('NOT ready') in request.shown_text


async def test_setdump_real_bot_authored_button_opens_picker(db, fake_bot):
    menu = FakeMessage(user=FakeUser(FAKE_BOT_ID))
    menu.chat = FakeChat(main.OWNER_ID, 'private')
    await main.cb_cmd_setdump(None, make_query(menu, 'cmd_setdump', FakeUser(main.OWNER_ID)))
    assert main.pending_action[main.OWNER_ID] == 'setdump_share'
    assert menu.shown_markup.__class__.__name__ == 'ReplyKeyboardMarkup'


@pytest.mark.parametrize('mode', ['broadcast', 'botcast', 'pin'])
async def test_campaign_audience_with_dump_also_registered_as_setchat(db, fake_bot, monkeypatch, mode):
    await connect_workspace(fake_bot)
    monkeypatch.setattr(main, 'get_user_channels', AsyncMock(return_value=[{'chat_id': DUMP}, {'chat_id': DESTINATION}]))
    fake_bot.pin_chat_message = AsyncMock(side_effect=ChatAdminRequired())
    payload = {'source_chat_id': 1, 'source_message_id': 9}
    report = await main.deliver_campaign_payload(payload, users_only=mode == 'botcast', pin=mode == 'pin')
    final = [dest for dest, src, mid in fake_bot.copies if src == DUMP]
    assert set(final) == ({1001, DESTINATION} if mode == 'broadcast' else {1001})
    assert DUMP not in final
    if mode == 'pin':
        assert report['pin_attempted'] == report['pin_failed_users'] == 1
        assert report['pin_succeeded'] == 0
        assert fake_bot.pin_chat_message.await_args.args[0] == 1001
        text = ui.broadcast_complete_text(report, users_only=True, pin=True)
        assert 'best-effort' in text and '1 refused' in text
    assert fake_bot.deleted


async def test_broadcast_blocked_and_other_errors_separate(db, fake_bot):
    await db.add_user(1001, 'Reader')
    await db.add_user(2002, 'Blocked')
    await db.add_user(3003, 'Other error')
    original = fake_bot.send_message
    async def send(uid, text, **kwargs):
        if uid == 2002:
            raise PeerIdInvalid()
        if uid == 3003:
            raise RuntimeError('server')
        return await original(uid, text, **kwargs)
    fake_bot.send_message = send
    report = await main.run_text_broadcast('Hello', users_only=True)
    assert (report['users_sent'], report['blocked'], report['failed']) == (1, 1, 1)


async def test_broadcast_returns_before_delivery_and_reports_later(db, monkeypatch):
    release = asyncio.Event()
    async def slow(*args, **kwargs):
        await release.wait()
        return {'users_total': 1, 'users_sent': 1}
    monkeypatch.setattr(main, 'run_text_broadcast', slow)
    message = FakeMessage('/broadcast Hello', FakeUser(main.OWNER_ID))
    await asyncio.wait_for(main.broadcast_handler(None, message), .1)
    assert sc('started in the background') in message.shown_text
    release.set()
    await drain_background()
    assert sc('BROADCAST COMPLETE') in message.shown_text


async def test_bounded_delivery_speed_against_previous_serial_loop(db):
    active = peak = 0
    async def send(item):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.1)
        active -= 1
    start = time.perf_counter()
    for item in range(8):
        await send(item)
        await asyncio.sleep(.05)  # PR #14 loop
    before = time.perf_counter() - start
    peak = 0
    start = time.perf_counter()
    await main.bounded_deliver(range(8), send)
    after = time.perf_counter() - start
    print(f'8 simulated 100ms sends: serial={before:.3f}s bounded={after:.3f}s; peak={peak}')
    assert 1 < peak <= 4
    assert after < before * .7

# Command baseline from PR #14's base (fa1274f), including aliases. No menu
# truncation is permitted; the admin panel is already paginated.
BASELINE_COMMANDS = '''start help login logout status cancel setcaption delcaption setthumb delthumb
setprefix setsuffix mystats myinfo history settings language refer bookmark bookmarks favorite favorites
share feedback premium stats users loggedusers activeusers newusers topusers broadcast ban unban banlist
finduser userinfo addpremium removepremium premiumlist addadmin removeadmin adminlist setfsub fsublist
delfsub fsublabel fsubcheck maintenance feedbacks sendmsg clearlogs export adminhelp admin admins addqr
delqr removeqr payments redeem setchat delchat models engine mychannels setengine pin pinned setdump
deldump dump post native giveaway participants endgiveaway menu cmsg botcast unpin'''.split()


@pytest.mark.parametrize('name', BASELINE_COMMANDS)
async def test_every_baseline_command_registered_and_reachable(db, fake_bot, name):
    assert name in main.COMMAND_NAMES
    assert callable(main.COMMAND_HANDLERS[name])
    await main.register_telegram_commands()
    assert name in {command.command for command in fake_bot.registered_commands}
    assert fake_bot.command_scopes[-1].__class__.__name__ == 'BotCommandScopeAllPrivateChats'
    if name in main.ADMIN_INLINE_HANDLERS:
        assert name in {n for _, names in main.ADMIN_PAGES for n in names}
        assert '/' + name in main.admin_help_text()


async def test_precommand_hook_registered_on_async_handler_not_latency_helper(db):
    import ast
    from pathlib import Path
    module = ast.parse(Path(main.__file__).read_text())
    defs = {node.name: node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not defs['update_lag_ms'].decorator_list
    assert len(defs['abort_pending_on_command'].decorator_list) == 1
    assert isinstance(defs['abort_pending_on_command'], ast.AsyncFunctionDef)


@pytest.mark.parametrize('admin,post,delete', [(False, True, True), (True, False, True), (True, True, False), (True, True, True)])
async def test_picker_requester_and_both_bot_rights_checked(db, fake_bot, admin, post, delete):
    owner = main.OWNER_ID
    fake_bot.members[(DUMP, owner)] = make_member(
        ChatMemberStatus.ADMINISTRATOR if admin else ChatMemberStatus.MEMBER, can_post_messages=admin)
    fake_bot.members[(DUMP, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=post, can_delete_messages=delete)
    main.pending_action[owner] = 'setdump_share'
    request = FakeMessage(user=FakeUser(owner))
    request.chat_shared = SimpleNamespace(button_id=main.DUMP_PICKER_BUTTON_ID,
        chat=SimpleNamespace(id=DUMP, type='channel', title='Workspace', username=None))
    await main.chat_shared_handler(None, request)
    assert bool(await main.get_dump_channel()) == (admin and post and delete)


async def test_setdump_typed_fallback_checks_same_rights(db, fake_bot, monkeypatch):
    fake_bot.members[(DUMP, main.OWNER_ID)] = make_member(ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)
    fake_bot.members[(DUMP, FAKE_BOT_ID)] = make_member(ChatMemberStatus.ADMINISTRATOR, can_post_messages=True, can_delete_messages=True)
    monkeypatch.setattr(main, 'resolve_chat_target', AsyncMock(return_value={
        'chat_id': DUMP, 'type': 'channel', 'title': 'Workspace'}))
    request = FakeMessage('/setdump @workspace', FakeUser(main.OWNER_ID))
    await main.setdump_handler(None, request)
    assert (await main.get_dump_channel())['chat_id'] == DUMP


async def test_admin_setdump_sends_picker_not_edit(db, fake_bot):
    message = FakeMessage(user=FakeUser(FAKE_BOT_ID))
    message.chat = FakeChat(main.OWNER_ID, 'private')
    query = make_query(message, 'admin:setdump', FakeUser(main.OWNER_ID))
    await main.run_admin_inline(None, query, 'setdump')
    assert message.replies and not message.edits
    assert message.shown_markup.__class__.__name__ == 'ReplyKeyboardMarkup'


async def test_login_ack_before_slow_session_lookup(db, monkeypatch):
    release = asyncio.Event()
    async def session(uid):
        await release.wait()
    monkeypatch.setattr(main, 'get_session', session)
    request = FakeMessage('/login')
    task = asyncio.create_task(main.login_handler(None, request))
    await asyncio.sleep(.01)
    assert request.replies
    release.set()
    await task
    assert main.login_pending[1001]['step'] == 'waiting_phone'


@pytest.mark.parametrize('media', [False, True])
async def test_oversized_custom_content_stages_every_chunk(db, fake_bot, media):
    await connect_workspace(fake_bot)
    await main.set_caption(1001, '😀' * 2500)
    source = SimpleNamespace(id=77, empty=False, chat=FakeChat(-100123),
        text=None if media else 'body', caption='body' if media else None,
        video=True if media else None)
    fake_bot.messages[77] = source
    assert await main.try_native_copy(FakeMessage(), fake_bot, 'example', 77)
    finals = [(dest, src, mid) for dest, src, mid in fake_bot.copies if src == DUMP]
    assert len(finals) >= 2
    assert all(dest == 1001 for dest, src, mid in finals)
    assert len(fake_bot.deleted) == len(finals)
    assert not main.DUMP_MIRROR.pending


async def test_upload_failure_does_not_send_to_destination(db, fake_bot, tmp_path):
    await connect_workspace(fake_bot)
    source = SimpleNamespace(id=77, empty=False, chat=FakeChat(-100123), text=None,
        caption='body', media=True, photo=True, video=None, document=None, audio=None,
        voice=None, video_note=None, sticker=None, animation=None)
    fake_bot.messages[77] = source
    fake_bot.copy_message = AsyncMock(side_effect=ChatAdminRequired())
    file = tmp_path / 'photo.jpg'
    file.write_bytes(b'photo')
    fake_bot.download_media = AsyncMock(return_value=str(file))
    fake_bot.send_photo = AsyncMock(side_effect=ChatAdminRequired())
    status = FakeMessage()
    assert not await main.fetch_and_send(FakeMessage(), status, fake_bot, 'example', 77, enforce_fsub=False)
    assert fake_bot.send_photo.await_args.args[0] == DUMP
    assert fake_bot.send_photo.await_count == 1
    assert sc('dump workspace') in status.shown_text
    assert not file.exists()


async def test_failed_campaign_stage_never_uses_source_directly(db, fake_bot):
    await connect_workspace(fake_bot)
    fake_bot.copy_message = AsyncMock(side_effect=ChatAdminRequired())
    with pytest.raises(ChatAdminRequired):
        await main.deliver_campaign_payload({'source_chat_id': 1, 'source_message_id': 5})
    assert all(call.kwargs['chat_id'] == DUMP for call in fake_bot.copy_message.await_args_list)


async def test_custom_media_overflow_is_not_lost_in_fallback(db, fake_bot, tmp_path, monkeypatch):
    await connect_workspace(fake_bot)
    await main.set_caption(1001, 'Long custom ' * 150)
    source = SimpleNamespace(id=77, empty=False, chat=FakeChat(-100123), text=None,
        caption='original', media=True, photo=True, video=None, document=None, audio=None,
        voice=None, video_note=None, sticker=None, animation=None)
    fake_bot.messages[77] = source
    monkeypatch.setattr(main, 'try_native_copy', AsyncMock(return_value=False))
    file = tmp_path / 'photo.jpg'
    file.write_bytes(b'photo')
    fake_bot.download_media = AsyncMock(return_value=str(file))
    fake_bot.send_photo = AsyncMock(return_value=SimpleNamespace(id=888))
    assert await main.fetch_and_send(FakeMessage(), FakeMessage(), fake_bot, 'example', 77, enforce_fsub=False)
    texts = [row['text'] for row in fake_bot.sent if 'text' in row]
    assert 'Long custom ' * 150 in ''.join(texts)
    assert all(dest == 1001 and src == DUMP for dest, src, mid in fake_bot.copies)
    assert (DUMP, 888) in fake_bot.deleted
