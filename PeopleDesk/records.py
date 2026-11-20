"""PeopleDesk's company records, demo data and workflow transactions."""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()


def today():
    return datetime.now(timezone.utc).date()


def day(offset=0):
    return (today() + timedelta(days=offset)).isoformat()


def key(prefix):
    return prefix + "-" + secrets.token_hex(5).upper()


def connect(path):
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def one(db, sql, args=()):
    return next(iter(rows(db, sql, args)), None)


def text(value, name="Value", limit=500):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{name} is required and must fit within {limit} characters.")
    return value.strip()


def email(value):
    value = text(value, "Email", 240)
    if not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value
    ):
        raise ValueError("Enter a single valid email address.")
    return value


def iso(value):
    return date.fromisoformat(text(value, "Date", 10)).isoformat()


def moment(value):
    try:
        d = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        raise ValueError("Choose a date and time in company time (UTC).")
    return d


def weekdays(start, end):
    start = date.fromisoformat(iso(start))
    end = date.fromisoformat(iso(end))
    if end < start or (end - start).days > 365:
        raise ValueError("Choose an ordered range within one year.")
    n = sum(
        (start + timedelta(days=i)).weekday() < 5 for i in range((end - start).days + 1)
    )
    if not n:
        raise ValueError("This range contains no working days.")
    return n


def password(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac(
            "sha256", value.encode(), bytes.fromhex(salt), 240000
        ).hex()
    )


