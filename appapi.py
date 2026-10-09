"""Vmore app HTTP API — served by the very same Render web service as the bot.

The Android app never logs in with a Telegram session.  It carries **one access
token** (the short code ``/gentoken`` prints, e.g. ``HPSEG9``) and talks to this
API only::

    GET  /api/v2/token/HPSEG9                     → account snapshot / validate
    POST /api/v2/token/HPSEG9/login                → app login (+ bot DM)
    POST /api/v2/token/HPSEG9/resolve              → what is behind a link?
    POST /api/v2/token/HPSEG9/send                 → deliver a link into the DM
    POST /api/v2/token/HPSEG9/job                  → start a private download
    GET  /api/v2/token/HPSEG9/job/<id>/file        → stream it (Range supported)
    POST /api/v2/token/HPSEG9/job/<id>/pause|resume|cancel
    POST /api/v2/token/HPSEG9/upload               → upload the edited file
    GET  /api/v2/token/HPSEG9/history              → downloads + history
    POST /api/v2/token/HPSEG9/revoke               → switch the token off
    GET  /api/v2/app  •  /api/v2/app/apk  •  /api/v2/owner  •  /api/v2/howto

Private content is pulled with the **user's own stored session** and streamed
straight to the phone, so the bot never re-uploads it to Telegram: that is where
the bandwidth saving comes from.  Uploads go back the same way — the user's own
session puts the finished file into the chat with the bot.

Everything Telegram-shaped runs on the bot's event loop; the Flask worker thread
hands coroutines over with :func:`call`.  The module is import-safe (no Flask app
is created here) so the bot keeps working even when the web server is disabled.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

import database as db
import ui

API_ROOT = "/api/v2"
APP_NAME = ui.APP_NAME

#: Where downloads/uploads are staged before they are streamed or sent.
SPOOL_DIR = Path(os.environ.get("APP_SPOOL_DIR", "downloads/app"))
#: Finished jobs (and their files) are swept this many seconds after last use.
JOB_TTL_SECONDS = float(os.environ.get("APP_JOB_TTL_SECONDS", str(45 * 60)))
#: A download that nobody streams any more is abandoned after this long.
JOB_IDLE_ABORT_SECONDS = float(os.environ.get("APP_JOB_IDLE_ABORT_SECONDS", "600"))
#: Hard ceiling for one app upload (Render's disk is small; 2 GB is Telegram's
#: premium limit and the biggest file the bot can post anyway).
MAX_UPLOAD_BYTES = int(os.environ.get("APP_MAX_UPLOAD_BYTES", str(2 * 1024 ** 3)))
#: The streaming reader waits this long for the first byte before giving up.
STREAM_FIRST_BYTE_TIMEOUT = float(os.environ.get("APP_STREAM_FIRST_BYTE_TIMEOUT", "90"))
#: Chunk size of the streaming reader.
STREAM_BLOCK = 1024 * 256
#: Telegram chunks are 1 MiB — the unit ``stream_media`` offsets in.
TG_CHUNK = 1024 * 1024

_LOCK = threading.Lock()
_LOOP = None
_BRIDGE = None
_LAST_IP = None


# --------------------------------------------------------------------------- #
#  Event-loop plumbing
# --------------------------------------------------------------------------- #

def bind_loop(loop) -> None:
    """Remember the bot's event loop (called from ``bot.on_start``)."""
    global _LOOP
    _LOOP = loop


def bind_bridge(bridge) -> None:
    global _BRIDGE
    _BRIDGE = bridge


def loop_ready() -> bool:
    return _LOOP is not None and _BRIDGE is not None


def call(factory, timeout: float | None = 120):
    """Run ``factory()`` (which must return a coroutine) on the bot's loop."""
    loop = _LOOP
    if loop is None:
        raise RuntimeError("the bot loop is not ready yet")
    future = asyncio.run_coroutine_threadsafe(factory(), loop)
    return future.result(timeout=timeout)


