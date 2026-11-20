"""PeopleDesk Windows launcher and same-origin local web service."""

import argparse
from contextlib import closing
from email.utils import formatdate
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import assistant_hr as ai
import providers
import company
import messaging
import cloud
import copilot
import routines
from records import *
from service import change, external, hr, state

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "web"


class App:
    def __init__(self, path, demo, origin):
        self.path = path
        self.demo = demo
        self.origin = origin.rstrip("/")
        self.cookie = "pd_demo" if demo else "pd_company"
        self.sessions = {}
        self.oauth = {}
        self.failures = {}
        self.attempts = {}
        self.lock = threading.Lock()
        init(path, demo)
        with closing(connect(path)) as db, db:
            company.migrate(db)
            messaging.migrate(db)
            copilot.migrate(db)
            routines.migrate(db)
            db.execute(
                "UPDATE cloud_jobs SET state='Verify with provider',detail='App restarted before outcome was recorded' WHERE state='In progress'"
            )
            self.setup_token = (
                secrets.token_urlsafe(32)
                if not one(db, "SELECT id FROM people")
                else ""
            )
            db.execute(
                "UPDATE actions SET status='Verify with provider',details='App restarted before outcome was recorded' WHERE status='In progress'"
            )

    def session(self, token):
        with self.lock:
            s = self.sessions.get(token)
            if not s or s[1] < time.time():
                return None
            return s[0]

    def login(self, pid, old):
        with self.lock:
            self.sessions.pop(old, None)
            now = time.time()
            self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
            token = secrets.token_urlsafe(40)
            self.sessions[token] = (pid, now + 28800)
            return token