def check_password(value, stored):
    return bool(stored) and hmac.compare_digest(
        password(value, stored.split(":")[0]), stored
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE COLLATE NOCASE,team TEXT NOT NULL,title TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('hr','employee')),manager TEXT REFERENCES people(id),start TEXT NOT NULL,location TEXT NOT NULL,hash TEXT);
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,person TEXT NOT NULL REFERENCES people(id),days INTEGER NOT NULL,reason TEXT NOT NULL,posted TEXT NOT NULL,request TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY,title TEXT NOT NULL,keywords TEXT NOT NULL,body TEXT NOT NULL,version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,creator TEXT NOT NULL REFERENCES people(id),subject TEXT NOT NULL REFERENCES people(id),body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Pending',created TEXT NOT NULL,reviewer TEXT REFERENCES people(id),reviewed TEXT,note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,owner TEXT NOT NULL REFERENCES people(id),helper TEXT REFERENCES people(id),due TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Open',source TEXT NOT NULL,flow TEXT);
CREATE TABLE IF NOT EXISTS flows(id TEXT PRIMARY KEY,kind TEXT NOT NULL,subject TEXT NOT NULL REFERENCES people(id),title TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS flow_notes(id TEXT PRIMARY KEY,flow TEXT NOT NULL REFERENCES flows(id),actor TEXT NOT NULL REFERENCES people(id),at TEXT NOT NULL,note TEXT NOT NULL,filename TEXT NOT NULL,attachment BLOB);
CREATE TABLE IF NOT EXISTS reminders(person TEXT NOT NULL REFERENCES people(id),task TEXT NOT NULL REFERENCES tasks(id),until_date TEXT NOT NULL,PRIMARY KEY(person,task));
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,title TEXT NOT NULL,starts TEXT NOT NULL,ends TEXT NOT NULL,people TEXT NOT NULL,source TEXT NOT NULL,external TEXT UNIQUE,link TEXT NOT NULL DEFAULT '',cancelled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY,author TEXT NOT NULL REFERENCES people(id),created TEXT NOT NULL,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS promotions(handoff TEXT NOT NULL REFERENCES handoffs(id),item INTEGER NOT NULL,request TEXT NOT NULL REFERENCES requests(id),PRIMARY KEY(handoff,item));
CREATE TABLE IF NOT EXISTS actions(request TEXT NOT NULL REFERENCES requests(id),channel TEXT NOT NULL,status TEXT NOT NULL,provider_id TEXT,details TEXT NOT NULL DEFAULT '',PRIMARY KEY(request,channel));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,verb TEXT NOT NULL,object TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS secrets(k TEXT PRIMARY KEY,blob BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS commands(actor TEXT NOT NULL,token TEXT NOT NULL,op TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor,token));
"""

PLAYBOOKS = {
    "Onboarding": [
        "Collect starter documents",
        "Prepare account and equipment request",
        "Schedule first-week check-in",
    ],
    "Hiring logistics": [
        "Draft interview invitation",
        "Collect interviewer availability",
        "Request interview feedback",
    ],
    "Attendance correction": [
        "Check the attendance entry",
        "Request manager confirmation",
        "Record the corrected attendance input",
    ],
    "Payroll support": [
        "Collect the payroll query",
        "Verify the source with payroll",
        "Return the payroll team's response",
    ],
    "Review cycle": [
        "Send review form reminder",
        "Collect completed forms",
        "Schedule manager conversation",
    ],
    "Training": [
        "Confirm training requirements",
        "Book training session",
        "Record attendance",
    ],
    "Exit administration": [
        "Collect exit paperwork",
        "Arrange equipment return",
        "Confirm final settlement handoff",
    ],
    "Policy review": [
        "Collect proposed handbook changes",
        "Arrange HR review",
        "Prepare publication checklist",
    ],
}
POLICIES = [
    (
        "POL-01",
        "Annual leave",
        "leave holiday vacation paid time off PTO",
        "Annual leave uses working days, Monday to Friday. Approved leave reduces the balance in the employee ledger. Submit dates to HR before taking leave.",
    ),
    (
        "POL-02",
        "Expense reimbursement",
        "expenses expense reimbursement receipts travel claim",
        "Submit an itemised receipt and business purpose to Finance within 30 days. Your manager reviews the claim before Finance processes payment.",
    ),
    (
        "POL-03",
        "Payslip access",
        "payslip pay slip payroll portal salary statement",
        "Payslips are issued through the payroll portal. If a statement is missing, open a payroll support case with HR.",
    ),
    (
        "POL-04",
        "Flexible working",
        "hybrid remote office wfh work from home",
        "Agree your working location with your manager. Requests to change a regular work arrangement go to HR for review.",
    ),
    (
        "POL-05",
        "New starter setup",
        "onboarding starter laptop induction equipment",
        "HR coordinates starter paperwork. IT provisions approved accounts and equipment. The line manager schedules a first-week check-in.",
    ),
    (
        "POL-06",
        "Confidential concerns",
        "complaint bullying harassment grievance confidential",
        "Submit a confidential case to HR. A human HR reviewer will arrange a private conversation and agree the next steps.",
    ),
    (
        "POL-07",
        "Working hours and attendance",
        "hours shift attendance timesheet clock",
        "Record attendance in the team timesheet. Submit corrections with the date and reason so HR can verify the entry with your manager.",
    ),
    (
        "POL-08",
        "Learning requests",
        "training learning course development",
        "Request manager approval before booking external training. Send the course details and dates to HR for coordination.",
    ),
    (
        "POL-09",
        "Exit process",
        "exit resignation equipment return notice",
        "Send the resignation notice to HR for acknowledgement. HR coordinates the exit meeting, equipment return and handoff to payroll.",
    ),
    (
        "POL-10",
        "Interview coordination",
        "interview candidate hiring recruitment",
        "The hiring coordinator collects interviewer availability and sends approved invitations. The hiring manager records the selection decision.",
    ),
]


def audit(db, actor, verb, obj):
    db.execute(
        "INSERT INTO audit(actor,verb,object,at) VALUES(?,?,?,?)",
        (actor, verb, obj, utcnow()),
    )


def init(path, demo=True):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if "revision" not in {c[1] for c in db.execute("PRAGMA table_info(requests)")}:
            db.execute(
                "ALTER TABLE requests ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"
            )
        if not one(db, "SELECT v FROM meta WHERE k='mode'"):
            db.executemany(
                "INSERT INTO meta VALUES(?,?)",
                [
                    ("mode", "demo" if demo else "company"),
                    ("company", "Aster Works" if demo else "Company workspace"),
                ],
            )
            if demo:
                seed(db)
        elif (one(db, "SELECT v FROM meta WHERE k='mode'")["v"] == "demo") != demo:
            raise ValueError(
                "Choose a separate database file for the company workspace."
            )
        db.commit()
    finally:
        db.close()


def seed(db):
    roster = [
        ("Amara Bennett", "People", "People Operations Lead"),
        ("Karan Mehta", "Engineering", "Platform Engineer"),
        ("Nora Chen", "Operations", "Operations Lead"),
        ("Maya Rao", "Finance", "Finance Analyst"),
        ("Ravi Shah", "Engineering", "Engineering Manager"),
        ("Sofia Lewis", "People", "People Coordinator"),
        ("Iris Okafor", "Design", "Product Designer"),
        ("Theo Park", "Operations", "Operations Coordinator"),
    ]
    first = "Anika Leo Zara Daniel Priya Tomas Elena Yusuf Mira Felix Asha Owen Lina Adil Neha Finn Sora Jonah Pia Sam Leila Luis Nia Hugo".split()
    last = "Sen Martin Collins Khan Das Moore Silva Abbas Patel Fischer Iyer Walsh Berg Ali Bose Clark Aoki Hall Roy Reed Aziz Costa King Moss".split()
    teams = [
        ("Finance", "Accounts Associate"),
        ("Engineering", "Systems Engineer"),
        ("Operations", "Operations Specialist"),
        ("Design", "Designer"),
        ("People", "HR Associate"),
        ("Quality", "Quality Specialist"),
    ]
    for i, name in enumerate(first):
        roster.append((name + " " + last[i], *teams[i % len(teams)]))
    for i, (name, team, title) in enumerate(roster):
        pid = f"E{i+1:03d}"
        db.execute(
            "INSERT INTO people VALUES(?,?,?,?,?,?,?,?,?,NULL)",
            (
                pid,
                name,
                name.lower().replace(" ", ".") + "@aster.example",
                team,
                title,
                "hr" if i == 0 else "employee",
                None if i == 0 else "E001",
                day(-30 - 17 * i),
                ["Bengaluru", "London", "Pune"][i % 3],
            ),
        )
        for prefix, d, reason in [
            ("OPEN", 24, "Annual entitlement"),
            ("USED", -((i * 3 + 3) % 11), "Previously approved leave"),
        ]:
            db.execute(
                "INSERT INTO ledger VALUES(?,?,?,?,?,NULL)",
                (prefix + "-" + pid, pid, d, reason, day(-5)),
            )
    db.executemany(
        "INSERT INTO policies VALUES(?,?,?,?,?)",
        [(p[0], p[1], p[2], p[3], "2026.1") for p in POLICIES],
    )
    f = start_flow(db, "Onboarding", "E007", "Iris · first week", "E001", day(0))
    start_flow(
        db,
        "Hiring logistics",
        "E006",
        "Operations coordinator interviews",
        "E001",
        day(1),
    )
    db.execute(
        "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,NULL)",
        (
            "TASK-100",
            "Prepare the platform onboarding checklist",
            "E002",
            "E005",
            day(),
            "Open",
            "People operations",
        ),
    )
    db.execute(
        "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,NULL)",
        (
            "TASK-101",
            "Check travel reimbursement documents",
            "E004",
            "E006",
            day(1),
            "Open",
            "Finance handoff",
        ),
    )
    future = today() + timedelta(days=3)
    while future.weekday() > 4:
        future += timedelta(days=1)
    request(
        db,
        "E002",
        "Leave",
        "E002",
        "Annual leave · Karan Mehta",
        {
            "start": future.isoformat(),
            "end": future.isoformat(),
            "days": 1,
            "reason": "Personal leave",
        },
    )
    request(
        db,
        "E006",
        "Email",
        "E007",
        "Welcome to Aster Works",
        {
            "to": "iris.okafor@aster.example",
            "subject": "Welcome to Aster Works",
            "message": "Hi Iris,\n\nWelcome to Aster Works. We look forward to your first-week check-in. Please let us know if you need anything before then.\n\nPeople Operations",
        },
    )
    request(
        db,
        "E007",
        "Human review",
        "E007",
        "Account access request",
        {
            "topic": "Access and security",
            "details": "Please review the design workspace access request.",
        },
    )
    for i, (title, t, ids) in enumerate(
        [
            ("People team check-in", "09:30", ["E001", "E006"]),
            ("First-week welcome", "14:00", ["E001", "E007"]),
            ("Operations planning", "11:00", ["E001", "E003"]),
        ]
    ):
        dt = moment(day(1 if i == 2 else 0) + "T" + t)
        db.execute(
            "INSERT INTO events(id,title,starts,ends,people,source) VALUES(?,?,?,?,?,?)",
            (
                f"EVT-{i+1}",
                title,
                dt.isoformat(timespec="minutes"),
                (dt + timedelta(minutes=30)).isoformat(timespec="minutes"),
                json.dumps(ids),
                "People calendar",
            ),
        )


def balance(db, pid):
    return db.execute(
        "SELECT coalesce(sum(days),0) FROM ledger WHERE person=?", (pid,)
    ).fetchone()[0]


def person(db, pid):
    p = one(
        db,
        "SELECT id,name,email,team,title,role,manager,start,location FROM people WHERE id=?",
        (pid,),
    )
    if not p:
        raise ValueError("Select an employee from the company directory.")
    return p


def request(db, creator, kind, subject, title, body):
    rid = key("REQ")
    db.execute(
        "INSERT INTO requests(id,kind,title,creator,subject,body,created) VALUES(?,?,?,?,?,?,?)",
        (rid, kind, title, creator, subject, json.dumps(body), utcnow()),
    )
    audit(db, creator, "Submitted " + kind.lower(), rid)
    return rid


def start_flow(db, kind, subject, title, actor, begin):
    if kind not in PLAYBOOKS:
        raise ValueError("Choose an available workflow.")
    person(db, subject)
    begin = iso(begin)
    fid = key("FLOW")
    db.execute(
        "INSERT INTO flows VALUES(?,?,?,?,?)", (fid, kind, subject, title, utcnow())
    )
    for i, task in enumerate(PLAYBOOKS[kind]):
        due = (date.fromisoformat(begin) + timedelta(days=i)).isoformat()
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,'Open',?,?)",
            (
                key("TASK"),
                task,
                actor,
                subject if subject != actor else None,
                due,
                kind + " · " + title,
                fid,
            ),
        )
    audit(db, actor, "Started " + kind, fid)
    return fid


def validate_leave(db, pid, data, exclude=""):
    s = iso(data.get("start"))
    e = iso(data.get("end"))
    n = weekdays(s, e)
    if s < day():
        raise ValueError("Choose leave starting today or later.")
    if n > balance(db, pid):
        raise ValueError("This request exceeds the available leave balance.")
    for r in rows(
        db,
        "SELECT id,body FROM requests WHERE subject=? AND kind='Leave' AND status IN ('Approved','Pending') AND id<>?",
        (pid, exclude),
    ):
        b = json.loads(r["body"])
        if s <= b["end"] and e >= b["start"]:
            raise ValueError("There is already a leave request covering these dates.")
    return {
        "start": s,
        "end": e,
        "days": n,
        "reason": text(data.get("reason") or "Annual leave", "Reason"),
    }


def meeting(db, data):
    title = text(data.get("title"), "Meeting title", 160)
    start = moment(data.get("starts"))
    if start <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError("Choose a future meeting time (UTC).")
    minutes = int(data.get("minutes", 30))
    if not 5 <= minutes <= 480:
        raise ValueError("Duration must be 5 to 480 minutes.")
    attendees = data.get("people")
    if not isinstance(attendees, list) or not 1 <= len(attendees) <= 30:
        raise ValueError("Select at least one attendee.")
    ids = list(dict.fromkeys(person(db, p)["id"] for p in attendees))
    s = start.isoformat(timespec="minutes")
    e = (start + timedelta(minutes=minutes)).isoformat(timespec="minutes")
    for event in rows(
        db,
        "SELECT people FROM events WHERE cancelled=0 AND starts<? AND ends>?",
        (e, s),
    ):
        if set(ids) & set(json.loads(event["people"])):
            raise ValueError("An attendee has a calendar conflict at this time.")
    return {
        "title": title,
        "starts": s,
        "ends": e,
        "minutes": minutes,
        "people": ids,
        "zoom": bool(data.get("zoom")),
    }


def review(db, actor, rid, decision, note):
    r = one(db, "SELECT * FROM requests WHERE id=?", (rid,))
    if not r or r["status"] != "Pending":
        raise ValueError("This request has already been reviewed or is unavailable.")
    if decision not in ("Approved", "Declined"):
        raise ValueError("Choose approve or decline.")
    b = json.loads(r["body"])
    if decision == "Approved":
        if r["kind"] == "Leave":
            valid = validate_leave(db, r["subject"], b, rid)
            db.execute(
                "INSERT INTO ledger VALUES(?,?,?,?,?,?)",
                (
                    key("LED"),
                    r["subject"],
                    -valid["days"],
                    "Approved annual leave",
                    day(),
                    rid,
                ),
            )
        elif r["kind"] == "Meeting":
            valid = meeting(db, b)
            db.execute(
                "INSERT INTO events(id,title,starts,ends,people,source) VALUES(?,?,?,?,?,?)",
                (
                    rid,
                    valid["title"],
                    valid["starts"],
                    valid["ends"],
                    json.dumps(valid["people"]),
                    "Approved meeting",
                ),
            )
        elif r["kind"] == "Task":
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,'Open',?,NULL)",
                (
                    key("TASK"),
                    r["title"],
                    b["owner"],
                    b.get("helper"),
                    b["due"],
                    b.get("source") or rid,
                ),
            )
        elif r["kind"] == "Human review" and not note.strip():
            raise ValueError(
                "Record the human reviewer's next step before closing the case."
            )
    db.execute(
        "UPDATE requests SET status=?,reviewer=?,reviewed=?,note=? WHERE id=?",
        (decision, actor, utcnow(), note[:2000], rid),
    )
    audit(db, actor, decision + " " + r["kind"].lower(), rid)
