"""Company-owned OAuth settings and each member's personal Google connection."""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.error
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import providers
from records import *

CONFIG_KEYS = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "ZOOM_ACCOUNT_ID",
    "ZOOM_CLIENT_ID",
    "ZOOM_CLIENT_SECRET",
    "ZOOM_HOST",
)
IDENTITY_SCOPES = "openid email profile"
SCOPES = (
    IDENTITY_SCOPES
    + " https://www.googleapis.com/auth/calendar.events.owned https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/tasks"
)
context = ContextVar("provider_context", default=None)
original_setting = providers.setting
original_google_token = providers.google_token


def config(db):
    value = one(db, "SELECT blob FROM secrets WHERE k='company_oauth'")
    stored = json.loads(providers.protect(value["blob"], True)) if value else {}
    return {
        k: os.environ.get("PEOPLEDESK_" + k) or stored.get(k, "") for k in CONFIG_KEYS
    }


def setting(k):
    ctx = context.get()
    return config(ctx[0]).get(k, "") if ctx else original_setting(k)


def token(db):
    ctx = context.get()
    if not ctx:
        return original_google_token(db)
    record = one(db, "SELECT blob FROM secrets WHERE k=?", ("google:" + ctx[1],))
    if not record:
        raise ValueError("Connect your own Google account in Connections.")
    data = json.loads(providers.protect(record["blob"], True))
    return providers.remote(
        "https://oauth2.googleapis.com/token",
        "POST",
        {
            "client_id": setting("GOOGLE_CLIENT_ID"),
            "client_secret": setting("GOOGLE_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": data["refresh_token"],
        },
        form=True,
    )["access_token"]


providers.setting = setting
providers.google_token = token


@contextmanager
def bound(db, pid):
    t = context.set((db, pid))
    try:
        yield
    finally:
        context.reset(t)


def connection(db, pid):
    c = config(db)
    record = one(db, "SELECT blob FROM secrets WHERE k=?", ("google:" + pid,))
    profile = json.loads(providers.protect(record["blob"], True)) if record else {}
    return {
        "googleConfigured": bool(c["GOOGLE_CLIENT_ID"] and c["GOOGLE_CLIENT_SECRET"]),
        "googleLinked": bool(record),
        "email": profile.get("email", ""),
        "zoomConfigured": all(c[k] for k in CONFIG_KEYS if k.startswith("ZOOM")),
    }


def start(handler, db, mode):
    c = config(db)
    if not c["GOOGLE_CLIENT_ID"] or not c["GOOGLE_CLIENT_SECRET"]:
        raise ValueError(
            "The company administrator must configure Google in Connections."
        )
    nonce = secrets.token_urlsafe(30)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(60)
    browser = secrets.token_urlsafe(32)
    redirect = handler.app.origin + "/oauth/account"
    query = dict(
        client_id=c["GOOGLE_CLIENT_ID"],
        redirect_uri=redirect,
        response_type="code",
        scope=IDENTITY_SCOPES if mode == "login" else SCOPES,
        state=state,
        nonce=nonce,
        code_challenge=base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        )
        .decode()
        .rstrip("="),
        code_challenge_method="S256",
        prompt="select_account" if mode == "login" else "consent",
        access_type="online" if mode == "login" else "offline",
    )
    with handler.app.lock:
        handler.app.oauth = {
            k: v for k, v in handler.app.oauth.items() if v["expiry"] > time.time()
        }
        handler.app.oauth[state] = {
            "browser": browser,
            "session": handler.token(),
            "mode": mode,
            "nonce": nonce,
            "verifier": verifier,
            "expiry": time.time() + 600,
        }
    cookie = (
        f"pd_oauth={browser}; Path=/oauth/account; HttpOnly; SameSite=Lax; Max-Age=600"
        + ("; Secure" if handler.app.origin.startswith("https:") else "")
    )
    handler.reply(
        {
            "url": "https://accounts.google.com/o/oauth2/v2/auth?"
            + urllib.parse.urlencode(query)
        },
        headers={"Set-Cookie": cookie},
    )