def spawn(factory):
    """Schedule ``factory()`` on the bot loop without waiting for it."""
    loop = _LOOP
    if loop is None:
        raise RuntimeError("the bot loop is not ready yet")
    return asyncio.run_coroutine_threadsafe(factory(), loop)


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def meta() -> dict:
    """Device / version / ip of the calling app (sent as query or JSON fields)."""
    body = request.get_json(silent=True) or {}
    return {
        "device": (body.get("device") or request.args.get("device") or
                   request.headers.get("User-Agent", ""))[:120],
        "version": (body.get("app_version") or request.args.get("app_version") or
                    request.headers.get("X-App-Version") or "")[:32],
        "ip": client_ip(),
    }


def ok(**payload):
    payload.setdefault("ok", True)
    payload.setdefault("app", APP_NAME)
    return jsonify(payload)


def fail(message: str, status: int = 400, **payload):
    payload.update({"ok": False, "error": message})
    return jsonify(payload), status


# --------------------------------------------------------------------------- #
#  Download jobs — the private-content path
# --------------------------------------------------------------------------- #

class JobCancelled(Exception):
    """Raised inside the download loop to stop a cancelled job."""


class Job:
    """One private download: Telegram → server → phone.

    The worker fills ``path`` chunk by chunk while the HTTP reader tails the same
    file, which is what makes the app's player start instantly and what makes
    pause / resume / cancel cheap: pausing only stops feeding the reader.
    """

    def __init__(self, user_id, link, *, kind=None, file_name=None, size=None):
        self.id = uuid.uuid4().hex[:16]
        self.user_id = int(user_id)
        self.link = link
        self.kind = kind or "file"
        self.file_name = file_name or f"{self.id}.bin"
        self.total = int(size or 0)
        self.written = 0
        self.status = "preparing"     # preparing → downloading → ready / error / cancelled
        self.error = None
        self.path = SPOOL_DIR / f"{self.id}.bin"
        self.paused = False
        self.cancelled = False
        self.created = time.time()
        self.updated = time.time()
        self.last_read = time.time()
        self.readers = 0
        self.task = None
        self.mime = mimetypes.guess_type(self.file_name)[0] or "application/octet-stream"

    # ── state helpers ──────────────────────────────────────────────────────
    def touch(self):
        self.updated = time.time()

    @property
    def ready(self) -> bool:
        return self.status == "ready" or (self.total and self.written >= self.total)

    @property
    def finished(self) -> bool:
        return self.status in {"ready", "error", "cancelled"}

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "paused": self.paused,
            "downloaded": int(self.written),
            "total": int(self.total),
            "percent": (int(self.written * 100 / self.total) if self.total else None),
            "file_name": self.file_name,
            "media": self.kind,
            "mime": self.mime,
            "error": self.error,
            "ready": bool(self.ready),
            "age": round(time.time() - self.created, 1),
        }

    # ── the worker ─────────────────────────────────────────────────────────
    async def run(self, client, message, on_progress=None):
        self.status = "downloading"
        self.touch()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as handle:
                async for chunk in client.stream_media(message):
                    while self.paused and not self.cancelled:
                        await asyncio.sleep(0.2)
                    if self.cancelled:
                        raise JobCancelled()
                    handle.write(chunk)
                    handle.flush()
                    self.written += len(chunk)
                    self.touch()
                if self.cancelled:
                    raise JobCancelled()
            if self.total and self.written < self.total:
                # Telegram reported more bytes than we received: report it rather
                # than hand the app a silently truncated file.
                self.status = "error"
                self.error = (f"incomplete download: {self.written} of {self.total} bytes")
            else:
                self.status = "ready"
                self.total = self.total or self.written
        except JobCancelled:
            self.status = "cancelled"
            self._unlink()
        except Exception as exc:  # pragma: no cover - network dependent
            self.status = "error"
            self.error = f"{type(exc).__name__}: {exc}"
            self._unlink()
        finally:
            self.touch()

    def _unlink(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


class JobRegistry:
    """Thread-safe (enough) table of live jobs, shared by the loop and Flask."""

    def __init__(self, ttl: float = JOB_TTL_SECONDS):
        self.ttl = float(ttl)
        self._jobs: dict[str, Job] = {}

    def add(self, job: Job) -> Job:
        with _LOCK:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str, user_id=None) -> Job | None:
        with _LOCK:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        if user_id is not None and job.user_id != int(user_id):
            return None
        return job

    def drop(self, job_id: str) -> None:
        with _LOCK:
            job = self._jobs.pop(job_id, None)
        if job is not None:
            job.cancelled = True
            job._unlink()

    def sweep(self) -> list[str]:
        """Forget finished jobs (and abort idle ones) past their TTL."""
        now = time.time()
        gone = []
        with _LOCK:
            jobs = list(self._jobs.values())
        for job in jobs:
            idle = now - max(job.last_read, job.updated)
            if job.finished and idle > self.ttl:
                self.drop(job.id)
                gone.append(job.id)
            elif not job.finished and job.readers == 0 and idle > JOB_IDLE_ABORT_SECONDS:
                job.cancelled = True
                job.status = "cancelled"
                job.error = "abandoned"
                self.drop(job.id)
                gone.append(job.id)
        return gone

    def live_for(self, user_id) -> list[Job]:
        with _LOCK:
            return [j for j in self._jobs.values() if j.user_id == int(user_id)]


