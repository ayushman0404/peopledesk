"""Encrypted-message storage. Private keys and plaintext belong only to participants."""

import base64
import json
import hashlib
from records import *

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_keys(person TEXT PRIMARY KEY REFERENCES people(id),public TEXT NOT NULL,backup TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY,title TEXT NOT NULL,kind TEXT NOT NULL,members TEXT NOT NULL,roster TEXT NOT NULL,creator TEXT NOT NULL REFERENCES people(id),created TEXT NOT NULL,direct_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS room_members(room TEXT NOT NULL REFERENCES rooms(id),person TEXT NOT NULL REFERENCES people(id),PRIMARY KEY(room,person));
CREATE TABLE IF NOT EXISTS chat_messages(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,room TEXT NOT NULL REFERENCES rooms(id),sender TEXT NOT NULL REFERENCES people(id),envelope TEXT NOT NULL,created TEXT NOT NULL);
"""


def migrate(db):
    db.executescript(SCHEMA)


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def b64(value, minimum=0, maximum=120000):
    if not isinstance(value, str) or len(value) > maximum * 2:
        raise ValueError("Invalid encrypted payload.")
    try:
        data = base64.b64decode(value, validate=True)
    except Exception:
        raise ValueError("Invalid encoded payload.")
    if not minimum <= len(data) <= maximum:
        raise ValueError("Encrypted payload has an invalid size.")
    return value


def member(db, u, rid):
    r = one(
        db,
        "SELECT r.* FROM rooms r JOIN room_members m ON r.id=m.room WHERE m.person=? AND r.id=?",
        (u["id"], rid),
    )
    if not r:
        raise PermissionError("You are not a member of this conversation.")
    return r


def public_key(v):
    if not isinstance(v, dict) or set(v) != {"box", "sign"}:
        raise ValueError("Both encryption and signing keys are required.")
    box = v["box"]
    sig = v["sign"]
    if set(box) - {"kty", "e", "n", "alg", "ext", "key_ops"} or set(sig) - {
        "kty",
        "crv",
        "x",
        "y",
        "ext",
        "key_ops",
    }:
        raise ValueError("Only public identity keys may be registered.")
    if (
        box.get("kty") != "RSA"
        or box.get("e") != "AQAB"
        or len(box.get("n", "")) != 512
    ):
        raise ValueError("Use an RSA-3072 public encryption key.")
    if (
        sig.get("kty") != "EC"
        or sig.get("crv") != "P-256"
        or len(sig.get("x", "")) != 43
        or len(sig.get("y", "")) != 43
    ):
        raise ValueError("Use a P-256 public signature key.")
    return v


def snapshot(db, u):
    keys = rows(db, "SELECT person,public FROM chat_keys")
    for k in keys:
        k["public"] = json.loads(k["public"])
    mine = one(db, "SELECT public,backup FROM chat_keys WHERE person=?", (u["id"],))
    if mine:
        mine = {k: json.loads(v) for k, v in mine.items()}
    rooms = rows(
        db,
        "SELECT r.*,(SELECT MAX(sequence) FROM chat_messages WHERE room=r.id) last_message FROM rooms r JOIN room_members m ON m.room=r.id WHERE m.person=? ORDER BY coalesce(last_message,0) DESC,r.created DESC",
        (u["id"],),
    )
    for r in rooms:
        r["members"] = json.loads(r["members"])
        r["roster"] = json.loads(r["roster"])
        r.pop("direct_key")
    return {
        "keys": keys,
        "identity": mine,
        "rooms": rooms,
        "workspace": one(db, "SELECT v FROM meta WHERE k='workspace_id'")["v"],
    }


def handle(db, u, op, d):
    pid = u["id"]
    if op == "messages-state":
        return snapshot(db, u)
    if op == "messages-read":
        room = member(db, u, d.get("room"))
        before = int(d.get("before", 9223372036854775807))
        msgs = rows(
            db,
            "SELECT * FROM chat_messages WHERE room=? AND sequence<? ORDER BY sequence DESC LIMIT 75",
            (room["id"], before),
        )
        for m in msgs:
            m["envelope"] = json.loads(m["envelope"])
        return {"messages": list(reversed(msgs)), "has_more": len(msgs) == 75}
    if op == "identity-register":
        if d.get("person") != pid:
            raise PermissionError(
                "Your account changed. Sign in and activate chat again."
            )
        public = public_key(d.get("public"))
        backup = d.get("backup")
        if not isinstance(backup, dict) or backup.get("iterations") != 600000:
            raise ValueError("Unsupported key backup.")
        b64(backup.get("salt"), 16, 16)
        b64(backup.get("iv"), 12, 12)
        b64(backup.get("cipher"), 100, 20000)
        if set(backup) != {"salt", "iv", "cipher", "iterations"}:
            raise ValueError("Unknown backup field.")
        if one(db, "SELECT person FROM chat_keys WHERE person=?", (pid,)):
            raise ValueError(
                "Chat identity already exists. Unlock it with your chat passphrase."
            )
        db.execute(
            "INSERT INTO chat_keys VALUES(?,?,?,?)",
            (pid, canonical(public), canonical(backup), utcnow()),
        )
        return {}
    if op == "room-create":
        members = d.get("members")
        if not isinstance(members, list):
            raise ValueError("Select participants.")
        members = sorted(set(members + [pid]))
        if not 2 <= len(members) <= 30:
            raise ValueError("Choose 2 to 30 participants.")
        roster = {}
        for p in members:
            person(db, p)
            registered = one(
                db,
                "SELECT k.public FROM chat_keys k JOIN profiles p ON p.person=k.person WHERE k.person=? AND p.active=1",
                (p,),
            )
            if not registered:
                raise ValueError("Every participant must activate private chat first.")
            roster[p] = json.loads(registered["public"])
        kind = d.get("kind")
        if kind not in ("direct", "group") or (kind == "direct" and len(members) != 2):
            raise ValueError("Choose a direct conversation or a group.")
        direct = "|".join(members) if kind == "direct" else None
        if direct:
            previous = one(db, "SELECT id FROM rooms WHERE direct_key=?", (direct,))
            if previous:
                return previous
        rid = key("ROOM")
        db.execute(
            "INSERT INTO rooms VALUES(?,?,?,?,?,?,?,?)",
            (
                rid,
                text(d.get("title") or "Conversation", "Group name", 100),
                kind,
                canonical(members),
                canonical(roster),
                pid,
                utcnow(),
                direct,
            ),
        )
        db.executemany(
            "INSERT INTO room_members VALUES(?,?)", [(rid, p) for p in members]
        )
        return {"id": rid}
    if op == "message-send":
        room = member(db, u, d.get("room"))
        env = d.get("envelope")
        if not isinstance(env, dict) or set(env) != {"payload", "signature"}:
            raise ValueError("Invalid encrypted envelope.")
        body = env["payload"]
        expected = {
            "v",
            "workspace",
            "room",
            "sender",
            "id",
            "roster",
            "iv",
            "cipher",
            "wraps",
        }
        if not isinstance(body, dict) or set(body) != expected:
            raise ValueError("Invalid encrypted message.")
        wid = one(db, "SELECT v FROM meta WHERE k='workspace_id'")["v"]
        digest = hashlib.sha256(room["roster"].encode()).hexdigest()
        if (
            body["v"] != 1
            or body["workspace"] != wid
            or body["room"] != room["id"]
            or body["sender"] != pid
            or body["roster"] != digest
        ):
            raise ValueError("Message identity or membership does not match.")
        mid = text(body["id"], "Message ID", 80)
        if not isinstance(body["wraps"], dict) or set(body["wraps"]) != set(
            json.loads(room["members"])
        ):
            raise ValueError("Encrypt the message for every conversation participant.")
        b64(body["cipher"], 16, 50000)
        b64(body["iv"], 12, 12)
        b64(env["signature"], 64, 64)
        for v in body["wraps"].values():
            b64(v, 384, 384)
        old = one(db, "SELECT sender,envelope FROM chat_messages WHERE id=?", (mid,))
        if old:
            if old["sender"] == pid and old["envelope"] == canonical(env):
                return {"id": mid}
            raise ValueError("Message ID already used.")
        db.execute(
            "INSERT INTO chat_messages(id,room,sender,envelope,created) VALUES(?,?,?,?,?)",
            (mid, room["id"], pid, canonical(env), utcnow()),
        )
        return {"id": mid}
    raise ValueError("Unknown private chat action.")


OPS = {
    "messages-state",
    "messages-read",
    "identity-register",
    "room-create",
    "message-send",
}