def callback(handler, db, query):
    from http.cookies import SimpleCookie
    from google.oauth2.id_token import verify_oauth2_token
    from google.auth.transport.requests import Request
    import company

    with handler.app.lock:
        session = handler.app.oauth.pop(query.get("state", [""])[0], None)
    cookies = SimpleCookie()
    cookies.load(handler.headers.get("Cookie", ""))
    browser = cookies.get("pd_oauth")
    if (
        not session
        or not browser
        or not secrets.compare_digest(browser.value, session["browser"])
        or session["expiry"] < time.time()
    ):
        raise ValueError("Google sign-in expired. Start again.")
    if not query.get("code"):
        raise ValueError("Google authorization was cancelled.")
    c = config(db)
    tokens = providers.remote(
        "https://oauth2.googleapis.com/token",
        "POST",
        dict(
            client_id=c["GOOGLE_CLIENT_ID"],
            client_secret=c["GOOGLE_CLIENT_SECRET"],
            redirect_uri=handler.app.origin + "/oauth/account",
            grant_type="authorization_code",
            code=query["code"][0],
            code_verifier=session["verifier"],
        ),
        form=True,
    )
    ident = verify_oauth2_token(tokens["id_token"], Request(), c["GOOGLE_CLIENT_ID"])
    if (
        ident.get("nonce") != session["nonce"]
        or not ident.get("email_verified")
        or not ident.get("sub")
    ):
        raise ValueError("Google identity verification failed.")
    if session["mode"] == "login":
        with db:
            db.execute("BEGIN IMMEDIATE")
            linked = one(
                db, "SELECT person FROM identities WHERE sub=?", (ident["sub"],)
            )
            if linked:
                pid = linked["person"]
            else:
                # Match only the exact verified company email, never its domain or claimed role.
                existing = one(
                    db,
                    "SELECT id FROM people WHERE email=? COLLATE NOCASE",
                    (ident["email"],),
                )
                if existing:
                    pid = existing["id"]
                    db.execute(
                        "INSERT INTO identities VALUES(?,?)", (ident["sub"], pid)
                    )
                else:
                    previous = one(
                        db,
                        "SELECT id FROM registrations WHERE email=?",
                        (ident["email"],),
                    )
                    if not previous:
                        company.register(
                            db,
                            {
                                "name": ident.get("name", ident["email"]),
                                "team": "Unassigned",
                            },
                            ident,
                        )
                    handler.sendbody(
                        303, b"", "text/plain", {"Location": "/?registration=pending"}
                    )
                    return
            company.enrich(db, person(db, pid))
        handler.sendbody(
            303,
            b"",
            "text/plain",
            {
                "Location": "/employee",
                **handler.cookieheader(handler.app.login(pid, handler.token()), 28800),
            },
        )
    else:
        if session["session"] != handler.token():
            raise PermissionError("Sign in again before connecting Google.")
        u = handler.user(db)
        if ident["email"].casefold() != u["email"].casefold():
            raise ValueError("Connect the Google account matching your company email.")
        if not tokens.get("refresh_token"):
            raise ValueError(
                "Google did not supply offline access. Reconnect and consent."
            )
        data = {
            "refresh_token": tokens["refresh_token"],
            "email": ident["email"],
            "scope": tokens.get("scope", ""),
        }
        with db:
            db.execute(
                "INSERT OR REPLACE INTO secrets VALUES(?,?)",
                ("google:" + u["id"], providers.protect(json.dumps(data).encode())),
            )
        handler.sendbody(303, b"", "text/plain", {"Location": "/#integrations"})