JOBS = JobRegistry()


async def _janitor():
    """Background sweeper for finished/abandoned jobs."""
    while True:
        try:
            JOBS.sweep()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[APP JANITOR] {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(120)


_JANITOR_STARTED = False


def ensure_janitor() -> None:
    global _JANITOR_STARTED
    if _JANITOR_STARTED or _LOOP is None:
        return
    _JANITOR_STARTED = True
    try:
        asyncio.run_coroutine_threadsafe(_janitor(), _LOOP)
    except Exception:  # pragma: no cover - loop already closing
        _JANITOR_STARTED = False


# --------------------------------------------------------------------------- #
#  Range-aware streaming (the app's video player needs byte ranges)
# --------------------------------------------------------------------------- #

def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """``("bytes=100-200", 1000)`` → ``(100, 200)`` (inclusive), or ``None``."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header.split("=", 1)[1].split(",")[0].strip()
    if "-" not in spec:
        return None
    first, _, last = spec.partition("-")
    try:
        if not first:                     # "bytes=-500" → the last 500 bytes
            length = int(last)
            if length <= 0:
                return None
            start = max(0, size - length)
            return start, size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start < 0 or end < start:
        return None
    return start, end


def _wait_for_first_byte(job: Job, timeout: float = STREAM_FIRST_BYTE_TIMEOUT):
    """Block until the worker has produced something (or failed)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.written > 0 or job.finished:
            return
        time.sleep(0.15)


def stream_job(job: Job):
    """Flask response that tails the job's file, byte-range aware."""
    range_header = request.headers.get("Range")
    _wait_for_first_byte(job)
    if job.status == "error" and not job.written:
        return fail(job.error or "download failed", 502)

    size = job.total or job.written
    window = parse_range(range_header, size or 1)
    start, end = window if window else (0, None)

    status = 206 if window else 200

    def generate():
        job.readers += 1
        job.last_read = time.time()
        position = start
        try:
            while True:
                available = job.written
                if position >= available:
                    if job.finished:
                        break
                    if job.cancelled:
                        break
                    position_header = None  # keep the loop simple
                    time.sleep(0.05)
                    job.last_read = time.time()
                    continue
                if end is not None and position > end:
                    break
                length = min(STREAM_BLOCK, available - position)
                if end is not None:
                    length = min(length, end - position + 1)
                if length <= 0:
                    break
                try:
                    with open(job.path, "rb") as handle:
                        handle.seek(position)
                        data = handle.read(length)
                except OSError:
                    break
                if not data:
                    time.sleep(0.05)
                    continue
                position += len(data)
                job.last_read = time.time()
                yield data
        finally:
            job.readers = max(0, job.readers - 1)
            job.last_read = time.time()

    headers = {
        "Content-Type": job.mime,
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
    }
    if end is None and size:
        headers["Content-Length"] = str(max(0, size - start))
    elif end is not None:
        headers["Content-Range"] = f"bytes {start}-{end}/{size or '*'}"
        headers["Content-Length"] = str(max(1, end - start + 1))
    return Response(stream_with_context(generate()), status=status, headers=headers)


def stream_file(path: Path, *, mime: str, download_name: str, cache: bool = True):
    """Serve a finished file with HTTP range support (APK, owner photo, …)."""
    try:
        size = path.stat().st_size
    except OSError:
        return fail("file not available", 404)
    window = parse_range(request.headers.get("Range"), size)
    start, end = window if window else (0, size - 1)
    length = max(0, end - start + 1)

    def generate():
        remaining = length
        with open(path, "rb") as handle:
            handle.seek(start)
            while remaining > 0:
                data = handle.read(min(STREAM_BLOCK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Type": mime,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{download_name}"',
        "Cache-Control": "public, max-age=3600" if cache else "no-store",
    }
    status = 200
    if window:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    return Response(stream_with_context(generate()), status=status, headers=headers)


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #

def authorize(token: str, *, count_call: bool = True):
    """``(token_row, user_id)`` or a Flask error response."""
    info = meta() if request.method != "GET" or request.args else {"device": None,
                                                                   "version": None,
                                                                   "ip": client_ip()}
    try:
        row = call(lambda: _touch(token, info, count_call))
    except RuntimeError as exc:
        return None, fail(f"bot not ready: {exc}", 503)
    except Exception as exc:  # pragma: no cover - database hiccup
        return None, fail(f"token lookup failed: {exc}", 500)
    if not row:
        return None, fail(ui.app_token_invalid_text(), 401)
    if row.get("revoked"):
        reason = row.get("revoked_reason")
        #: ``expired`` is the 30-day clock running out; say so, because the fix
        #: (a fresh /gentoken) is different from a leak (which needs the user to
        #: decide whether to keep using the app at all).
        if reason == "expired":
            return None, fail(ui.app_token_expired_text(), 401, expired=True)
        return None, fail("this token was revoked", 401, revoked=True)
    return row, int(row["user_id"])


async def _touch(token, info, count_call):
    row = await db.get_app_token(token)
    if not row:
        return row
    if not row.get("revoked") and db.app_token_expired(row):
        #: The 30 days are over: retire the row so the answer (and /appusers)
        #: agrees with what the app just experienced.
        await db.app_tokens_col.update_one(
            {"_id": row["_id"]},
            {"$set": {"revoked": True, "revoked_at": db.utcnow(),
                      "revoked_reason": "expired"}})
        return await db.get_app_token(token)
    if row.get("revoked"):
        return row
    return await db.touch_app_token(token, ip=info.get("ip"), device=info.get("device"),
                                    app_version=info.get("version"), count_call=count_call)


# --------------------------------------------------------------------------- #
#  Route tables
# --------------------------------------------------------------------------- #

blueprint = Blueprint("vmore_api", __name__)


@blueprint.after_app_request
def _cors(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, X-App-Version")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response


@blueprint.route("", methods=["GET"])
@blueprint.route("/", methods=["GET"])
def api_index():
    base = request.url_root.rstrip("/")
    return ok(
        name=f"{APP_NAME} API",
        version=ui.APP_VERSION,
        base_url=base,
        endpoints=[
            f"GET  {API_ROOT}/token/<TOKEN>",
            f"POST {API_ROOT}/token/<TOKEN>/login",
            f"POST {API_ROOT}/token/<TOKEN>/resolve",
            f"POST {API_ROOT}/token/<TOKEN>/send",
            f"POST {API_ROOT}/token/<TOKEN>/job",
            f"GET  {API_ROOT}/token/<TOKEN>/job/<ID>",
            f"GET  {API_ROOT}/token/<TOKEN>/job/<ID>/file",
            f"POST {API_ROOT}/token/<TOKEN>/job/<ID>/pause|resume|cancel",
            f"POST {API_ROOT}/token/<TOKEN>/upload",
            f"GET  {API_ROOT}/token/<TOKEN>/history",
            f"POST {API_ROOT}/token/<TOKEN>/revoke",
            f"GET  {API_ROOT}/app",
            f"GET  {API_ROOT}/app/apk",
            f"GET  {API_ROOT}/howto",
            f"GET  {API_ROOT}/owner",
            f"GET  {API_ROOT}/owner/photo",
        ],
        ready=loop_ready(),
    )


@blueprint.route("/howto", methods=["GET"])
def howto():
    base = call(lambda: db.get_app_config()).get("base_url") if loop_ready() else None
    return ok(text=ui.app_howto_text(base_url=base))


@blueprint.route("/app", methods=["GET"])
def app_info():
    if not loop_ready():
        return fail("the bot is still starting", 503)

    async def _gather():
        config = await db.get_app_config()
        apk = config.get("apk") or {}
        users = await db.count_app_users()
        base = config.get("base_url") or request.url_root.rstrip("/")
        return config, apk, users, base

    try:
        config, apk, users, base = call(_gather)
    except Exception as exc:
        return fail(f"app info unavailable: {exc}", 500)
    return ok(
        name=APP_NAME,
        version=apk.get("version") or ui.APP_VERSION,
        base_url=base,
        apk_available=bool(apk.get("file_id")),
        apk_size=apk.get("size"),
        apk_file=apk.get("file_name"),
        apk_url=f"{base}{API_ROOT}/app/apk",
        owner=bridge().owner_cached(),
        howto=ui.app_howto_text(base_url=base),
        app_users=int(users),
        #: TDLib direct mode: the phone runs its own Telegram session, so both
        #: downloads and uploads travel phone ↔ Telegram without touching the
        #: server.  These three values are all it needs to start it.
        **bridge().td_config(),
    )


@blueprint.route("/app/apk", methods=["GET"])
def app_apk():
    if not loop_ready():
        return fail("the bot is still starting", 503)
    try:
        info = call(lambda: bridge().apk_file())
    except Exception as exc:
        return fail(f"APK unavailable: {exc}", 500)
    if not info:
        return fail(ui.app_missing_text(), 404)
    path, name = info
    return stream_file(Path(path), mime="application/vnd.android.package-archive",
                       download_name=name or f"{APP_NAME}.apk")


@blueprint.route("/owner", methods=["GET"])
def owner():
    return ok(owner=bridge().owner_cached())


@blueprint.route("/owner/photo", methods=["GET"])
def owner_photo():
    if not loop_ready():
        return fail("the bot is still starting", 503)
    try:
        data = call(lambda: bridge().owner_photo())
    except Exception as exc:
        return fail(f"photo unavailable: {exc}", 500)
    if not data:
        return fail("no photo", 404)
    return Response(data, mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})


def bridge():
    if _BRIDGE is None:
        raise RuntimeError("the bot loop is not ready yet")
    return _BRIDGE


def bridge_call(method: str, *args, timeout: float | None = 120, **kwargs):
    """Run one bridge coroutine on the bot loop and wait for its result."""
    return call(lambda: getattr(bridge(), method)(*args, **kwargs), timeout=timeout)


# --------------------------------------------------------------------------- #
#  Token endpoints
# --------------------------------------------------------------------------- #

@blueprint.route("/token/<token>", methods=["GET"])
def token_info(token):
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    try:
        payload = bridge_call("account", row)
    except Exception as exc:
        return fail(f"account lookup failed: {exc}", 500)
    return ok(**payload)


@blueprint.route("/token/<token>/login", methods=["POST", "GET"])
def token_login(token):
    """The app's login: validate the token and tell the bot in the DM."""
    if not loop_ready():
        return fail("the bot is still starting", 503)
    info = meta()
    row, error = authorize(token)
    if row is None:
        return error
    payload = bridge_call("login", row, device=info["device"], version=info["version"],
                          ip=info["ip"])
    return ok(first_login=payload.pop("first_login", False), **payload)


@blueprint.route("/token/<token>/revoke", methods=["POST"])
def token_revoke(token):
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    payload = bridge_call("revoke", row)
    return ok(**payload)


@blueprint.route("/token/<token>/resolve", methods=["POST"])
def token_resolve(token):
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token)
    if row is None:
        return error
    link = (request.get_json(silent=True) or {}).get("link") or request.form.get("link")
    if not link:
        return fail("send a 'link' field", 400)
    payload = bridge_call("resolve", row, link)
    return ok(**payload) if payload.get("ok", True) else fail(payload.get("error"), 400, **payload)


@blueprint.route("/token/<token>/send", methods=["POST"])
def token_send(token):
    """Public link → straight into the user's Telegram DM (no phone bandwidth)."""
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token)
    if row is None:
        return error
    body = request.get_json(silent=True) or {}
    link = body.get("link") or request.form.get("link")
    if not link:
        return fail("send a 'link' field", 400)
    payload = bridge_call("send_to_dm", row, link, caption=body.get("caption"),
                          timeout=3600)
    return ok(**payload) if payload.get("ok", True) else fail(payload.get("error"), 400, **payload)


