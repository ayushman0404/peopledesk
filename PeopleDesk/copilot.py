"""Conversation-to-action planning. Model proposals never bypass application permissions."""

import json, re
from datetime import timedelta
import assistant_hr as ai
import company, service
import routines
from records import *

SCHEMA = """
CREATE TABLE IF NOT EXISTS copilot_turns(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,role TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS copilot_plans(id TEXT PRIMARY KEY,actor TEXT NOT NULL,version INTEGER NOT NULL,state TEXT NOT NULL,steps TEXT NOT NULL,result TEXT NOT NULL DEFAULT '[]',created TEXT NOT NULL);
"""
KINDS = ("assign", "meeting", "email", "focus", "status", "routine")
FIELDS = ("kind", "person", "title", "date", "time", "detail", "status", "reference")


def migrate(db):
    db.executescript(SCHEMA)


def record(db, u, role, body):
    db.execute(
        "INSERT INTO copilot_turns(actor,role,body,created) VALUES(?,?,?,?)",
        (u["id"], role, json.dumps(body), utcnow()),
    )


def plan(db, u, pid):
    p = one(db, "SELECT * FROM copilot_plans WHERE id=? AND actor=?", (pid, u["id"]))
    if not p:
        raise PermissionError("This plan is not in your assistant workspace.")
    p["steps"] = json.loads(p["steps"])
    p["result"] = json.loads(p["result"])
    return p


def history(db, u):
    turns = rows(
        db,
        "SELECT * FROM (SELECT id,role,body,created FROM copilot_turns WHERE actor=? ORDER BY id DESC LIMIT 80) ORDER BY id",
        (u["id"],),
    )
    for t in turns:
        t["body"] = json.loads(t["body"])
        if t["body"].get("plan_id"):
            t["body"]["plan"] = plan(db, u, t["body"]["plan_id"])
    return {"turns": turns}


def context(db, u):
    return company.augment(db, u, service.state(db, u))


def brief(db, u):
    s = context(db, u)
    tasks = [t for t in s["tasks"] if t["status"] != "Done" and t.get("accepted", 1)]
    overdue = [t for t in tasks if t["due"] < day()]
    blocked = [t for t in tasks if t["status"] == "Blocked"]
    due = [t for t in tasks if t["due"] == day()]
    pending = [r for r in s["requests"] if r["status"] == "Pending"]
    sources = [
        {
            "id": t["id"],
            "text": t["title"]
            + " · "
            + person(db, t["owner"])["name"]
            + " · "
            + t["status"]
            + " · due "
            + t["due"],
        }
        for t in sorted(tasks, key=lambda t: (t["status"] != "Blocked", t["due"]))[:8]
    ]
    answer = f"Here is the current picture in your workspace: {len(overdue)} overdue tasks, {len(blocked)} blocked, {len(due)} due today, and {len(pending)} pending requests."
    if blocked:
        answer += " Start by asking what is blocking " + blocked[0]["title"] + "."
    elif overdue:
        answer += (
            " Start with the oldest overdue commitment: "
            + sorted(overdue, key=lambda t: t["due"])[0]["title"]
            + "."
        )
    else:
        answer += (
            " There are no overdue or blocked tasks in the records you can access."
        )
    answer += " These counts describe visible work, not employee performance."
    return {
        "answer": answer,
        "sources": sources,
        "brief": {
            "overdue": len(overdue),
            "blocked": len(blocked),
            "today": len(due),
            "pending": len(pending),
        },
    }


def date_from(q):
    match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", q)
    if match:
        return iso(match[0])
    if re.search(r"\btomorrow\b", q, re.I):
        return day(1)
    if re.search(r"\btoday\b", q, re.I):
        return day()
    for i, n in enumerate(
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    ):
        if re.search(r"\b" + n + r"\b", q, re.I):
            return day((i - today().weekday()) % 7 or 7)
    return ""


def time_from(q):
    m = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", q, re.I)
    if m:
        return f"{int(m[1])%12+(12 if m[3].lower()=='pm' else 0):02d}:{m[2] or '00'}"
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", q)
    return f"{int(m[1]):02d}:{m[2]}" if m else ""