def refresh(db, u):
    result = []
    pid = u["id"]
    with bound(db, pid):
        bearer = token(db)
        calls = {
            "calendar": (
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                {
                    "timeMin": day() + "T00:00:00Z",
                    "timeMax": day(31) + "T00:00:00Z",
                    "singleEvents": "true",
                    "maxResults": "100",
                    "orderBy": "startTime",
                },
            ),
            "files": (
                "https://www.googleapis.com/drive/v3/files",
                {
                    "pageSize": 50,
                    "q": "trashed = false",
                    "fields": "files(id,name,mimeType,webViewLink,modifiedTime),nextPageToken",
                    "orderBy": "modifiedTime desc",
                },
            ),
            "tasks": (
                "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks",
                {"maxResults": 100, "showCompleted": "true", "showHidden": "true"},
            ),
            "mail": (
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                {"maxResults": 10, "q": "in:inbox"},
            ),
        }
        for kind, (url, params) in calls.items():
            try:
                page = providers.remote(
                    url + "?" + urllib.parse.urlencode(params), token=bearer
                )
                values = page.get(
                    (
                        "files"
                        if kind == "files"
                        else "messages" if kind == "mail" else "items"
                    ),
                    [],
                )
                if kind == "calendar":
                    while page.get("nextPageToken"):
                        params["pageToken"] = page["nextPageToken"]
                        page = providers.remote(
                            url + "?" + urllib.parse.urlencode(params), token=bearer
                        )
                        values += page.get("items", [])
                if kind == "mail":
                    values = [
                        providers.remote(
                            "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                            + v["id"]
                            + "?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date",
                            token=bearer,
                        )
                        for v in values
                    ]
                with db:
                    db.execute(
                        "DELETE FROM personal_cloud WHERE person=? AND provider='Google' AND kind=?",
                        (pid, kind),
                    )
                    db.executemany(
                        "INSERT INTO personal_cloud VALUES(?,'Google',?,?,?)",
                        [(pid, kind, v["id"], json.dumps(v)) for v in values],
                    )
                result.append(kind + " refreshed (" + str(len(values)) + ")")
            except Exception:
                result.append(kind + " unavailable; any previous results are retained")
    return {"message": ". ".join(result)}