@blueprint.route("/token/<token>/history", methods=["GET"])
def token_history(token):
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    limit = min(int(request.args.get("limit", 50) or 50), 200)
    payload = bridge_call("history", row, limit=limit)
    return ok(**payload)


@blueprint.route("/token/<token>/upload", methods=["POST"])
def token_upload(token):
    """The edited file goes back through the user's own session.

    When the phone changed nothing but the words (caption — and at most the
    thumbnail), no ``file`` field is attached at all: the server re-sends what
    it already has and the biggest network leg of the whole app disappears.
    """
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token)
    if row is None:
        return error
    upload = request.files.get("file")
    if upload is None:
        return _upload_reference(row)

    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "upload.bin").suffix[:12] or ".bin"
    staged = SPOOL_DIR / f"up_{uuid.uuid4().hex[:16]}{suffix}"
    try:
        upload.save(staged)
        if staged.stat().st_size > MAX_UPLOAD_BYTES:
            staged.unlink(missing_ok=True)
            return fail("file too large", 413)
        thumb = request.files.get("thumbnail")
        thumb_path = None
        if thumb is not None and thumb.filename:
            thumb_path = SPOOL_DIR / f"th_{uuid.uuid4().hex[:12]}.jpg"
            thumb.save(thumb_path)
        payload = bridge_call(
            "upload", row, str(staged),
            timeout=3600,
            kind=(request.form.get("kind") or "video"),
            file_name=(request.form.get("file_name") or upload.filename or "Vmore.bin"),
            caption=request.form.get("caption"),
            thumbnail=str(thumb_path) if thumb_path else None,
            link=request.form.get("link"),
            duration=request.form.get("duration"),
            width=request.form.get("width"),
            height=request.form.get("height"),
        )
    except Exception as exc:
        return fail(f"upload failed: {exc}", 500)
    finally:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
    return ok(**payload) if payload.get("ok", True) else fail(payload.get("error"), 400, **payload)


