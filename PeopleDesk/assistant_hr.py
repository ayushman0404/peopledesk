"""Local inference plus record lookups. The model has no database or provider tools."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from datetime import timedelta
from records import balance, day, one, person, rows, today

BASE = (
    Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
)
HANDOFF = BASE.parent / "Handoff-Studio"
if str(HANDOFF) not in sys.path:
    sys.path.insert(0, str(HANDOFF))
import pipeline

ENGINE = Path(os.environ.get("PEOPLEDESK_ENGINE") or HANDOFF / "engine")
gate = threading.BoundedSemaphore(1)


def available():
    return (ENGINE / pipeline.MODEL).is_file() and (
        ENGINE / "llama-completion.exe"
    ).is_file()


def handoff(notes):
    if not available():
        raise ValueError(
            "The local Qwen engine is missing. Keep Handoff-Studio next to PeopleDesk."
        )
    if not gate.acquire(timeout=2):
        raise ValueError("The language model is busy. Try again shortly.")
    model = pipeline.LocalModel()
    model.engine = ENGINE
    model.exe = ENGINE / "llama-completion.exe"
    model.weights = ENGINE / pipeline.MODEL
    try:
        return pipeline.build(notes, model)
    finally:
        model.close()
        gate.release()


def generate(system, user, fields, max_tokens=420):
    if not available():
        raise ValueError(
            "The local Qwen engine is unavailable. You can still use the forms."
        )
    if not gate.acquire(timeout=2):
        raise ValueError("The language model is busy. Try again shortly.")
    try:
        schema = {
            "type": "object",
            "properties": fields,
            "required": list(fields),
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory(prefix="peopledesk-") as temp:
            prompt = Path(temp) / "prompt.txt"
            prompt.write_text(
                "<|im_start|>system\n"
                + system
                + "<|im_end|>\n<|im_start|>user\n"
                + user.replace("<|", "< |")
                + "<|im_end|>\n<|im_start|>assistant\n",
                encoding="utf8",
            )
            cmd = [
                str(ENGINE / "llama-completion.exe"),
                "-m",
                str(ENGINE / pipeline.MODEL),
                "-f",
                str(prompt),
                "-c",
                "6144",
                "-t",
                "6",
                "-ngl",
                "0",
                "--offline",
                "--no-warmup",
                "--no-display-prompt",
                "--no-conversation",
                "--color",
                "off",
                "--simple-io",
                "--temp",
                "0",
                "-n",
                str(max_tokens),
                "-j",
                json.dumps(schema),
            ]
            proc = subprocess.run(
                cmd,
                cwd=ENGINE,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=120,
            )
            if proc.returncode:
                raise ValueError("Local inference failed. Try a shorter request.")
            return json.JSONDecoder().raw_decode(proc.stdout.decode().lstrip())[0]
    finally:
        gate.release()


def draft_mail(brief, recipient):
    out = generate(
        "Draft a concise, polite workplace email for the requester. Use only the supplied facts. Do not invent a sender name, role, dates, promises, disciplinary conclusions or instructions not given. Return a subject and a body for a human editor.",
        json.dumps({"recipient": recipient, "brief": brief}),
        {"subject": {"type": "string"}, "message": {"type": "string"}},
    )
    return {"subject": out["subject"][:160], "message": out["message"][:4000]}


def tokenise(s):
    return set(re.findall(r"[a-z0-9]+", s.casefold())) - set(
        "how what many is the of an a are do does and my i to can we for me in on our about please tell us company policy policies".split()
    )


def sensitive(s):
    return bool(
        re.search(
            r"\b(fir(?:e|ing)|terminat\w*|reject\w*|rank\w*|disciplin\w*|harass\w*|complaint|grievance|salary change|pay raise|pay cut|security access|performance scor\w*|sentiment)\b",
            s,
            re.I,
        )
    )


def mentioned_people(q, people):
    words = tokenise(q)
    return [
        p
        for p in people
        if p["id"].casefold() in words
        or re.search(
            r"(?<!\w)" + re.escape(p["name"].casefold()) + r"(?!\w)", q.casefold()
        )
        or p["name"].split()[0].casefold() in words
    ]


def chat(db, user, q):
    folks = rows(db, "SELECT id,name FROM people ORDER BY name")
    mentioned = mentioned_people(q, folks)
    words = tokenise(q)
    t = q.casefold()
    result = {"answer": "", "sources": [], "action": None}

    def say(msg, refs=(), action=None):
        return dict(result, answer=msg, sources=list(refs), action=action)

    if sensitive(q):
        return say(
            "An HR reviewer can handle this privately. Open a confidential case and describe the next step you need.",
            action={"type": "case", "details": q},
        )
    policy_rows = rows(db, "SELECT * FROM policies ORDER BY id")
    ranked = sorted(
        (
            (len(words & tokenise(p["keywords"] + " " + p["title"])), p)
            for p in policy_rows
        ),
        key=lambda x: -x[0],
    )
    if re.search(r"\b(meet|meeting|zoom|schedule|book a call)\b", t) and not re.search(
        r"\b(policy|handbook)\b", t
    ):
        intent = "meeting"
    elif re.search(r"\b(email|e-mail|mail|letter)\b", t):
        intent = "email"
    elif (
        re.search(r"\b(request|apply|submit|book|take)\b", t)
        and re.search(r"\b(leave|vacation|pto|time off)\b", t)
        and not ("how" in words or "how" in t.split()[:2])
    ):
        intent = "leave"
    elif re.search(
        r"\b(leave|holiday|vacation|pto|days off|time off)\b", t
    ) and re.search(r"\b(left|balance|remaining|remain|available|many|unused)\b", t):
        intent = "balance"
    elif re.search(r"\b(task|tasks|assignments|to-do|workload)\b", t):
        intent = "tasks"
    elif ranked and ranked[0][0] and not re.search(r"\b(balance|remaining)\b", t):
        intent = "policy"
    else:
        if not available():
            return say(
                "I couldn't match that to a company record. You can open a case for HR.",
                action={"type": "case", "details": q},
            )
        options = ["balance", "policy", "meeting", "leave", "email", "tasks", "unknown"]
        intent = generate(
            "Route a question from an HR workspace. balance means available leave; leave means a new leave request. Use unknown for unrelated questions, private details, or unsupported requests.",
            q,
            {"intent": {"type": "string", "enum": options}},
        )["intent"]
    target = mentioned[0]["id"] if len(mentioned) == 1 else user["id"]
    if intent in ("balance", "tasks"):
        if len(mentioned) > 1:
            return say("Choose one employee so I can check the right record.")
        if user["role"] != "hr" and target != user["id"]:
            return say(
                "You can view your own leave ledger and tasks. HR can review another employee's records."
            )
        if not mentioned and not re.search(r"\b(my|me|mine|i)\b", t):
            return say(
                "Whose record should I check? Use an employee's name or ask about your own record."
            )
        p = person(db, target)
        if intent == "balance":
            entries = rows(
                db,
                "SELECT id,days,reason FROM ledger WHERE person=? ORDER BY posted,id",
                (target,),
            )
            if not entries:
                return say(
                    "There is no leave ledger for "
                    + p["name"]
                    + " yet. Ask HR to record the opening entitlement."
                )
            return say(
                f"{p['name']} has {balance(db,target)} working days of annual leave remaining.",
                [
                    {"id": e["id"], "text": f"{e['reason']} · {e['days']:+d} days"}
                    for e in entries
                ],
            )
        tasks = rows(
            db,
            "SELECT * FROM tasks WHERE (owner=? OR helper=?) AND status='Open' ORDER BY due",
            (target, target),
        )
        if re.search(r"\btoday\b", t):
            tasks = [i for i in tasks if i["due"] == day()]
        return say(
            f"{p['name']} has {len(tasks)} matching open tasks.",
            [{"id": i["id"], "text": i["title"] + " · due " + i["due"]} for i in tasks],
        )
    if intent == "policy":
        if ranked and ranked[0][0]:
            top = ranked[0][1]
            return say(
                "The closest handbook section is “"
                + top["title"]
                + "”. If it doesn't answer the question, ask HR for a ruling.",
                [{"id": top["id"] + " · v" + top["version"], "text": top["body"]}],
                {"type": "case", "details": q},
            )
        return say(
            "I couldn't find a handbook section covering that question. Ask HR to review it.",
            action={"type": "case", "details": q},
        )
    if intent == "meeting":
        start = re.search(r"\b(20\d\d-\d\d-\d\d)\b", q)
        datevalue = (
            start.group(1)
            if start
            else day(1) if "tomorrow" in t else day() if "today" in t else ""
        )
        tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
        if tm:
            hh = (int(tm[1]) % 12) + (12 if tm[3] == "pm" else 0)
            clock = f"{hh:02d}:{tm[2] or '00'}"
        else:
            tm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
            clock = f"{int(tm[1]):02d}:{tm[2]}" if tm else ""
        return say(
            "Review the attendees, date and time, then submit the meeting to HR. Times use UTC.",
            action={
                "type": "meeting",
                "starts": datevalue + "T" + clock if datevalue and clock else "",
                "people": list(
                    dict.fromkeys([user["id"]] + [p["id"] for p in mentioned])
                ),
                "zoom": "zoom" in t,
                "title": (
                    "Meeting with " + ", ".join(p["name"] for p in mentioned)
                    if mentioned
                    else ""
                ),
            },
        )
    if intent == "email":
        return say(
            "Open the draft editor to choose the recipient and review the wording before submitting it.",
            action={
                "type": "email",
                "brief": q,
                "subjectId": target if len(mentioned) == 1 else "",
            },
        )
    if intent == "leave":
        return say(
            "Confirm the dates in the leave form. HR approval updates the ledger.",
            action={
                "type": "leave",
                "subjectId": target if user["role"] == "hr" else user["id"],
            },
        )
    return say(
        "I couldn't find a supported answer in the company records. You can ask HR to review it.",
        action={"type": "case", "details": q},
    )
