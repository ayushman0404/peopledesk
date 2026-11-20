"""Local provider adapters. Writes run only after explicit HR approval and execution."""

import base64
import ctypes
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import timedelta
from email.message import EmailMessage
from email.policy import SMTP
from records import day, moment, one, rows, utcnow, key, audit


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise ValueError(
            "Windows credential protection is required for storing OAuth tokens."
        )
    data = bytes(data)
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    api = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    if not api(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dest)):
        raise ValueError("This Windows user cannot open the provider credentials.")
    try:
        return ctypes.string_at(dest.pbData, dest.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.pbData)


def remote(url, method="GET", data=None, token=None, basic=None, form=False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if basic:
        headers["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    if data is not None:
        payload = (
            urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        )
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form else "application/json"
        )
    else:
        payload = None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def setting(k):
    return os.environ.get("PEOPLEDESK_" + k, "").strip()


def configured():
    return {
        "google": all(setting(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")),
        "zoom": all(
            setting(k)
            for k in (
                "ZOOM_ACCOUNT_ID",
                "ZOOM_CLIENT_ID",
                "ZOOM_CLIENT_SECRET",
                "ZOOM_HOST",
            )
        ),
    }


GOOGLE_SCOPES = "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/calendar.events.owned"


def google_url(callback):
    verifier = secrets.token_urlsafe(60)
    state = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    q = dict(
        client_id=setting("GOOGLE_CLIENT_ID"),
        redirect_uri=callback,
        response_type="code",
        scope=GOOGLE_SCOPES,
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return (
        "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q),
        state,
        verifier,
    )


def exchange(db, code, verifier, callback):
    tokens = remote(
        "https://oauth2.googleapis.com/token",
        "POST",
        dict(
            client_id=setting("GOOGLE_CLIENT_ID"),
            client_secret=setting("GOOGLE_CLIENT_SECRET"),
            redirect_uri=callback,
            grant_type="authorization_code",
            code=code,
            code_verifier=verifier,
        ),
        form=True,
    )
    if not tokens.get("refresh_token"):
        raise ValueError(
            "Google did not return an offline grant. Reconnect and consent."
        )
    if not set(GOOGLE_SCOPES.split()) <= set(tokens.get("scope", "").split()):
        raise ValueError(
            "Both Calendar and Gmail permissions are needed for this connection."
        )
    db.execute(
        "INSERT OR REPLACE INTO secrets VALUES('google',?)",
        (protect(tokens["refresh_token"].encode()),),
    )


def google_token(db):
    record = one(db, "SELECT blob FROM secrets WHERE k='google'")
    if not record:
        raise ValueError("Connect Google in Integrations first.")
    refresh = protect(record["blob"], True).decode()
    data = dict(
        client_id=setting("GOOGLE_CLIENT_ID"),
        client_secret=setting("GOOGLE_CLIENT_SECRET"),
        grant_type="refresh_token",
        refresh_token=refresh,
    )
    return remote("https://oauth2.googleapis.com/token", "POST", data, form=True)[
        "access_token"
    ]


def zoom_token():
    if not configured()["zoom"]:
        raise ValueError("Configure the Zoom account in Integrations first.")
    return remote(
        "https://zoom.us/oauth/token",
        "POST",
        {"grant_type": "account_credentials", "account_id": setting("ZOOM_ACCOUNT_ID")},
        basic=setting("ZOOM_CLIENT_ID") + ":" + setting("ZOOM_CLIENT_SECRET"),
        form=True,
    )["access_token"]


def mail_bytes(b):
    msg = EmailMessage(policy=SMTP)
    msg["To"] = b["to"]
    msg["Subject"] = b["subject"]
    msg["X-Unsent"] = "1"
    msg.set_content(b["message"])
    return msg.as_bytes()


def calendar_bytes(event):
    def escape(s):
        return (
            s.replace("\\", "\\\\")
            .replace("\r", "")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    def stamp(s):
        return moment(s).strftime("%Y%m%dT%H%M00Z")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PeopleDesk//People Calendar//EN",
        "BEGIN:VEVENT",
        "UID:" + event["id"] + "@peopledesk.local",
        "DTSTAMP:" + utcnow().replace("-", "").replace(":", "") + "Z",
        "DTSTART:" + stamp(event["starts"]),
        "DTEND:" + stamp(event["ends"]),
        "SUMMARY:" + escape(event["title"]),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


G_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
G_DRAFTS = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"


def publish(db, request, channel):
    b = json.loads(request["body"])
    rid = request["id"]
    if channel == "Zoom":
        host = urllib.parse.quote(setting("ZOOM_HOST"), safe="")
        reply = remote(
            "https://api.zoom.us/v2/users/" + host + "/meetings",
            "POST",
            {
                "topic": b["title"],
                "type": 2,
                "start_time": b["starts"] + ":00Z",
                "duration": b["minutes"],
                "timezone": "UTC",
            },
            token=zoom_token(),
        )
        url = reply["join_url"]
        if not url.startswith("https://"):
            raise ValueError("Zoom returned no usable join link.")
        return str(reply["id"]), url
    token = google_token(db)
    if channel == "Gmail draft":
        draft = remote(
            G_DRAFTS,
            "POST",
            {"message": {"raw": base64.urlsafe_b64encode(mail_bytes(b)).decode()}},
            token,
        )
        return draft["id"], "Created in Gmail drafts"
    if channel == "Gmail send":
        draft = one(
            db,
            "SELECT provider_id FROM actions WHERE request=? AND channel='Gmail draft' AND status='Completed'",
            (rid,),
        )
        if not draft:
            raise ValueError("Create the Gmail draft before sending.")
        # Send the reviewed bytes even if somebody changed the mailbox draft.
        msg = {"raw": base64.urlsafe_b64encode(mail_bytes(b)).decode()}
        result = remote(
            G_DRAFTS + "/send",
            "POST",
            {"id": draft["provider_id"], "message": msg},
            token,
        )
        return result["id"], "Sent by Gmail"
    event = one(db, "SELECT * FROM events WHERE id=?", (rid,))
    if not event:
        raise ValueError("Local event is missing.")
    eid = hashlib.sha256(rid.encode()).hexdigest()
    invites = [
        {"email": one(db, "SELECT email FROM people WHERE id=?", (pid,))["email"]}
        for pid in b["people"]
    ]
    payload = {
        "id": eid,
        "summary": b["title"],
        "start": {"dateTime": b["starts"] + ":00Z"},
        "end": {"dateTime": b["ends"] + ":00Z"},
        "attendees": invites,
    }
    if event["link"]:
        payload["location"] = event["link"]
    try:
        result = remote(G_EVENTS + "?sendUpdates=all", "POST", payload, token)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise
        result = remote(G_EVENTS + "/" + eid, token=token)
    return result["id"], "Published to Google Calendar"


def pull_calendar(db, actor):
    from datetime import datetime, timezone

    token = google_token(db)
    query = {
        "timeMin": day() + "T00:00:00Z",
        "timeMax": day(31) + "T00:00:00Z",
        "singleEvents": "true",
        "maxResults": "250",
        "orderBy": "startTime",
    }
    fetched = {}

    def norm(obj):
        if "date" in obj:
            return obj["date"] + "T00:00"
        return (
            datetime.fromisoformat(obj["dateTime"].replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M")
        )

    while True:
        page = remote(G_EVENTS + "?" + urllib.parse.urlencode(query), token=token)
        for e in page.get("items", []):
            if e.get("status") != "cancelled":
                fetched[e["id"]] = (
                    e.get("summary") or "Busy",
                    norm(e["start"]),
                    norm(e["end"]),
                )
        if not page.get("nextPageToken"):
            break
        query["pageToken"] = page["nextPageToken"]
    # The HR account owns the imported calendar. Employee views only see local invitations.
    for ext, (title, start, end) in fetched.items():
        linked = one(
            db,
            "SELECT request FROM actions WHERE channel='Google Calendar' AND provider_id=? AND status='Completed'",
            (ext,),
        )
        if linked:
            db.execute(
                "UPDATE events SET starts=?,ends=?,title=?,cancelled=0 WHERE id=?",
                (start, end, title, linked["request"]),
            )
        else:
            db.execute(
                """INSERT INTO events(id,title,starts,ends,people,source,external) VALUES(?,?,?,?,?,'Google Calendar',?)
                ON CONFLICT(external) DO UPDATE SET title=excluded.title,starts=excluded.starts,ends=excluded.ends,cancelled=0""",
                (key("GC"), title, start, end, json.dumps([actor]), ext),
            )
    for e in rows(
        db,
        "SELECT id,external FROM events WHERE external IS NOT NULL AND starts>=? AND starts<?",
        (day(), day(31)),
    ):
        if e["external"] not in fetched:
            db.execute("UPDATE events SET cancelled=1 WHERE id=?", (e["id"],))
    audit(db, actor, "Refreshed Google calendar", str(len(fetched)) + " events")
    return len(fetched)
