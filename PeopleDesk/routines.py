"""Weekday task automation, durable receipts, and revalidated authority."""

import json
from datetime import datetime, timedelta
import company
from records import *

SCHEMA = """
CREATE TABLE IF NOT EXISTS routines(id TEXT PRIMARY KEY,actor TEXT NOT NULL,owner TEXT NOT NULL,title TEXT NOT NULL,detail TEXT NOT NULL,clock TEXT NOT NULL,next_date TEXT NOT NULL,state TEXT NOT NULL,last_note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS routine_runs(rule TEXT NOT NULL,scheduled TEXT NOT NULL,task TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(rule,scheduled));
"""


def migrate(db):
    db.executescript(SCHEMA)


def create(db, u, d):
    target = person(db, d.get("owner"))
    if target["id"] != u["id"] and not company.manages(u, target):
        raise PermissionError("Only automate your own work or work you manage.")
    date = iso(d.get("date"))
    clock = text(d.get("time"), "Time", 5)
    moment(date + "T" + clock)
    rid = key("AUTO")
    db.execute(
        "INSERT INTO routines VALUES(?,?,?,?,?,?,?,'Active','')",
        (
            rid,
            u["id"],
            target["id"],
            text(d.get("title"), "Title", 160),
            str(d.get("detail", ""))[:3000],
            clock,
            date,
        ),
    )
    audit(db, u["id"], "Created weekday task routine", rid)
    return {"id": rid}


def snapshot(db, u):
    rules = rows(
        db, "SELECT * FROM routines WHERE actor=? ORDER BY rowid DESC", (u["id"],)
    )
    for r in rules:
        r["runs"] = rows(
            db,
            "SELECT * FROM routine_runs WHERE rule=? ORDER BY created DESC LIMIT 8",
            (r["id"],),
        )
    return {"rules": rules}


def toggle(db, u, d):
    r = one(db, "SELECT * FROM routines WHERE id=? AND actor=?", (d.get("id"), u["id"]))
    if not r:
        raise PermissionError("This routine belongs to another account.")
    status = d.get("state")
    if status not in ("Active", "Paused"):
        raise ValueError("Choose Active or Paused.")
    db.execute("UPDATE routines SET state=?,last_note='' WHERE id=?", (status, r["id"]))
    audit(db, u["id"], "Routine " + status, r["id"])
    return {}


def tick(path, now=None):
    from contextlib import closing

    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    date = now.date().isoformat()
    clock = now.strftime("%H:%M")
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        candidates = rows(
            db,
            "SELECT * FROM routines WHERE state='Active' AND (next_date<? OR (next_date=? AND clock<=?))",
            (date, date, clock),
        )
        for r in candidates:
            # Missed occurrences collapse to one task on the next working day.
            if now.weekday() >= 5:
                continue
            try:
                u = company.enrich(db, person(db, r["actor"]))
                target = company.enrich(db, person(db, r["owner"]))
                if target["id"] != u["id"] and not company.manages(u, target):
                    raise PermissionError(
                        "The creator no longer manages the recipient."
                    )
            except (PermissionError, ValueError):
                db.execute(
                    "UPDATE routines SET state='Paused',last_note='Access changed; review the recipient and creator before resuming.' WHERE id=?",
                    (r["id"],),
                )
                continue
            if not one(
                db,
                "SELECT task FROM routine_runs WHERE rule=? AND scheduled=?",
                (r["id"], date),
            ):
                result = company.handle(
                    db,
                    u,
                    "assign",
                    {
                        "owner": r["owner"],
                        "title": r["title"],
                        "description": r["detail"],
                        "due": date,
                        "project": "Weekday routine",
                    },
                )
                db.execute(
                    "INSERT INTO routine_runs VALUES(?,?,?,?)",
                    (r["id"], date, result["id"], utcnow()),
                )
                db.execute(
                    "UPDATE routines SET last_note=? WHERE id=?",
                    ("Created " + result["id"] + " on " + date, r["id"]),
                )
            next_day = now.date() + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            db.execute(
                "UPDATE routines SET next_date=? WHERE id=?",
                (next_day.isoformat(), r["id"]),
            )
