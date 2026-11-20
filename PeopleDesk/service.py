"""Role-scoped PeopleDesk operations. SQLite transactions guard approvals and balances."""

import base64
import json
import re
import sqlite3
import urllib.error
from datetime import timedelta
import assistant_hr as ai
import providers
from records import *


def hr(u):
    if u["role"] != "hr":
        raise PermissionError("This action requires an HR reviewer.")


def state(db, u):
    admin = u["role"] == "hr"
    pid = u["id"]
    mode = one(db, "SELECT v FROM meta WHERE k='mode'")["v"]
    people = rows(db, "SELECT id,name,email,team,title FROM people ORDER BY name")
    if admin:
        people = rows(
            db,
            "SELECT p.id,p.name,p.email,p.team,p.title,p.start,p.location,p.manager,(SELECT SUM(days) FROM ledger WHERE person=p.id) AS balance FROM people p ORDER BY name",
        )
    tasks = rows(
        db,
        "SELECT * FROM tasks "
        + ("" if admin else "WHERE owner=? OR helper=? ")
        + "ORDER BY status DESC,due,title",
        () if admin else (pid, pid),
    )
    reqs = rows(
        db,
        "SELECT * FROM requests "
        + ("" if admin else "WHERE creator=? ")
        + "ORDER BY created DESC,rowid DESC",
        () if admin else (pid,),
    )
    for r in reqs:
        r["body"] = json.loads(r["body"])
        r["actions"] = (
            rows(
                db,
                "SELECT channel,status,details FROM actions WHERE request=?",
                (r["id"],),
            )
            if admin
            else []
        )
    events = rows(db, "SELECT * FROM events WHERE cancelled=0 ORDER BY starts")
    for e in events:
        e["people"] = json.loads(e["people"])
    if not admin:
        events = [e for e in events if pid in e["people"]]
    flows = rows(db, "SELECT * FROM flows ORDER BY created DESC") if admin else []
    for flow in flows:
        flow["notes"] = rows(
            db,
            "SELECT id,actor,at,note,filename FROM flow_notes WHERE flow=? ORDER BY at DESC",
            (flow["id"],),
        )
    snoozed = {
        r["task"]
        for r in rows(
            db,
            "SELECT task FROM reminders WHERE person=? AND until_date>?",
            (pid, day()),
        )
    }
    reminders = [
        t["id"]
        for t in tasks
        if t["due"] <= day() and t["status"] == "Open" and t["id"] not in snoozed
    ]
    saved = rows(db, "SELECT * FROM handoffs ORDER BY created DESC") if admin else []
    for h in saved:
        h["items"] = json.loads(h["items"])
        h["promoted"] = {
            str(p["item"]): p["request"]
            for p in rows(
                db, "SELECT item,request FROM promotions WHERE handoff=?", (h["id"],)
            )
        }
    config = providers.configured()
    return {
        "user": u,
        "reminders": reminders,
        "company": one(db, "SELECT v FROM meta WHERE k='company'")["v"],
        "mode": mode,
        "today": day(),
        "people": people,
        "policies": rows(db, "SELECT * FROM policies ORDER BY id"),
        "tasks": tasks,
        "requests": reqs,
        "events": events,
        "flows": flows,
        "playbooks": PLAYBOOKS if admin else {},
        "handoffs": saved,
        "ledger": rows(
            db, "SELECT * FROM ledger WHERE person=? ORDER BY posted DESC,id", (pid,)
        ),
        "model": ai.available(),
        "integrations": (
            {
                "googleConfigured": config["google"],
                "googleLinked": bool(one(db, "SELECT k FROM secrets WHERE k='google'")),
                "zoomConfigured": config["zoom"],
            }
            if admin
            else {}
        ),
        "activity": (
            rows(db, "SELECT * FROM audit ORDER BY id DESC LIMIT 35") if admin else []
        ),
    }