def person_id(db, u, value):
    if value.casefold() in ("me", "myself", "i", u["id"].casefold()):
        return u["id"]
    ps = rows(
        db,
        "SELECT p.id,p.name,p.email FROM people p JOIN profiles a ON a.person=p.id WHERE a.active=1",
    )
    exact = [
        p
        for p in ps
        if value.casefold()
        in (p["id"].casefold(), p["name"].casefold(), p["email"].casefold())
    ]
    matches = exact or [
        p for p in ps if p["name"].split()[0].casefold() == value.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(
            "Choose one exact colleague name; '" + value + "' is missing or ambiguous."
        )
    return matches[0]["id"]


def normalize(step):
    if not isinstance(step, dict):
        raise ValueError("Each step must contain action fields.")
    if step.get("kind") not in KINDS:
        raise ValueError("Choose a supported action.")
    return {
        k: text(step[k], k, 4000 if k == "detail" else 180) if step.get(k) else ""
        for k in FIELDS
    }


def validate(db, u, step):
    p = normalize(step)
    k = p["kind"]
    if k in ("assign", "meeting", "email", "routine"):
        pid = person_id(db, u, p["person"])
    if k in ("assign", "meeting", "focus", "routine"):
        iso(p["date"])
        if p["date"] < day():
            raise ValueError("Use today or a future date for new work.")
    if k in ("assign", "meeting", "email", "focus", "routine"):
        text(p["title"], "Title", 160)
    if k in ("meeting", "focus", "routine"):
        moment(p["date"] + "T" + p["time"])
    if k == "routine" and pid != u["id"] and not company.manages(u, person(db, pid)):
        raise PermissionError("Only automate work for yourself or people you manage.")
    if k == "email":
        text(p["detail"], "Email body", 4000)
    if k == "status":
        company.visible_task(db, u, p["reference"])
        if p["status"] not in ("Open", "In progress", "Blocked", "Done"):
            raise ValueError("Choose Open, In progress, Blocked or Done.")
    return p


def errors(db, u, steps):
    result = []
    for i, s in enumerate(steps):
        try:
            validate(db, u, s)
        except (ValueError, PermissionError) as e:
            result.append("Step " + str(i + 1) + ": " + str(e))
    return result


def store_plan(db, u, steps, pid=None, expected=None):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 4:
        raise ValueError("A plan supports one to four actions.")
    steps = [normalize(s) for s in steps]
    with db:
        db.execute("BEGIN IMMEDIATE")
        if pid:
            p = plan(db, u, pid)
            if p["state"] != "Ready" or (
                expected is not None and p["version"] != expected
            ):
                raise ValueError("This plan changed. Reload it before editing.")
            db.execute(
                "UPDATE copilot_plans SET steps=?,version=version+1 WHERE id=?",
                (json.dumps(steps), pid),
            )
        else:
            pid = key("PLAN")
            db.execute(
                "UPDATE copilot_plans SET state='Superseded' WHERE actor=? AND state='Ready'",
                (u["id"],),
            )
            db.execute(
                "INSERT INTO copilot_plans VALUES(?,?,1,'Ready',?,'[]',?)",
                (pid, u["id"], json.dumps(steps), utcnow()),
            )
        out = {
            "answer": (
                "I've updated the plan. Review the revised details before running it."
                if expected is not None
                else "Here is the work I can carry out. Check the details below, then run the plan. You can also tell me what to change."
            ),
            "plan_id": pid,
        }
        missing = errors(db, u, steps)
        if missing:
            out["answer"] = "I need a few details before I can run this: " + " ".join(
                missing
            )
        record(db, u, "assistant", out)
    return {**out, "plan": plan(db, u, pid)}


def execute(db, u, d):
    with db:
        db.execute("BEGIN IMMEDIATE")
        p = plan(db, u, d.get("id"))
        if p["version"] != int(d.get("version", 0)):
            raise ValueError(
                "This plan has a newer version. Review the latest details."
            )
        if p["state"] == "Completed":
            return {
                "answer": "This plan already ran. No duplicate work was created.",
                "receipts": p["result"],
            }
        if p["state"] != "Ready":
            raise ValueError("This plan is cancelled.")
        steps = [validate(db, u, s) for s in p["steps"]]
        receipts = []
        for s in steps:
            k = s["kind"]
            if k == "routine":
                r = routines.create(
                    db,
                    u,
                    {
                        "owner": person_id(db, u, s["person"]),
                        "title": s["title"],
                        "detail": s["detail"],
                        "date": s["date"],
                        "time": s["time"],
                    },
                )
                label = "Weekday task routine enabled; runs while the service is open"
                dest = "routine"
            elif k == "assign":
                pid = person_id(db, u, s["person"])
                r = company.handle(
                    db,
                    u,
                    "assign",
                    {
                        "title": s["title"],
                        "owner": pid,
                        "due": s["date"],
                        "description": s["detail"],
                        "project": "Assistant work plan",
                    },
                )
                direct = pid == u["id"] or company.manages(u, person(db, pid))
                label = (
                    "Assigned to " if direct else "Collaboration invitation sent to "
                ) + person(db, pid)["name"]
                dest = "task"
            elif k == "status":
                r = company.handle(
                    db,
                    u,
                    "task-progress",
                    {"id": s["reference"], "status": s["status"]},
                )
                r = {"id": s["reference"]}
                label = "Task marked " + s["status"]
                dest = "task"
            elif k == "focus":
                r = service.change(
                    db,
                    u,
                    "work-block",
                    {
                        "title": s["title"],
                        "starts": s["date"] + "T" + s["time"],
                        "minutes": 30,
                    },
                )
                label = "30-minute focus block scheduled"
                dest = "event"
            elif k == "meeting":
                pid = person_id(db, u, s["person"])
                r = service.make_request(
                    db,
                    u,
                    {
                        "kind": "Meeting",
                        "title": s["title"],
                        "starts": s["date"] + "T" + s["time"],
                        "minutes": 30,
                        "people": list(dict.fromkeys([u["id"], pid])),
                        "zoom": "zoom" in (s["title"] + " " + s["detail"]).lower(),
                    },
                )
                label = "Meeting request submitted for HR approval"
                dest = "request"
            else:
                pid = person_id(db, u, s["person"])
                r = service.make_request(
                    db,
                    u,
                    {
                        "kind": "Email",
                        "title": s["title"],
                        "to": person(db, pid)["email"],
                        "message": s["detail"],
                    },
                )
                label = "Email draft submitted for HR approval; not sent"
                dest = "request"
            receipts.append(
                {
                    "id": r["id"] if isinstance(r, dict) else r,
                    "label": label,
                    "title": s["title"] or s["reference"],
                    "destination": dest,
                }
            )
        db.execute(
            "UPDATE copilot_plans SET state='Completed',result=? WHERE id=?",
            (json.dumps(receipts), p["id"]),
        )
        out = {"answer": "Done. Here are the recorded results.", "receipts": receipts}
        record(db, u, "assistant", out)
        audit(db, u["id"], "Executed assistant plan", p["id"])
    return out


def compound_step(db, u, q):
    q = q.strip().rstrip(".;")
    m = re.fullmatch(
        r"(?:please )?assign (.+?) to (.+?)\s+(?:by |on )?(today|tomorrow|20\d{2}-\d{2}-\d{2}|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        q,
        re.I,
    )
    if m:
        return {
            "kind": "assign",
            "person": m[1],
            "title": m[2],
            "date": date_from(m[3]),
        }
    if re.search(r"\bfocus\b", q, re.I):
        return {
            "kind": "focus",
            "title": "Focus time",
            "detail": q,
            "date": date_from(q),
            "time": time_from(q),
        }
    people = ai.mentioned_people(q, rows(db, "SELECT id,name FROM people"))
    if len(people) != 1:
        return None
    if re.search(r"\b(meeting|zoom|call)\b", q, re.I):
        return {
            "kind": "meeting",
            "person": people[0]["name"],
            "title": "Meeting with " + people[0]["name"],
            "detail": q,
            "date": date_from(q),
            "time": time_from(q),
        }
    if re.match(r"(?:draft |write |prepare |send )?(?:an? )?email\b", q, re.I):
        mail = ai.draft_mail(q, person(db, people[0]["id"])["email"])
        return {
            "kind": "email",
            "person": people[0]["name"],
            "title": mail["subject"],
            "detail": mail["message"],
        }
    return None


def respond(db, u, q):
    q = text(q, "Message", 1500)
    # Treat instructions to change consequential employment outcomes as a human case.
    if ai.sensitive(q):
        out = {
            "answer": "That needs a human HR decision. I can help document the facts for review, but I won't decide employment, pay or disciplinary outcomes.",
            "action": {"type": "case", "details": q},
        }
        with db:
            record(db, u, "user", {"answer": q})
            record(db, u, "assistant", out)
        return out
    latest = one(
        db,
        "SELECT id FROM copilot_plans WHERE actor=? AND state='Ready' ORDER BY rowid DESC LIMIT 1",
        (u["id"],),
    )
    previous = plan(db, u, latest["id"]) if latest else None
    with db:
        record(db, u, "user", {"answer": q})
    if previous and re.fullmatch(
        r"(yes|do it|run (it|the plan)|confirm|go ahead)[.! ]*", q, re.I
    ):
        last = one(
            db,
            "SELECT body FROM copilot_turns WHERE actor=? AND role='assistant' ORDER BY id DESC LIMIT 1",
            (u["id"],),
        )
        if not last or json.loads(last["body"]).get("plan_id") != previous["id"]:
            out = {
                "answer": "Use Run plan on the plan you want to execute, so I don't act on an older conversation by mistake."
            }
            with db:
                record(db, u, "assistant", out)
            return out
        return execute(db, u, {"id": previous["id"], "version": previous["version"]})
    if previous and re.fullmatch(
        r"(cancel|cancel it|cancel the plan|never mind)[.! ]*", q, re.I
    ):
        with db:
            db.execute(
                "UPDATE copilot_plans SET state='Cancelled' WHERE id=?",
                (previous["id"],),
            )
            out = {"answer": "Cancelled. No work was created by that plan."}
            record(db, u, "assistant", out)
        return out
    if re.search(
        r"\b(brief|prioriti[sz]e|workload|what should I|what needs|plan my day)\b",
        q,
        re.I,
    ):
        out = brief(db, u)
    elif re.fullmatch(r"(thanks|thank you)[.! ]*", q, re.I):
        out = {"answer": "You're welcome. What would you like to tackle next?"}
    elif re.fullmatch(r"(hi|hello|hey)[.! ]*", q, re.I) or re.search(
        r"what can you do|how do I use", q, re.I
    ):
        out = {
            "answer": "Hi "
            + u["name"].split()[0]
            + ". Tell me the outcome you want. I can assign work, update a task, prepare email, request a meeting, or plan focus time. Try: Assign Karan to review the launch checklist tomorrow."
        }
    elif (
        previous
        and re.search(r"^(make|change|move|instead|actually|use)\b", q, re.I)
        and (date_from(q) or time_from(q))
        and not re.search(r"\b(person|owner|title|email|assign)\b", q, re.I)
    ):
        steps = previous["steps"]
        for s in steps:
            if s["kind"] in ("assign", "meeting", "focus", "routine") and date_from(q):
                s["date"] = date_from(q)
            if s["kind"] in ("meeting", "focus", "routine") and time_from(q):
                s["time"] = time_from(q)
        return store_plan(db, u, steps, previous["id"], previous["version"])
    elif re.search(
        r"\b(assign|routine|give .*task|create .*task|add .*task|schedule|book|draft|email|mark|focus|change|move)\b",
        q,
        re.I,
    ):
        # Common assignment phrasing avoids model latency while retaining exact user wording.
        chunks = re.split(
            r"\s*;\s*|\s+and then\s+|\s+then\s+|\s+and (?=(?:schedule|assign|draft|email|book|create)\b)",
            q,
            flags=re.I,
        )
        if len(chunks) > 1:
            if len(chunks) > 4:
                raise ValueError("Split this into plans of up to four actions.")
            steps = [compound_step(db, u, chunk) for chunk in chunks]
            if all(steps):
                return store_plan(db, u, steps)
            out = {
                "answer": "I couldn't resolve every step confidently. Give each action its own colleague, date and time, separated by 'then'. No work has been created."
            }
            with db:
                record(db, u, "assistant", out)
            return out
        if re.search(r"\bfocus\b", q, re.I) and re.search(
            r"\b(schedule|book|block)\b", q, re.I
        ):
            return store_plan(db, u, [compound_step(db, u, q)])
        fast = re.fullmatch(
            r"(?:please )?assign (.+?) to (.+?)\s+(?:by |on )?(today|tomorrow|20\d{2}-\d{2}-\d{2}|monday|tuesday|wednesday|thursday|friday|saturday|sunday)[.!]?",
            q,
            re.I,
        )
        email_request = re.match(
            r"^(?:please )?(?:draft |write |prepare |send )?(?:an? )?(?:email|e-mail)\b",
            q,
            re.I,
        )
        if email_request and not re.search(r"\b(and then|also|then)\b", q, re.I):
            mentioned = ai.mentioned_people(q, rows(db, "SELECT id,name FROM people"))
            if len(mentioned) == 1:
                recipient = mentioned[0]
            elif (
                not mentioned and previous and re.search(r"\b(him|her|them)\b", q, re.I)
            ):
                recipient = person(
                    db, person_id(db, u, previous["steps"][-1]["person"])
                )
            else:
                out = {
                    "answer": "Who should receive the email? Use one colleague's full name so I choose the right person."
                }
                with db:
                    record(db, u, "assistant", out)
                return out
            drafted = ai.draft_mail(q, person(db, recipient["id"])["email"])
            steps = [
                {
                    "kind": "email",
                    "person": recipient["name"],
                    "title": drafted["subject"],
                    "detail": drafted["message"],
                }
            ]
        elif (
            re.search(r"\b(meeting|zoom|call)\b", q, re.I)
            and re.search(r"\b(schedule|book|arrange)\b", q, re.I)
            and not re.search(r"\b(and then|also|then)\b", q, re.I)
        ):
            mentioned = ai.mentioned_people(q, rows(db, "SELECT id,name FROM people"))
            if len(mentioned) != 1:
                out = {
                    "answer": "Which colleague should join? Use one exact name for this meeting request."
                }
                with db:
                    record(db, u, "assistant", out)
                return out
            steps = [
                {
                    "kind": "meeting",
                    "person": mentioned[0]["name"],
                    "title": (
                        "Zoom meeting with "
                        if re.search(r"\bzoom\b", q, re.I)
                        else "Meeting with "
                    )
                    + mentioned[0]["name"],
                    "date": date_from(q),
                    "time": time_from(q),
                    "detail": q,
                }
            ]
        elif fast and not re.search(r"\b(and then|also|then)\b", q, re.I):
            steps = [
                dict(
                    kind="assign",
                    person=fast[1],
                    title=fast[2],
                    date=date_from(fast[3]),
                )
            ]
        else:
            recent = rows(
                db,
                "SELECT role,body FROM copilot_turns WHERE actor=? ORDER BY id DESC LIMIT 3",
                (u["id"],),
            )
            recent = [
                {
                    "role": r["role"],
                    "text": json.loads(r["body"]).get("answer", "")[:500],
                }
                for r in recent
            ]
            fields = {k: {"type": "string"} for k in FIELDS}
            fields["kind"] = {"type": "string", "enum": list(KINDS)}
            parsed = ai.generate(
                "You are PeopleDesk's work planner. Extract only actions explicitly requested by the user. Return no steps and ask a concise question if unclear or unsupported. Never invent people, task IDs, dates or facts. Empty missing fields stay empty. Dates are ISO YYYY-MM-DD, times HH:MM UTC. Today is "
                + day()
                + ". Meeting/focus blocks are 30 minutes. Email steps prepare drafts, not send. assign creates tasks; status changes a visible task. routine creates a task each weekday at the given UTC time, starting on date, ONLY if the user explicitly requests repeating weekday work. When revising, preserve the existing plan except requested changes. Colleague names must come from the directory. Do not execute anything.",
                json.dumps(
                    {
                        "request": q,
                        "directory": rows(db, "SELECT id,name FROM people"),
                        "visible_tasks": [
                            {"id": t["id"], "title": t["title"]}
                            for t in context(db, u)["tasks"]
                        ][:15],
                        "previous_plan": (
                            previous["steps"]
                            if previous
                            and re.search(
                                r"^(change|move|make|instead|actually|use)\b", q, re.I
                            )
                            else None
                        ),
                    }
                ),
                {
                    "reply": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": fields,
                            "required": list(fields),
                            "additionalProperties": False,
                        },
                    },
                },
                max_tokens=1000,
            )
            steps = parsed["steps"]
            if not steps:
                out = {
                    "answer": parsed["reply"] or "Tell me who should do what, and when."
                }
                with db:
                    record(db, u, "assistant", out)
                return out
        revision = (
            previous
            if re.search(r"^(change|move|make|instead|actually|use)\b", q, re.I)
            else None
        )
        return store_plan(
            db,
            u,
            steps,
            revision["id"] if revision else None,
            revision["version"] if revision else None,
        )
    else:
        out = ai.chat(db, u, q)
        if (
            out.get("action", {}).get("type") == "case"
            and not out.get("sources")
            and not ai.sensitive(q)
        ):
            recent = rows(
                db,
                "SELECT role,body FROM copilot_turns WHERE actor=? ORDER BY id DESC LIMIT 5",
                (u["id"],),
            )
            facts = brief(db, u)
            answer = ai.generate(
                "You are PeopleDesk, a concise friendly workplace assistant. Answer the user's question using the supplied conversation and workspace facts. You can help plan tasks, prepare email drafts, request meetings, create weekday task routines, find records, and guide colleagues. This response performs no actions: never claim anything has been sent, assigned, booked or changed. If the user wants action, explain one concrete next request. Do not invent company facts, employee performance judgments or live provider connections. Ask one focused question when information is missing.",
                json.dumps(
                    {
                        "question": q,
                        "recent": [
                            {
                                "role": t["role"],
                                "text": json.loads(t["body"]).get("answer", "")[:500],
                            }
                            for t in reversed(recent)
                        ],
                        "facts": facts,
                    }
                ),
                {"answer": {"type": "string"}},
            )
            out = {"answer": answer["answer"], "sources": facts["sources"]}
    with db:
        record(db, u, "assistant", out)
    return out


def handle(db, u, op, d):
    if op == "assistant-history":
        return history(db, u)
    if op == "assistant-create":
        return store_plan(db, u, d.get("steps"))
    if op == "assistant-talk":
        return respond(db, u, d.get("q"))
    if op == "assistant-run":
        return execute(db, u, d)
    if op == "assistant-edit":
        return store_plan(db, u, d.get("steps"), d.get("id"), int(d.get("version", 0)))
    if op == "assistant-cancel":
        with db:
            p = plan(db, u, d.get("id"))
            if p["state"] != "Ready":
                raise ValueError("Only a ready plan can be cancelled.")
            db.execute(
                "UPDATE copilot_plans SET state='Cancelled' WHERE id=?", (p["id"],)
            )
        return {"answer": "Plan cancelled."}
    raise ValueError("Unknown assistant action.")


OPS = {
    "assistant-history",
    "assistant-talk",
    "assistant-run",
    "assistant-edit",
    "assistant-cancel",
    "assistant-create",
}