def run(db, u, op, d):
    pid = u["id"]
    if op == "provider-config":
        import company

        company.administrator(u)
        saved = config(db)
        for k in CONFIG_KEYS:
            if d.get(k):
                saved[k] = text(d[k], k, 4000)
        db.execute(
            "INSERT OR REPLACE INTO secrets VALUES('company_oauth',?)",
            (providers.protect(json.dumps(saved).encode()),),
        )
        db.commit()
        return {"message": "Company provider settings saved."}
    if op == "cloud-disconnect":
        with db:
            db.execute("DELETE FROM secrets WHERE k=?", ("google:" + pid,))
            db.execute("DELETE FROM personal_cloud WHERE person=?", (pid,))
        return {"message": "Your Google connection was removed."}
    if op == "cloud-refresh":
        return refresh(db, u)
    if op == "cloud-test-zoom":
        with bound(db, pid):
            providers.zoom_token()
        return {"message": "Zoom accepted the company credentials."}
    if op == "cloud-task":
        t = one(
            db,
            "SELECT * FROM tasks WHERE id=? AND (owner=? OR helper=?)",
            (d.get("id"), pid, pid),
        )
        if not t:
            raise PermissionError("You can sync tasks assigned to you.")
        details = one(db, "SELECT accepted FROM task_details WHERE task=?", (t["id"],))
        if details and not details["accepted"]:
            raise ValueError("Accept this collaboration before syncing it.")
        url = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"
        body = {
            "title": t["title"],
            "notes": "PeopleDesk " + t["id"] + "\n" + t["source"],
            "due": t["due"] + "T00:00:00.000Z",
            "status": "completed" if t["status"] == "Done" else "needsAction",
        }
        return write(
            db,
            u,
            t["id"],
            "Google Tasks",
            lambda bearer: providers.remote(url, "POST", body, token=bearer),
            lambda bearer, rid: providers.remote(
                url + "/" + urllib.parse.quote(rid, safe=""),
                "PATCH",
                body,
                token=bearer,
            ),
        )
    if op == "cloud-digest":
        ts = rows(
            db,
            "SELECT title,due FROM tasks WHERE owner=? AND status<>'Done' ORDER BY due LIMIT 30",
            (pid,),
        )
        body = (
            "Hello "
            + u["name"]
            + ",\n\nYour current assigned work\n\n"
            + "\n".join(t["title"] + " · due " + t["due"] for t in ts)
            + "\n\nPeopleDesk"
        )
        raw = base64.urlsafe_b64encode(
            providers.mail_bytes(
                {
                    "to": u["email"],
                    "subject": "Your PeopleDesk work plan",
                    "message": body,
                }
            )
        ).decode()
        return write(
            db,
            u,
            "digest-" + day(),
            "Gmail",
            lambda bearer: providers.remote(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                "POST",
                {"raw": raw},
                token=bearer,
            ),
        )
    if op == "cloud-meeting":
        e = one(db, "SELECT * FROM events WHERE id=? AND cancelled=0", (d.get("id"),))
        if not e or pid not in json.loads(e["people"]):
            raise PermissionError("You must attend the meeting to sync it.")
        if e["source"] == "Approved meeting":
            r = one(db, "SELECT status FROM requests WHERE id=?", (e["id"],))
            if not r or r["status"] != "Approved":
                raise ValueError("Approve the meeting first.")
        eid = hashlib.sha256((pid + "|" + e["id"]).encode()).hexdigest()
        body = {
            "id": eid,
            "summary": e["title"],
            "start": {"dateTime": e["starts"] + ":00Z"},
            "end": {"dateTime": e["ends"] + ":00Z"},
            "description": "PeopleDesk " + e["id"],
        }
        if e["link"]:
            body["location"] = e["link"]

        def create(bearer):
            try:
                return providers.remote(providers.G_EVENTS, "POST", body, token=bearer)
            except urllib.error.HTTPError as exc:
                if exc.code != 409:
                    raise
                return providers.remote(providers.G_EVENTS + "/" + eid, token=bearer)

        return write(
            db,
            u,
            e["id"],
            "Google Calendar",
            create,
            lambda bearer, rid: providers.remote(
                providers.G_EVENTS + "/" + urllib.parse.quote(rid, safe=""),
                "PATCH",
                {k: v for k, v in body.items() if k != "id"},
                token=bearer,
            ),
        )
    raise ValueError("Unknown connection action.")


def write(db, u, obj, provider, fn, update=None):
    with bound(db, u["id"]):
        bearer = token(db)
        db.execute("BEGIN IMMEDIATE")
        old = one(
            db,
            "SELECT state,remote_id FROM cloud_jobs WHERE person=? AND object=? AND provider=?",
            (u["id"], obj, provider),
        )
        if old:
            if not update or old["state"] != "Completed" or not old["remote_id"]:
                db.rollback()
                raise ValueError(
                    "This sync is already recorded. Check its status before repeating it."
                )
            db.execute(
                "UPDATE cloud_jobs SET state='In progress' WHERE person=? AND object=? AND provider=?",
                (u["id"], obj, provider),
            )
        else:
            db.execute(
                "INSERT INTO cloud_jobs VALUES(?,?,?,'In progress',NULL,'')",
                (u["id"], obj, provider),
            )
        db.commit()
        try:
            response = update(bearer, old["remote_id"]) if old else fn(bearer)
        except Exception:
            with db:
                db.execute(
                    "UPDATE cloud_jobs SET state='Verify with provider',detail='Check your provider account before retrying' WHERE person=? AND object=? AND provider=?",
                    (u["id"], obj, provider),
                )
            raise ValueError("Provider completion is uncertain. Check your account.")
        verb = "Updated in " if old else "Created in "
        with db:
            db.execute(
                "UPDATE cloud_jobs SET state='Completed',remote_id=?,detail=? WHERE person=? AND object=? AND provider=?",
                (response["id"], verb + provider, u["id"], obj, provider),
            )
        return {"message": verb + provider}