class Handler(BaseHTTPRequestHandler):
    server_version = "PeopleDesk"

    def log_message(self, *a):
        pass

    @property
    def app(self):
        return self.server.app

    def token(self):
        c = SimpleCookie()
        c.load(self.headers.get("Cookie", ""))
        v = c.get(self.app.cookie)
        return v.value if v else ""

    def sendbody(self, status, body, mime, headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        for k, v in {
            "Content-Type": mime,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        }.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def reply(self, data, status=200, headers=None):
        self.sendbody(
            status,
            json.dumps(data, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
            headers,
        )

    def user(self, db):
        pid = self.app.session(self.token())
        if not pid:
            raise PermissionError("Sign in to your workspace.")
        return company.enrich(db, person(db, pid))

    def allowed_host(self):
        return (
            self.headers.get("Host", "").casefold()
            == urllib.parse.urlsplit(self.app.origin).netloc.casefold()
        )

    def do_GET(self):
        if not self.allowed_host():
            return self.reply({"error": "Invalid host"}, 403)
        parsed = urllib.parse.urlsplit(self.path)
        try:
            with closing(connect(self.app.path)) as db:
                if parsed.path == "/api/info":
                    return self.reply(
                        {
                            "product": "PeopleDesk",
                            "version": "3.0",
                            "demo": self.app.demo,
                            "company": one(db, "SELECT v FROM meta WHERE k='company'")[
                                "v"
                            ],
                            "signed": bool(self.app.session(self.token())),
                            "setup": bool(self.app.setup_token),
                            "google": cloud.connection(db, "")["googleConfigured"],
                        }
                    )
                if parsed.path == "/api/state":
                    u = self.user(db)
                    result = company.augment(db, u, state(db, u))
                    result["integrations"] = cloud.connection(db, u["id"])
                    return self.reply(result)
                if parsed.path == "/oauth/account":
                    return cloud.callback(self, db, urllib.parse.parse_qs(parsed.query))
                if parsed.path.startswith("/export/"):
                    user = self.user(db)
                    parts = parsed.path.split("/")
                    if len(parts) != 4:
                        raise ValueError("Unknown export.")
                    kind, rid = parts[2:]
                    if kind == "shared":
                        f = one(db, "SELECT * FROM shared_files WHERE id=?", (rid,))
                        if not f or (
                            f["owner"] != user["id"]
                            and f["audience"] not in ("company", "team:" + user["team"])
                        ):
                            raise PermissionError("File unavailable.")
                        return self.sendbody(
                            200,
                            f["body"],
                            "application/octet-stream",
                            {
                                "Content-Disposition": "attachment; filename*=UTF-8''"
                                + urllib.parse.quote(f["name"], safe="")
                            },
                        )
                    if kind == "document":
                        hr(user)
                        doc = one(
                            db,
                            "SELECT filename,attachment FROM flow_notes WHERE id=?",
                            (rid,),
                        )
                        if not doc or not doc["attachment"]:
                            raise ValueError("Document unavailable.")
                        return self.sendbody(
                            200,
                            doc["attachment"],
                            "application/octet-stream",
                            {
                                "Content-Disposition": "attachment; filename*=UTF-8''"
                                + urllib.parse.quote(doc["filename"], safe="")
                            },
                        )
                    if kind == "meeting":
                        e = one(
                            db,
                            "SELECT * FROM events WHERE id=? AND cancelled=0",
                            (rid,),
                        )
                        if not e or (
                            user["role"] != "hr"
                            and user["id"] not in json.loads(e["people"])
                        ):
                            raise PermissionError("Event unavailable.")
                        return self.sendbody(
                            200,
                            providers.calendar_bytes(e),
                            "text/calendar",
                            {
                                "Content-Disposition": 'attachment; filename="meeting.ics"'
                            },
                        )
                    if kind == "email":
                        hr(user)
                        r = one(
                            db,
                            "SELECT body FROM requests WHERE id=? AND kind='Email' AND status='Approved'",
                            (rid,),
                        )
                        if not r:
                            raise ValueError(
                                "Approve the email draft before exporting."
                            )
                        return self.sendbody(
                            200,
                            providers.mail_bytes(json.loads(r["body"])),
                            "message/rfc822",
                            {
                                "Content-Disposition": 'attachment; filename="approved-draft.eml"'
                            },
                        )
                files = {
                    "/": "index.html",
                    "/employee": "index.html",
                    "/join": "index.html",
                    "/style.css": "style.css",
                    "/app.js": "app.js",
                    "/company.js": "company.js",
                    "/messages.js": "messages.js",
                    "/company.css": "company.css",
                    "/copilot.js": "copilot.js",
                    "/copilot.css": "copilot.css",
                    "/manifest.webmanifest": "manifest.webmanifest",
                    "/sw.js": "sw.js",
                    "/app-icon.svg": "app-icon.svg",
                }
                if parsed.path not in files:
                    return self.reply({"error": "Not found"}, 404)
                name = files[parsed.path]
                self.sendbody(
                    200,
                    (ASSETS / name).read_bytes(),
                    {
                        ".html": "text/html",
                        ".css": "text/css",
                        ".js": "application/javascript",
                        ".webmanifest": "application/manifest+json",
                        ".svg": "image/svg+xml",
                    }[Path(name).suffix]
                    + "; charset=utf-8",
                )
        except Exception as e:
            self.failure(e)

    def failure(self, e):
        if isinstance(e, (BrokenPipeError, ConnectionResetError)):
            return
        if isinstance(e, PermissionError):
            return self.reply({"error": str(e)}, 403)
        if isinstance(e, sqlite3.IntegrityError):
            return self.reply(
                {
                    "error": "That entry already exists or references an unavailable record."
                },
                409,
            )
        if isinstance(e, (ValueError, TypeError, KeyError, RuntimeError)):
            return self.reply({"error": str(e)[:350]}, 400)
        if isinstance(e, (OSError, TimeoutError)):
            return self.reply(
                {
                    "error": "The local service or provider is unavailable. Check the connection and try again."
                },
                503,
            )
        self.reply({"error": "The operation could not be completed."}, 500)

    def cookieheader(self, token, secs):
        return {
            "Set-Cookie": f"{self.app.cookie}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={secs}"
            + ("; Secure" if self.app.origin.startswith("https:") else "")
        }

    def do_POST(self):
        if not self.allowed_host() or self.headers.get("Origin") != self.app.origin:
            return self.reply(
                {"error": "Use the workspace that opened this page."}, 403
            )
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected JSON.")
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > (
                7100000
                if self.path in ("/api/flow-note", "/api/share-file")
                else 160000
            ):
                raise ValueError("This request exceeds the input limit.")
            d = json.loads(self.rfile.read(n))
            op = self.path.removeprefix("/api/")
            if not isinstance(d, dict):
                raise ValueError("Expected an object.")
            with closing(connect(self.app.path)) as db:
                if op in ("login", "register", "google-login", "workspace-setup"):
                    # Shared-host limits are intentionally generous for team onboarding.
                    client = self.client_address[0]
                    with self.app.lock:
                        now = time.time()
                        self.app.attempts = {
                            k: v for k, v in self.app.attempts.items() if v[1] > now
                        }
                        count, expiry = self.app.attempts.get(client, (0, now + 60))
                        if count >= 120:
                            raise PermissionError(
                                "Too many requests. Wait one minute before trying again."
                            )
                        self.app.attempts[client] = (count + 1, expiry)
                if op == "workspace-setup":
                    if not self.app.setup_token or not secrets.compare_digest(
                        d.get("setup_token", ""), self.app.setup_token
                    ):
                        raise PermissionError(
                            "Open the setup link launched on the company host."
                        )
                    pw = text(d.get("password"), "Password", 128)
                    if len(pw) < 12:
                        raise ValueError("Use at least 12 characters.")
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        if one(db, "SELECT id FROM people"):
                            raise ValueError("Workspace already configured.")
                        db.execute(
                            "UPDATE meta SET v=? WHERE k='company'",
                            (text(d.get("company"), "Company name", 100),),
                        )
                        pid = company.new_person(
                            db,
                            text(d.get("name"), "Name", 100),
                            email(d.get("email")),
                            password(pw),
                            "Leadership",
                            "Founder",
                            "owner",
                            None,
                        )
                    self.app.setup_token = ""
                    return self.reply(
                        {"ok": True},
                        headers=self.cookieheader(
                            self.app.login(pid, self.token()), 28800
                        ),
                    )
                if op == "register":
                    if self.app.setup_token:
                        raise ValueError(
                            "The company administrator must finish setup first."
                        )
                    if self.app.demo:
                        raise ValueError("Open company mode for registration.")
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        result = company.register(db, d)
                    return self.reply(result)
                if op == "google-login":
                    if self.app.demo:
                        raise ValueError("Use company mode for Google sign-in.")
                    return cloud.start(self, db, "login")
                if op == "login":
                    if self.app.demo and d.get("demo") in (
                        "hr",
                        "employee",
                        "manager",
                        "lead",
                        "people",
                    ):
                        pid = {
                            "hr": "E001",
                            "employee": "E002",
                            "manager": "E005",
                            "lead": "E003",
                            "people": "E006",
                        }[d["demo"]]
                    else:
                        addr = email(d.get("email"))
                        pw = text(d.get("password"), "Password", 128)
                        with self.app.lock:
                            prev = self.app.failures.get(addr, (0, 0))
                            if prev[0] >= 8 and prev[1] > time.time():
                                raise PermissionError(
                                    "Too many attempts. Try again in ten minutes."
                                )
                        p = one(db, "SELECT id,hash FROM people WHERE email=?", (addr,))
                        if not p or not check_password(pw, p["hash"]):
                            with self.app.lock:
                                self.app.failures[addr] = (
                                    (prev[0] if prev[1] > time.time() else 0) + 1,
                                    time.time() + 600,
                                )
                            raise PermissionError(
                                "The email or password did not match."
                            )
                        with self.app.lock:
                            self.app.failures.pop(addr, None)
                        pid = p["id"]
                    company.enrich(db, person(db, pid))
                    return self.reply(
                        {"ok": True},
                        headers=self.cookieheader(
                            self.app.login(pid, self.token()), 28800
                        ),
                    )
                if op == "logout":
                    with self.app.lock:
                        self.app.sessions.pop(self.token(), None)
                    return self.reply({"ok": True}, headers=self.cookieheader("", 0))
                u = self.user(db)
                if op in messaging.OPS:
                    with db:
                        if op not in ("messages-state", "messages-read"):
                            db.execute("BEGIN IMMEDIATE")
                        return self.reply(messaging.handle(db, u, op, d))
                if op == "cloud-connect":
                    if self.app.demo:
                        raise ValueError("Connect real accounts in company mode.")
                    return cloud.start(self, db, "connect")
                if op in (
                    "provider-config",
                    "cloud-refresh",
                    "cloud-disconnect",
                    "cloud-task",
                    "cloud-digest",
                    "cloud-meeting",
                    "cloud-test-zoom",
                ):
                    if self.app.demo:
                        raise ValueError("Connect real accounts in company mode.")
                    return self.reply(cloud.run(db, u, op, d))
                if op == "stop-local":
                    hr(u)
                    if not self.app.origin.startswith("http://127.0.0.1:"):
                        raise PermissionError("Stop the shared service from its host.")
                    self.reply(
                        {
                            "message": "Local service stopped. Reopen PeopleDesk to continue."
                        }
                    )
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if op == "change-password":
                    if self.app.demo:
                        raise ValueError("Use company mode to change credentials.")
                    new = text(d.get("new"), "New password", 128)
                    if len(new) < 12:
                        raise ValueError("Use 12 to 128 characters.")
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        stored = one(
                            db, "SELECT hash FROM people WHERE id=?", (u["id"],)
                        )["hash"]
                        if not check_password(
                            text(d.get("current"), "Current password", 128), stored
                        ):
                            raise PermissionError("Current password did not match.")
                        db.execute(
                            "UPDATE people SET hash=? WHERE id=?",
                            (password(new), u["id"]),
                        )
                    with self.app.lock:
                        self.app.sessions = {
                            k: v
                            for k, v in self.app.sessions.items()
                            if v[0] != u["id"]
                        }
                    return self.reply(
                        {"message": "Password updated. Sign in again."},
                        headers=self.cookieheader("", 0),
                    )
                if op == "chat":
                    return self.reply(
                        ai.chat(db, u, text(d.get("q"), "Question", 1000))
                    )
                if op in copilot.OPS:
                    return self.reply(copilot.handle(db, u, op, d))
                if op == "routine-list":
                    return self.reply(routines.snapshot(db, u))
                if op == "routine-toggle":
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        result = routines.toggle(db, u, d)
                    return self.reply(result)
                if op == "draft":
                    return self.reply(
                        ai.draft_mail(
                            text(d.get("brief"), "Email instructions", 1500),
                            email(d.get("to")),
                        )
                    )
                if op == "external":
                    with cloud.bound(db, u["id"]):
                        return self.reply(external(db, u, d))
                token = text(d.get("token"), "Request identifier", 100)
                # The cached result makes a retry safe even after a browser timeout.
                lookup = lambda: one(
                    db,
                    "SELECT result,op FROM commands WHERE actor=? AND token=?",
                    (u["id"], token),
                )
                cached = lookup()
                if cached:
                    if cached["op"] != op:
                        raise ValueError("This request ID belongs to another action.")
                    return self.reply(json.loads(cached["result"]))
                payload = d
                if op == "handoff":
                    hr(u)
                    payload = ai.handoff(text(d.get("notes"), "Notes", 6000))
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    cached = lookup()
                    if cached:
                        if cached["op"] != op:
                            raise ValueError("Request ID conflict.")
                        return self.reply(json.loads(cached["result"]))
                    if op == "save-handoff":
                        raise ValueError("Use the local model to build the handoff.")
                    if op == "task-status":
                        res = company.handle(db, u, "task-progress", payload)
                    elif op in company.OPS:
                        res = company.handle(db, u, op, payload)
                    else:
                        res = change(
                            db, u, "save-handoff" if op == "handoff" else op, payload
                        )
                    db.execute(
                        "INSERT INTO commands VALUES(?,?,?,?)",
                        (u["id"], token, op, json.dumps(res)),
                    )
                self.reply(res)
        except Exception as e:
            self.failure(e)


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        if hasattr(self, "stop_routines"):
            self.stop_routines.set()
            self.routine_worker.join(timeout=25)
        super().server_close()


def runserver(path, demo, port, origin=None):
    server = WorkspaceServer(("127.0.0.1", port), Handler)
    server.app = App(
        path, demo, origin or "http://127.0.0.1:" + str(server.server_port)
    )
    server.stop_routines = threading.Event()

    def run_routines():
        while not server.stop_routines.wait(30):
            try:
                routines.tick(path)
            except (sqlite3.Error, ValueError, PermissionError):
                pass

    server.routine_worker = threading.Thread(target=run_routines, daemon=True)
    server.routine_worker.start()
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--employee", action="store_true")
    args = parser.parse_args()
    demo = not (args.company or args.setup)
    folder = Path(
        os.environ.get("PEOPLEDESK_DATA")
        or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PeopleDesk"
    )
    path = folder / ("demo.db" if demo else "company.db")
    port = int(os.environ.get("PEOPLEDESK_PORT") or (8878 if demo else 8879))
    local = f"http://127.0.0.1:{port}"
    origin = os.environ.get("PEOPLEDESK_ORIGIN", local) if not demo else local
    if origin != local and (
        not origin.startswith("https://") or urllib.parse.urlsplit(origin).path
    ):
        raise ValueError(
            "The reverse proxy origin must be an HTTPS origin with no path."
        )
    try:
        server = runserver(path, demo, port, origin)
    except OSError:
        with urllib.request.urlopen(origin + "/api/info", timeout=3) as r:
            identity = json.load(r)
        if identity.get("product") != "PeopleDesk" or identity.get("demo") != demo:
            raise ValueError("The workspace port is already in use.")
        if identity.get("version") != "3.0":
            raise ValueError(
                "An earlier PeopleDesk service is using this port. Use Stop local service in its workspace, then reopen PeopleDesk 3."
            )
        if not args.no_browser:
            webbrowser.open(origin + ("/employee" if args.employee else "/#assistant"))
        return
    if not args.no_browser:
        suffix = (
            "#setup=" + server.app.setup_token
            if server.app.setup_token
            else "/employee" if args.employee else "/#assistant"
        )
        webbrowser.open(origin + suffix)
    if sys.stdout:
        print("PeopleDesk is running at " + origin, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