def _upload_reference(row):
    """Zero-transfer commit: the phone shipped words, not bytes.

    Two server-side sources, cheapest first: the finished download job whose
    spooled file is still warm, then the original message itself, which the
    bridge re-sends through the user's session — either natively (Telegram
    does it, zero bytes) or by pulling it down here and sending it straight
    back.  Every failure is flagged ``needs_bytes`` so the app knows to fall
    back to the classic upload on its own.
    """
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = None
    try:
        thumb = request.files.get("thumbnail")
        if thumb is not None and thumb.filename:
            thumb_path = SPOOL_DIR / f"th_{uuid.uuid4().hex[:12]}.jpg"
            thumb.save(thumb_path)
        job_id = (request.form.get("job_id") or "").strip()
        if job_id:
            job = JOBS.get(job_id, row["user_id"])
            if job is not None and job.status == "ready" and job.path.exists():
                #: The very bytes the phone downloaded still sit on the spool:
                #: pushing *them* out skips the phone→server leg entirely and
                #: no second Telegram download is needed either.
                payload = bridge_call(
                    "upload", row, str(job.path), timeout=3600,
                    kind=(request.form.get("kind") or job.kind or "video"),
                    file_name=(request.form.get("file_name") or job.file_name
                               or "Vmore.bin"),
                    caption=request.form.get("caption"),
                    thumbnail=str(thumb_path) if thumb_path else None,
                    link=job.link,
                    duration=request.form.get("duration"),
                    width=request.form.get("width"),
                    height=request.form.get("height"))
                payload.setdefault("via", "spool")
                if payload.get("ok", True):
                    return ok(**payload)
                payload.setdefault("needs_bytes", True)
                return fail(payload.get("error"), 400, **payload)
        link = (request.form.get("link") or "").strip()
        if link:
            payload = bridge_call(
                "upload_reference", row, link, timeout=3600,
                caption=request.form.get("caption"),
                thumbnail=str(thumb_path) if thumb_path else None,
                kind=request.form.get("kind"),
                file_name=request.form.get("file_name"),
                duration=request.form.get("duration"),
                width=request.form.get("width"),
                height=request.form.get("height"))
            return ok(**payload) if payload.get("ok", True) \
                else fail(payload.get("error"), 400, **payload)
        return fail("attach the file as the 'file' field", 400)
    finally:
        if thumb_path is not None:
            try:
                thumb_path.unlink(missing_ok=True)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