def make_request(db, u, d):
    kind = d.get("kind")
    admin = u["role"] == "hr"
    pid = d.get("subject") or u["id"]
    p = person(db, pid)
    if not admin and pid != u["id"]:
        raise PermissionError("Submit requests in your own name.")
    if kind == "Leave":
        b = validate_leave(db, pid, d)
        title = "Annual leave · " + p["name"]
    elif kind == "Meeting":
        b = meeting(db, d)
        if u["id"] not in b["people"] and not admin:
            raise ValueError("Include yourself on the meeting request.")
        title = b["title"]
    elif kind == "Email":
        title = text(d.get("title"), "Subject", 160)
        if any(c in title for c in "\r\n"):
            raise ValueError("The email subject must be one line.")
        b = {
            "to": email(d.get("to")),
            "subject": title,
            "message": text(d.get("message"), "Email body", 4000),
        }
    elif kind == "Human review":
        title = text(d.get("title"), "Case title", 160)
        b = {
            "topic": text(d.get("topic"), "Case type", 100),
            "details": text(d.get("details"), "Private case notes", 3000),
        }
    elif kind == "Task":
        hr(u)
        title = text(d.get("title"), "Task", 180)
        owner = person(db, d.get("owner"))["id"]
        helper = person(db, d["helper"])["id"] if d.get("helper") else None
        if owner == helper:
            raise ValueError("Choose a different collaborator.")
        b = {
            "owner": owner,
            "helper": helper,
            "due": iso(d.get("due")),
            "source": text(d.get("source") or "HR work queue", "Source", 700),
        }
    else:
        raise ValueError("Choose a supported request type.")
    return request(db, u["id"], kind, pid, title, b)


