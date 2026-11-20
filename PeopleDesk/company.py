"""Company membership, collaboration and registration with scoped permissions."""

import base64
import hashlib
import json
import secrets
import time
from records import *

ROLES = {
    "owner": "Founder / administrator",
    "hr": "People operations",
    "manager": "Manager / VP",
    "lead": "Team lead",
    "employee": "Team member",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles(person TEXT PRIMARY KEY REFERENCES people(id),access TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS invitations(token_hash TEXT PRIMARY KEY,email TEXT NOT NULL,access TEXT NOT NULL,team TEXT NOT NULL,title TEXT NOT NULL,manager TEXT REFERENCES people(id),expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS registrations(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE COLLATE NOCASE,hash TEXT,google_sub TEXT,team TEXT NOT NULL,title TEXT NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS identities(sub TEXT PRIMARY KEY,person TEXT NOT NULL REFERENCES people(id));
CREATE TABLE IF NOT EXISTS task_details(task TEXT PRIMARY KEY REFERENCES tasks(id),assigner TEXT NOT NULL REFERENCES people(id),description TEXT NOT NULL,priority TEXT NOT NULL,project TEXT NOT NULL,accepted INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS task_comments(id TEXT PRIMARY KEY,task TEXT NOT NULL REFERENCES tasks(id),author TEXT NOT NULL REFERENCES people(id),body TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shared_files(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES people(id),name TEXT NOT NULL,body BLOB NOT NULL,audience TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notices(id TEXT PRIMARY KEY,author TEXT NOT NULL REFERENCES people(id),title TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,person TEXT NOT NULL REFERENCES people(id),title TEXT NOT NULL,target TEXT NOT NULL,seen INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS personal_cloud(person TEXT NOT NULL REFERENCES people(id),provider TEXT NOT NULL,kind TEXT NOT NULL,remote_id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(person,provider,kind,remote_id));
CREATE TABLE IF NOT EXISTS cloud_jobs(person TEXT NOT NULL,object TEXT NOT NULL,provider TEXT NOT NULL,state TEXT NOT NULL,remote_id TEXT,detail TEXT NOT NULL DEFAULT '',PRIMARY KEY(person,object,provider));
"""


def migrate(db):
    db.executescript(SCHEMA)
    with db:
        db.execute(
            "INSERT OR IGNORE INTO meta VALUES('workspace_id',?)",
            (secrets.token_hex(16),),
        )
        db.execute(
            "INSERT OR IGNORE INTO profiles SELECT id,CASE role WHEN 'hr' THEN 'hr' ELSE 'employee' END,1 FROM people"
        )
        if not one(db, "SELECT person FROM profiles WHERE access='owner'"):
            first = one(
                db, "SELECT id FROM people WHERE role='hr' ORDER BY rowid LIMIT 1"
            )
            if first:
                db.execute(
                    "UPDATE profiles SET access='owner' WHERE person=?", (first["id"],)
                )
        if not one(db, "SELECT v FROM meta WHERE k='collaboration_seed'"):
            if one(db, "SELECT v FROM meta WHERE k='mode'")["v"] == "demo":
                db.executemany(
                    "UPDATE profiles SET access=? WHERE person=?",
                    [("manager", "E005"), ("lead", "E003"), ("hr", "E006")],
                )
                db.execute("UPDATE people SET role='hr' WHERE id='E006'")
                db.execute(
                    "UPDATE people SET manager='E005' WHERE team='Engineering' AND id<>'E005'"
                )
                db.execute(
                    "INSERT OR IGNORE INTO task_details SELECT id,'E001','Coordinate with your collaborator and record progress here.','Normal','People operations',1 FROM tasks"
                )
            db.execute("INSERT INTO meta VALUES('collaboration_seed','1')")


def enrich(db, u):
    p = one(db, "SELECT access,active FROM profiles WHERE person=?", (u["id"],))
    if p and not p["active"]:
        raise PermissionError("This company account is inactive.")
    u["access"] = p["access"] if p else ("hr" if u["role"] == "hr" else "employee")
    u["role"] = "hr" if u["access"] in ("owner", "hr") else "employee"
    return u


def administrator(u):
    if u.get("access") != "owner":
        raise PermissionError("A company administrator must perform this action.")


def manager(u):
    return u.get("access") in ("owner", "hr", "manager", "lead")


def manages(u, p):
    return u.get("access") in ("owner", "hr") or (
        u.get("access") in ("manager", "lead")
        and (p["manager"] == u["id"] or p["team"] == u["team"])
    )


def visible_task(db, u, tid):
    t = one(db, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t or (
        u["id"] not in (t["owner"], t["helper"])
        and not manages(u, person(db, t["owner"]))
        and not one(
            db,
            "SELECT task FROM task_details WHERE task=? AND assigner=?",
            (tid, u["id"]),
        )
    ):
        raise PermissionError("This task is outside your workspace.")
    return t


def notify(db, pid, title, target):
    db.execute(
        "INSERT INTO notifications VALUES(?,?,?,?,0,?)",
        (key("N"), pid, title, target, utcnow()),
    )


def augment(db, u, s):
    pid = u["id"]
    for p in s["people"]:
        profile = one(
            db, "SELECT access,active FROM profiles WHERE person=?", (p["id"],)
        ) or {"access": "employee", "active": 1}
        p.update(profile)
    if manager(u):
        ids = [
            p["id"]
            for p in rows(db, "SELECT id,team,manager FROM people")
            if manages(u, p)
        ]
        visible = set(ids + [pid])
        all_tasks = rows(db, "SELECT * FROM tasks ORDER BY due,id")
        s["tasks"] = [
            t
            for t in all_tasks
            if t["owner"] in visible
            or t["helper"] == pid
            or one(
                db,
                "SELECT task FROM task_details WHERE task=? AND assigner=?",
                (t["id"], pid),
            )
        ]
    else:
        additional = rows(
            db,
            "SELECT t.* FROM tasks t JOIN task_details d ON d.task=t.id WHERE d.assigner=?",
            (pid,),
        )
        s["tasks"] = list({t["id"]: t for t in s["tasks"] + additional}.values())
    for t in s["tasks"]:
        extra = one(db, "SELECT * FROM task_details WHERE task=?", (t["id"],))
        t.update(
            extra
            or {
                "assigner": None,
                "description": "",
                "priority": "Normal",
                "project": t["source"],
                "accepted": 1,
            }
        )
        t["comments"] = rows(
            db,
            "SELECT * FROM task_comments WHERE task=? ORDER BY created LIMIT 200",
            (t["id"],),
        )
    # Personal provider calendars remain private even to company administrators.
    s["events"] = [
        e
        for e in s["events"]
        if not e["source"].startswith("Google Calendar") or pid in e["people"]
    ]
    s["workspace_id"] = one(db, "SELECT v FROM meta WHERE k='workspace_id'")["v"]
    s["roles"] = ROLES
    s["notifications"] = rows(
        db,
        "SELECT * FROM notifications WHERE person=? ORDER BY created DESC LIMIT 60",
        (pid,),
    )
    s["announcements"] = rows(
        db, "SELECT * FROM notices ORDER BY created DESC LIMIT 30"
    )
    s["files"] = [
        f
        for f in rows(
            db,
            "SELECT id,owner,name,audience,created,length(body) size FROM shared_files ORDER BY created DESC",
        )
        if f["owner"] == pid
        or f["audience"] == "company"
        or f["audience"] == "team:" + u["team"]
    ]
    s["registrations"] = (
        rows(
            db,
            "SELECT id,name,email,team,title,state,created FROM registrations WHERE state='Pending' ORDER BY created",
        )
        if u["role"] == "hr"
        else []
    )
    s["cloud"] = [
        {**r, "body": json.loads(r["body"])}
        for r in rows(
            db,
            "SELECT provider,kind,remote_id,body FROM personal_cloud WHERE person=?",
            (pid,),
        )
    ]
    s["cloud_jobs"] = rows(
        db, "SELECT object,provider,state,detail FROM cloud_jobs WHERE person=?", (pid,)
    )
    from datetime import datetime, timezone

    def calendar_time(v):
        raw = v.get("dateTime") or v.get("date")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M")

    for row in s["cloud"]:
        if row["kind"] != "calendar":
            continue
        event = row["body"]
        if event.get("status") == "cancelled":
            continue
        starts = calendar_time(event.get("start", {}))
        ends = calendar_time(event.get("end", {}))
        if not starts or not ends:
            continue
        s["events"].append(
            {
                "id": "google-" + row["remote_id"],
                "title": event.get("summary") or "Busy",
                "starts": starts,
                "ends": ends,
                "people": [pid],
                "source": "My Google Calendar",
                "link": event.get("hangoutLink") or event.get("htmlLink") or "",
                "remote": True,
                "all_day": bool(event.get("start", {}).get("date")),
            }
        )
    s["events"].sort(key=lambda e: e["starts"])
    return s


def new_person(db, name, addr, pw, team, title, access, manager_id, google_sub=None):
    if access not in ROLES:
        raise ValueError("Choose a valid role.")
    pid = key("EMP")
    if manager_id:
        person(db, manager_id)
    db.execute(
        "INSERT INTO people(id,name,email,team,title,role,manager,start,location,hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            pid,
            name,
            addr,
            team,
            title,
            "hr" if access in ("owner", "hr") else "employee",
            manager_id,
            day(),
            "",
            pw,
        ),
    )
    db.execute("INSERT INTO profiles VALUES(?,?,1)", (pid, access))
    if google_sub:
        db.execute("INSERT INTO identities VALUES(?,?)", (google_sub, pid))
    return pid


def register(db, d, verified=None):
    name = text(d.get("name"), "Full name", 100)
    addr = email(verified["email"] if verified else d.get("email")).lower()
    if one(db, "SELECT id FROM people WHERE email=?", (addr,)):
        raise ValueError(
            "An account already exists. Sign in or ask your administrator for access."
        )
    pw = None
    if not verified:
        pw = text(d.get("password"), "Password", 128)
        if len(pw) < 12:
            raise ValueError("Use at least 12 characters.")
        pw = password(pw)
    invitation = d.get("invitation", "")
    if invitation:
        h = hashlib.sha256(invitation.encode()).hexdigest()
        inv = one(
            db,
            "SELECT * FROM invitations WHERE token_hash=? AND used=0 AND expires>?",
            (h, int(time.time())),
        )
        if not inv or inv["email"].casefold() != addr.casefold():
            raise ValueError(
                "Invitation is invalid, expired or for a different email address."
            )
        pid = new_person(
            db,
            name,
            addr,
            pw,
            inv["team"],
            inv["title"],
            inv["access"],
            inv["manager"],
            verified["sub"] if verified else None,
        )
        db.execute("UPDATE invitations SET used=1 WHERE token_hash=?", (h,))
        audit(db, pid, "Joined with invitation", pid)
        return {"id": pid}
    rid = key("JOIN")
    db.execute(
        "INSERT INTO registrations VALUES(?,?,?,?,?,?,?,'Pending',?)",
        (
            rid,
            name,
            addr,
            pw,
            verified["sub"] if verified else None,
            text(d.get("team") or "Unassigned", "Team", 100),
            text(d.get("title") or "Team member", "Job title", 100),
            utcnow(),
        ),
    )
    return {
        "message": "Your registration is awaiting company approval. Sign in after your administrator approves it."
    }


def handle(db, u, op, d):
    pid = u["id"]
    if op == "leave-adjust":
        if u["role"] != "hr":
            raise PermissionError("HR must review leave ledger adjustments.")
        target = person(db, d.get("id"))
        amount = int(d.get("days", 0))
        if not -365 <= amount <= 365 or amount == 0:
            raise ValueError(
                "Enter a whole number of days between -365 and 365, excluding zero."
            )
        reason = text(d.get("reason"), "Adjustment reason", 300)
        balance = one(
            db,
            "SELECT coalesce(SUM(days),0) balance FROM ledger WHERE person=?",
            (target["id"],),
        )["balance"]
        if balance + amount < 0:
            raise ValueError("The adjustment would make the leave balance negative.")
        adjustment = key("LEDGER")
        db.execute(
            "INSERT INTO ledger VALUES(?,?,?,?,?,NULL)",
            (adjustment, target["id"], amount, reason, utcnow()),
        )
        audit(db, pid, "Leave ledger adjusted", adjustment)
        notify(
            db,
            target["id"],
            "Your leave ledger was adjusted: " + str(amount) + " days · " + reason,
            "overview",
        )
        return {
            "message": "Leave ledger updated. New balance: "
            + str(balance + amount)
            + " working days."
        }
    if op == "invite":
        if u["role"] != "hr":
            raise PermissionError("Ask HR to invite a company member.")
        access = d.get("access", "employee")
        if access in ("owner", "hr") and u["access"] != "owner":
            raise PermissionError(
                "Only an administrator can grant HR or administrator access."
            )
        if access not in ROLES:
            raise ValueError("Choose a role.")
        token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO invitations VALUES(?,?,?,?,?,?,?,0)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                email(d.get("email")).lower(),
                access,
                text(d.get("team"), "Team", 100),
                text(d.get("title"), "Title", 100),
                d.get("manager") or pid,
                int(time.time()) + 7 * 86400,
            ),
        )
        return {"invitation": token, "email": d["email"]}
    if op == "membership":
        if u["role"] != "hr":
            raise PermissionError("HR approval is required.")
        r = one(
            db,
            "SELECT * FROM registrations WHERE id=? AND state='Pending'",
            (d.get("id"),),
        )
        if not r:
            raise ValueError("Registration was already reviewed.")
        decision = d.get("decision")
        if decision not in ("Approved", "Declined"):
            raise ValueError("Choose a decision.")
        if decision == "Approved":
            access = d.get("access", "employee")
            if access in ("hr", "owner") and u["access"] != "owner":
                raise PermissionError("Only an administrator can grant this role.")
            created = new_person(
                db,
                r["name"],
                r["email"],
                r["hash"],
                r["team"],
                r["title"],
                access,
                d.get("manager") or pid,
                r["google_sub"],
            )
            notify(db, created, "Your company account is ready", "overview")
        db.execute(
            "UPDATE registrations SET state=?,hash=NULL WHERE id=?", (decision, r["id"])
        )
        audit(db, pid, "Registration " + decision, r["id"])
        return {}
    if op == "member-access":
        administrator(u)
        target = person(db, d.get("id"))
        access = d.get("access")
        active = d.get("active", True) in (True, 1, "1")
        if access not in ROLES:
            raise ValueError("Choose a valid role.")
        if target["id"] == pid and (access != "owner" or not active):
            raise ValueError(
                "Keep your current administrator access while managing the workspace."
            )
        db.execute(
            "INSERT INTO profiles VALUES(?,?,?) ON CONFLICT(person) DO UPDATE SET access=excluded.access,active=excluded.active",
            (target["id"], access, int(active)),
        )
        db.execute(
            "UPDATE people SET team=?,title=?,manager=?,role=? WHERE id=?",
            (
                text(d.get("team"), "Team", 100),
                text(d.get("title"), "Title", 100),
                d.get("manager") or None,
                "hr" if access in ("owner", "hr") else "employee",
                target["id"],
            ),
        )
        audit(db, pid, "Changed member access", target["id"])
        return {}
    if op == "assign":
        owner = person(db, d.get("owner"))
        helper = person(db, d["helper"])["id"] if d.get("helper") else None
        if helper == owner["id"]:
            raise ValueError("Choose a different collaborator.")
        direct = owner["id"] == pid or manages(u, owner)
        tid = key("TASK")
        title = text(d.get("title"), "Task", 180)
        priority = d.get("priority", "Normal")
        if priority not in ("Low", "Normal", "High"):
            raise ValueError("Choose a priority.")
        db.execute(
            "INSERT INTO tasks(id,title,owner,helper,due,status,source) VALUES(?,?,?,?,?,'Open',?)",
            (
                tid,
                title,
                owner["id"],
                helper,
                iso(d.get("due")),
                "Assigned by " + u["name"],
            ),
        )
        db.execute(
            "INSERT INTO task_details VALUES(?,?,?,?,?,?)",
            (
                tid,
                pid,
                str(d.get("description", ""))[:3000],
                priority,
                str(d.get("project", ""))[:100],
                int(direct),
            ),
        )
        for recipient in {owner["id"], helper} - {None, pid}:
            notify(
                db,
                recipient,
                ("New task" if direct else "Collaboration invitation") + ": " + title,
                tid,
            )
        audit(db, pid, "Assigned task" if direct else "Proposed collaboration", tid)
        return {"id": tid}
    if op == "accept-task":
        t = visible_task(db, u, d.get("id"))
        if t["owner"] != pid:
            raise PermissionError("The responsible employee must accept this task.")
        db.execute("UPDATE task_details SET accepted=1 WHERE task=?", (t["id"],))
        return {}
    if op == "task-comment":
        t = visible_task(db, u, d.get("id"))
        db.execute(
            "INSERT INTO task_comments VALUES(?,?,?,?,?)",
            (
                key("COMMENT"),
                t["id"],
                pid,
                text(d.get("body"), "Progress update", 2000),
                utcnow(),
            ),
        )
        return {}
    if op == "task-progress":
        t = visible_task(db, u, d.get("id"))
        extra = one(db, "SELECT accepted FROM task_details WHERE task=?", (t["id"],))
        if extra and not extra["accepted"]:
            raise ValueError(
                "The responsible employee must accept the collaboration first."
            )
        status = d.get("status")
        if status not in ("Open", "In progress", "Blocked", "Done"):
            raise ValueError("Choose a supported status.")
        db.execute("UPDATE tasks SET status=? WHERE id=?", (status, t["id"]))
        audit(db, pid, "Task " + status, t["id"])
        return {}
    if op == "publish-notice":
        if not manager(u):
            raise PermissionError(
                "A lead or manager can publish company announcements."
            )
        db.execute(
            "INSERT INTO notices VALUES(?,?,?,?,?)",
            (
                key("NOTICE"),
                pid,
                text(d.get("title"), "Title", 180),
                text(d.get("body"), "Announcement", 4000),
                utcnow(),
            ),
        )
        return {}
    if op == "read-notifications":
        db.execute("UPDATE notifications SET seen=1 WHERE person=?", (pid,))
        return {}
    if op == "share-file":
        name = text(d.get("filename"), "Filename", 180)
        raw = base64.b64decode(d.get("attachment", ""), validate=True)
        if not raw or len(raw) > 5 * 1024 * 1024:
            raise ValueError("Choose a file up to 5 MB.")
        audience = d.get("audience", "private")
        if audience not in ("private", "company", "team:" + u["team"]):
            raise ValueError("Choose your team, company or private storage.")
        fid = key("FILE")
        db.execute(
            "INSERT INTO shared_files VALUES(?,?,?,?,?,?)",
            (fid, pid, name, raw, audience, utcnow()),
        )
        return {"id": fid}
    raise ValueError("Unknown company action.")


OPS = {
    "invite",
    "membership",
    "member-access",
    "assign",
    "accept-task",
    "task-comment",
    "task-progress",
    "publish-notice",
    "read-notifications",
    "share-file",
    "leave-adjust",
}