#  Job endpoints
# --------------------------------------------------------------------------- #

@blueprint.route("/token/<token>/job", methods=["POST"])
def job_create(token):
    if not loop_ready():
        return fail("the bot is still starting", 503)
    row, error = authorize(token)
    if row is None:
        return error
    body = request.get_json(silent=True) or {}
    link = body.get("link") or request.form.get("link")
    if not link:
        return fail("send a 'link' field", 400)
    try:
        payload = bridge_call("start_job", row, link, JOBS)
    except Exception as exc:
        return fail(f"could not start the download: {exc}", 500)
    return ok(**payload) if payload.get("ok", True) else fail(payload.get("error"), 400, **payload)


@blueprint.route("/token/<token>/job/<job_id>", methods=["GET"])
def job_status(token, job_id):
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    job = JOBS.get(job_id, row["user_id"])
    if job is None:
        return fail("unknown job", 404)
    return ok(job=job.snapshot())


@blueprint.route("/token/<token>/job/<job_id>/file", methods=["GET"])
def job_file(token, job_id):
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    job = JOBS.get(job_id, row["user_id"])
    if job is None:
        return fail("unknown job", 404)
    return stream_job(job)


def _job_action(token, job_id, action):
    row, error = authorize(token, count_call=False)
    if row is None:
        return error
    job = JOBS.get(job_id, row["user_id"])
    if job is None:
        return fail("unknown job", 404)
    if action == "pause":
        job.paused = True
        job.status = "paused" if not job.ready else "ready"
    elif action == "resume":
        job.paused = False
        if not job.finished:
            job.status = "downloading"
    elif action == "cancel":
        JOBS.drop(job_id)
        return ok(cancelled=True, job=job.snapshot())
    job.touch()
    return ok(job=job.snapshot())


@blueprint.route("/token/<token>/job/<job_id>/pause", methods=["POST"])
def job_pause(token, job_id):
    return _job_action(token, job_id, "pause")


@blueprint.route("/token/<token>/job/<job_id>/resume", methods=["POST"])
def job_resume(token, job_id):
    return _job_action(token, job_id, "resume")


@blueprint.route("/token/<token>/job/<job_id>/cancel", methods=["POST"])
def job_cancel(token, job_id):
    return _job_action(token, job_id, "cancel")


# --------------------------------------------------------------------------- #
#  Registration
# --------------------------------------------------------------------------- #

def register(app, bridge_object) -> None:
    """Attach the API to the bot's Flask app and remember the bridge."""
    bind_bridge(bridge_object)
    app.register_blueprint(blueprint, url_prefix=API_ROOT)
    app.config.setdefault("MAX_CONTENT_LENGTH", MAX_UPLOAD_BYTES)
    ensure_janitor()
    print(f"[APP API] {APP_NAME} API mounted at {API_ROOT}", flush=True)