def change(db, u, op, d):
    pid = u["id"]
    if op == "work-block":
        b = meeting(
            db,
            dict(
                title=d.get("title"),
                starts=d.get("starts"),
                minutes=d.get("minutes", 30),
                people=[pid],
            ),
        )
        eid = key("EVT")
        db.execute(
            "INSERT INTO events(id,title,starts,ends,people,source) VALUES(?,?,?,?,?,'Work block')",
            (eid, b["title"], b["starts"], b["ends"], json.dumps([pid])),
        )
        audit(db, pid, "Scheduled work block", eid)
        return {"id": eid}
    if op == "snooze":
        t = one(db, "SELECT * FROM tasks WHERE id=?", (d.get("id"),))
        if not t or (u["role"] != "hr" and pid not in (t["owner"], t["helper"])):
            raise PermissionError("Task unavailable.")
        db.execute(
            "INSERT OR REPLACE INTO reminders VALUES(?,?,?)", (pid, t["id"], day(1))
        )
        return {}
    if op == "revise-email":
        hr(u)
        r = one(
            db,
            "SELECT * FROM requests WHERE id=? AND kind='Email' AND status='Pending'",
            (d.get("id"),),
        )
        if not r:
            raise ValueError("Only a pending email can be edited.")
        if int(d.get("revision", 1)) != r["revision"]:
            raise ValueError(
                "This draft changed. Reopen it to review the latest wording."
            )
        title = text(d.get("title"), "Subject", 160)
        if "\n" in title or "\r" in title:
            raise ValueError("Use a single-line subject.")
        b = {
            "to": email(d.get("to")),
            "subject": title,
            "message": text(d.get("message"), "Message", 4000),
        }
        db.execute(
            "UPDATE requests SET body=?,title=?,revision=revision+1 WHERE id=?",
            (json.dumps(b), title, r["id"]),
        )
        audit(db, pid, "Revised pending email", r["id"])
        return {"id": r["id"]}
    if op == "flow-note":
        hr(u)
        flow = one(db, "SELECT id FROM flows WHERE id=?", (d.get("flow"),))
        if not flow:
            raise ValueError("Choose a workflow.")
        note = text(d.get("note"), "Note", 3000)
        data = None
        filename = ""
        if d.get("attachment"):
            data = base64.b64decode(d["attachment"], validate=True)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("Choose a document up to 2 MB.")
            filename = text(d.get("filename"), "Filename", 180)
            if Path(filename).suffix.lower() not in (
                ".pdf",
                ".txt",
                ".png",
                ".jpg",
                ".jpeg",
                ".csv",
                ".docx",
            ):
                raise ValueError("Use a PDF, image, text, CSV or DOCX document.")
        nid = key("NOTE")
        db.execute(
            "INSERT INTO flow_notes VALUES(?,?,?,?,?,?,?)",
            (nid, flow["id"], pid, utcnow(), note, filename, data),
        )
        audit(db, pid, "Added workflow record", flow["id"])
        return {"id": nid, "flow": flow["id"]}
    if op == "request":
        return {"id": make_request(db, u, d)}
    if op == "review":
        hr(u)
        current = one(db, "SELECT revision FROM requests WHERE id=?", (d.get("id"),))
        if not current or int(d.get("revision", 1)) != current["revision"]:
            raise ValueError(
                "The request changed. Reopen it before recording a decision."
            )
        review(db, pid, d.get("id"), d.get("decision"), str(d.get("note", "")))
        return {}
    if op == "task-status":
        t = one(db, "SELECT * FROM tasks WHERE id=?", (d.get("id"),))
        if not t or (u["role"] != "hr" and pid not in (t["owner"], t["helper"])):
            raise PermissionError("This task is outside your workspace.")
        if d.get("status") not in ("Open", "Done"):
            raise ValueError("Choose a valid task status.")
        db.execute("UPDATE tasks SET status=? WHERE id=?", (d["status"], t["id"]))
        audit(db, pid, "Marked task " + d["status"], t["id"])
        return {}
    if op == "flow":
        hr(u)
        return {
            "id": start_flow(
                db,
                d.get("kind"),
                d.get("subject"),
                text(d.get("title"), "Workflow title", 140),
                pid,
                d.get("begin"),
            )
        }
    if op == "add-person":
        hr(u)
        p = key("EMP")
        addr = email(d.get("email"))
        pw = d.get("password", "")
        if not isinstance(pw, str) or not 12 <= len(pw) <= 128:
            raise ValueError("Choose an initial password of 12 to 128 characters.")
        mgr = person(db, d.get("manager") or pid)["id"]
        entitlement = int(d.get("balance", 0))
        if not 0 <= entitlement <= 365:
            raise ValueError("Enter a starting leave balance from 0 to 365.")
        db.execute(
            "INSERT INTO people VALUES(?,?,?,?,?,'employee',?,?,?,?)",
            (
                p,
                text(d.get("name"), "Name", 100),
                addr,
                text(d.get("team"), "Team", 100),
                text(d.get("title"), "Job title", 100),
                mgr,
                iso(d.get("start")),
                text(d.get("location"), "Location", 100),
                password(pw),
            ),
        )
        db.execute(
            "INSERT INTO ledger VALUES(?,?,?,?,?,NULL)",
            (key("LED"), p, entitlement, "Opening balance", day()),
        )
        audit(db, pid, "Added employee", p)
        return {"id": p}
    if op == "policy":
        hr(u)
        doc = d.get("id") or key("POL")
        db.execute(
            "INSERT INTO policies VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,keywords=excluded.keywords,body=excluded.body,version=excluded.version",
            (
                doc,
                text(d.get("title"), "Policy title", 120),
                text(d.get("keywords"), "Search terms", 300),
                text(d.get("body"), "Handbook text", 4500),
                text(d.get("version"), "Version", 40),
            ),
        )
        audit(db, pid, "Saved handbook policy", doc)
        return {"id": doc}
    if op == "save-handoff":
        hr(u)
        hid = key("HAND")
        db.execute(
            "INSERT INTO handoffs VALUES(?,?,?,?)",
            (hid, pid, utcnow(), json.dumps(d["items"])),
        )
        audit(db, pid, "Built handoff", hid)
        return {"id": hid}
    if op == "promote":
        hr(u)
        h = one(db, "SELECT * FROM handoffs WHERE id=?", (d.get("handoff"),))
        if not h:
            raise ValueError("Handoff was not found.")
        item = next(
            (i for i in json.loads(h["items"]) if i["id"] == d.get("item")), None
        )
        if not item:
            raise ValueError("Select a handoff item.")
        prev = one(
            db,
            "SELECT request FROM promotions WHERE handoff=? AND item=?",
            (h["id"], item["id"]),
        )
        if prev:
            return {"id": prev["request"]}
        source = h["id"] + " · S" + str(item["id"]) + " · " + item["source"]
        if item["kind"] != "Action" or ai.sensitive(item["source"]):
            r = make_request(
                db,
                u,
                dict(
                    kind="Human review",
                    title=item["draft"][:160],
                    topic="Handoff review",
                    details=source,
                ),
            )
        else:
            r = make_request(
                db,
                u,
                dict(
                    kind="Task",
                    title=d.get("title") or item["draft"][:180],
                    owner=d.get("owner"),
                    helper=d.get("helper"),
                    due=d.get("due"),
                    source=source,
                ),
            )
        db.execute("INSERT INTO promotions VALUES(?,?,?)", (h["id"], item["id"], r))
        return {"id": r}
    raise ValueError("Unknown workspace action.")


def external(db, u, d):
    hr(u)
    if one(db, "SELECT v FROM meta WHERE k='mode'")["v"] != "company":
        raise ValueError("Use a company workspace to connect a real account.")
    channel = d.get("channel")
    rid = d.get("id")
    db.execute("BEGIN IMMEDIATE")
    r = one(db, "SELECT * FROM requests WHERE id=?", (rid,))
    if not r or r["status"] != "Approved":
        raise ValueError("HR approval is required first.")
    b = json.loads(r["body"])
    allowed = {
        "Email": ["Gmail draft", "Gmail send"],
        "Meeting": ["Google Calendar"] + (["Zoom"] if b.get("zoom") else []),
    }
    if channel not in allowed.get(r["kind"], []):
        raise ValueError("Choose a valid delivery action.")
    if (
        channel == "Google Calendar"
        and b.get("zoom")
        and not one(
            db,
            "SELECT provider_id FROM actions WHERE request=? AND channel='Zoom' AND status='Completed'",
            (rid,),
        )
    ):
        raise ValueError(
            "Create the approved Zoom meeting before publishing its calendar invitation."
        )
    if channel == "Gmail send" and not one(
        db,
        "SELECT provider_id FROM actions WHERE request=? AND channel='Gmail draft' AND status='Completed'",
        (rid,),
    ):
        raise ValueError("Create the Gmail draft first.")
    existing = one(
        db, "SELECT * FROM actions WHERE request=? AND channel=?", (rid, channel)
    )
    if existing and existing["status"] != "Failed":
        raise ValueError(
            "This operation is already recorded. Check the provider before taking further action."
        )
    if channel == "Zoom" and not providers.configured()["zoom"]:
        raise ValueError("Configure the Zoom credentials first.")
    if channel != "Zoom" and not one(
        db, "SELECT k FROM secrets WHERE k=?", ("google:" + u["id"],)
    ):
        raise ValueError("Connect Google first.")
    db.execute(
        "INSERT OR REPLACE INTO actions VALUES(?,?,'In progress',NULL,'')",
        (rid, channel),
    )
    db.commit()
    try:
        provider_id, details = providers.publish(db, r, channel)
    except Exception as ex:
        # A transport timeout or server error can follow a successful external write.
        status = (
            "Failed"
            if isinstance(ex, urllib.error.HTTPError)
            and ex.code in (400, 401, 403, 404, 422, 429)
            else "Verify with provider"
        )
        db.execute(
            "UPDATE actions SET status=?,details=? WHERE request=? AND channel=?",
            (status, "Check the provider account before retrying.", rid, channel),
        )
        audit(db, u["id"], channel + " · " + status, rid)
        db.commit()
        raise ValueError(
            channel
            + " could not be confirmed. Check Integrations and the provider account."
        ) from ex
    db.execute(
        "UPDATE actions SET status='Completed',provider_id=?,details=? WHERE request=? AND channel=?",
        (provider_id, details, rid, channel),
    )
    if channel == "Zoom":
        db.execute("UPDATE events SET link=? WHERE id=?", (details, rid))
    if channel == "Google Calendar":
        db.execute(
            "DELETE FROM events WHERE external=? AND source='Google Calendar' AND id<>?",
            (provider_id, rid),
        )
        db.execute("UPDATE events SET external=? WHERE id=?", (provider_id, rid))
    audit(db, u["id"], "Completed " + channel, rid)
    db.commit()
    return {"message": details}
