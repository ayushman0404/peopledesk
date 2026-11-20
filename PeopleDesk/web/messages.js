/* Private messaging uses browser WebCrypto. The API receives encrypted envelopes. */
const Messenger = {
  snapshot: null,
  room: null,
  keys: null,
  account: null,
  timer: null,
  older: [],
  hasMore: false,
  sending: false,
  opening: 0,
  encoder: new TextEncoder(),
  decoder: new TextDecoder(),
  canonical(value) {
    if (Array.isArray(value))
      return "[" + value.map((v) => this.canonical(v)).join(",") + "]";
    if (value && typeof value === "object")
      return (
        "{" +
        Object.keys(value)
          .sort()
          .map((k) => JSON.stringify(k) + ":" + this.canonical(value[k]))
          .join(",") +
        "}"
      );
    return JSON.stringify(value);
  },
  bytes(value) {
    return this.encoder.encode(value);
  },
  b64(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer)));
  },
  from64(text) {
    return Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
  },
  async hash(value) {
    const b = await crypto.subtle.digest(
      "SHA-256",
      this.bytes(this.canonical(value)),
    );
    return [...new Uint8Array(b)]
      .map((x) => x.toString(16).padStart(2, "0"))
      .join("");
  },
  async fetch() {
    const account = S.user.id;
    const snap = await api("messages-state", {});
    if (S?.user.id !== account) return false;
    this.snapshot = snap;
    return true;
  },
  lock() {
    this.opening++;
    clearTimeout(this.timer);
    this.keys = null;
    this.room = null;
    this.snapshot = null;
    this.account = null;
    this.older = [];
    this.hasMore = false;
  },
  async derive(pass, salt) {
    const base = await crypto.subtle.importKey(
      "raw",
      this.bytes(pass),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", hash: "SHA-256", salt, iterations: 600000 },
      base,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  },
  async unlock(pass) {
    const pid = S.user.id;
    if (!crypto.subtle)
      throw Error("Private chat requires HTTPS or a localhost connection.");
    if (pass.length < 16)
      throw Error(
        "Use a chat passphrase of at least 16 characters. Store it securely for recovery.",
      );
    if (!(await this.fetch())) return;
    const ctx = this.bytes(
      "PeopleDesk chat backup v1|" + S.workspace_id + "|" + pid,
    );
    let priv, publicKeys;
    if (this.snapshot.identity) {
      const { public: pub, backup } = this.snapshot.identity;
      const key = await this.derive(pass, this.from64(backup.salt));
      try {
        priv = JSON.parse(
          this.decoder.decode(
            await crypto.subtle.decrypt(
              {
                name: "AES-GCM",
                iv: this.from64(backup.iv),
                additionalData: ctx,
              },
              key,
              this.from64(backup.cipher),
            ),
          ),
        );
      } catch {
        throw Error(
          "The chat passphrase did not unlock your keys. Your existing identity has been preserved.",
        );
      }
      publicKeys = pub;
    } else {
      const box = await crypto.subtle.generateKey(
        {
          name: "RSA-OAEP",
          modulusLength: 3072,
          publicExponent: new Uint8Array([1, 0, 1]),
          hash: "SHA-256",
        },
        true,
        ["encrypt", "decrypt"],
      );
      const sign = await crypto.subtle.generateKey(
        { name: "ECDSA", namedCurve: "P-256" },
        true,
        ["sign", "verify"],
      );
      priv = {
        box: await crypto.subtle.exportKey("jwk", box.privateKey),
        sign: await crypto.subtle.exportKey("jwk", sign.privateKey),
      };
      publicKeys = {
        box: await crypto.subtle.exportKey("jwk", box.publicKey),
        sign: await crypto.subtle.exportKey("jwk", sign.publicKey),
      };
      const salt = crypto.getRandomValues(new Uint8Array(16)),
        iv = crypto.getRandomValues(new Uint8Array(12));
      const key = await this.derive(pass, salt);
      const cipher = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv, additionalData: ctx },
        key,
        this.bytes(JSON.stringify(priv)),
      );
      if (S?.user.id !== pid) return;
      await api("identity-register", {
        person: pid,
        public: publicKeys,
        backup: {
          salt: this.b64(salt),
          iv: this.b64(iv),
          cipher: this.b64(cipher),
          iterations: 600000,
        },
      });
    }
    if (
      priv.box.n !== publicKeys.box.n ||
      priv.box.e !== publicKeys.box.e ||
      priv.sign.x !== publicKeys.sign.x ||
      priv.sign.y !== publicKeys.sign.y
    )
      throw Error(
        "Recovered identity does not match the registered public keys.",
      );
    const privateBox = await crypto.subtle.importKey(
      "jwk",
      priv.box,
      { name: "RSA-OAEP", hash: "SHA-256" },
      false,
      ["decrypt"],
    );
    const privateSign = await crypto.subtle.importKey(
      "jwk",
      priv.sign,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["sign"],
    );
    if (S?.user.id !== pid) return;
    this.keys = { box: privateBox, sign: privateSign, public: publicKeys };
    this.account = pid;
    await this.fetch();
    route("messages");
  },
  async trust(roster) {
    for (const [pid, identity] of Object.entries(roster)) {
      const fp = await this.hash(identity),
        storage = "pd-chat-pin:" + S.workspace_id + ":" + S.user.id + ":" + pid;
      if (pid === S.user.id && fp !== (await this.hash(this.keys.public)))
        throw Error(
          "This conversation does not match your recovered chat identity.",
        );
      const old = localStorage.getItem(storage);
      if (old && old !== fp)
        throw Error(
          "The encryption identity for " +
            name(pid) +
            " has changed. Compare fingerprints before continuing.",
        );
      if (!old) localStorage.setItem(storage, fp);
    }
  },
  async open(rid) {
    const opening = ++this.opening;
    if (!this.keys) throw Error("Unlock your chat identity first.");
    const room = this.snapshot.rooms.find((r) => r.id === rid);
    if (!room) return;
    await this.trust(room.roster);
    if (opening !== this.opening || !this.keys) return;
    this.room = room;
    this.older = [];
    this.hasMore = false;
    $("#conversation").innerHTML = this.conversationHTML();
    document
      .querySelectorAll(".conversation-link")
      .forEach((el) => el.classList.toggle("selected", el.dataset.id === rid));
    await this.load(false);
  },
  conversationHTML() {
    const r = this.room;
    return (
      '<header class="conversation-head"><div><h2>' +
      esc(this.title(r)) +
      "</h2><small>" +
      r.members.length +
      ' participants · encrypted messages</small></div><div class="inline">' +
      btn("Verify people", "chat-verify", "quiet", "shield") +
      ib("New group", "chat-new", "plus") +
      '</div></header><div class="message-log" id="message-log" aria-live="polite"></div><form id="composeform" class="message-compose"><label class="sr" for="message-text">Message</label><textarea id="message-text" name="message" placeholder="Write a private message…" maxlength="8000" rows="2" required></textarea><button class="btn" type="submit" aria-label="Send encrypted message">' +
      icon("send") +
      '</button></form><p class="chat-error error" id="chat-error"></p>'
    );
  },
  title(r) {
    return r.kind === "direct"
      ? r.members
          .filter((p) => p !== S.user.id)
          .map(name)
          .join(", ")
      : r.title;
  },
  async decode(item, room) {
    const p = item.envelope.payload;
    const expected = await this.hash(room.roster);
    if (
      p.sender !== item.sender ||
      p.room !== room.id ||
      p.workspace !== S.workspace_id ||
      p.roster !== expected ||
      !room.members.includes(p.sender)
    )
      throw Error("Identity check failed");
    const pub = await crypto.subtle.importKey(
      "jwk",
      room.roster[p.sender].sign,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"],
    );
    if (
      !(await crypto.subtle.verify(
        { name: "ECDSA", hash: "SHA-256" },
        pub,
        this.from64(item.envelope.signature),
        this.bytes(this.canonical(p)),
      ))
    )
      throw Error("Signature check failed");
    const raw = await crypto.subtle.decrypt(
      { name: "RSA-OAEP" },
      this.keys.box,
      this.from64(p.wraps[S.user.id]),
    );
    const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, [
      "decrypt",
    ]);
    const aad = this.bytes(
      this.canonical({
        workspace: p.workspace,
        room: p.room,
        sender: p.sender,
        id: p.id,
        roster: p.roster,
      }),
    );
    return this.decoder.decode(
      await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: this.from64(p.iv), additionalData: aad },
        key,
        this.from64(p.cipher),
      ),
    );
  },
  async load(older = false) {
    clearTimeout(this.timer);
    const room = this.room,
      account = this.account;
    if (!room || !this.keys || view !== "messages") return;
    const before =
      older && this.older.length ? this.older[0].sequence : undefined;
    try {
      const result = await api("messages-read", {
        room: room.id,
        ...(before ? { before } : {}),
      });
      if (this.room?.id !== room.id || this.account !== account) return;
      const firstLoad = this.older.length === 0;
      this.older = [
        ...new Map(
          [...this.older, ...result.messages].map((m) => [m.sequence, m]),
        ).values(),
      ].sort((a, b) => a.sequence - b.sequence);
      if (older || firstLoad) this.hasMore = result.has_more;
      const html = [];
      if (this.hasMore)
        html.push(btn("Load earlier messages", "chat-older", "quiet"));
      for (const item of this.older) {
        let message;
        try {
          message = await this.decode(item, room);
        } catch {
          message = "Unable to verify or decrypt this message.";
        }
        html.push(
          '<article class="message ' +
            (item.sender === account ? "outgoing" : "incoming") +
            '"><small>' +
            esc(name(item.sender)) +
            "</small><p>" +
            esc(message) +
            "</p><time>" +
            esc(item.created.slice(11, 16)) +
            " UTC</time></article>",
        );
      }
      if (
        this.room?.id !== room.id ||
        this.account !== account ||
        view !== "messages"
      )
        return;
      const log = $("#message-log");
      if (log) {
        const nearEnd =
          log.scrollHeight - log.scrollTop - log.clientHeight < 80;
        const markup =
          html.join("") ||
          '<div class="empty">Start the conversation. Only participants with their chat keys can read it.</div>';
        if (log.innerHTML !== markup) {
          log.innerHTML = markup;
          if (nearEnd && !older) log.scrollTop = log.scrollHeight;
        }
      }
    } catch (e) {
      const el = $("#chat-error");
      if (el) el.textContent = e.message;
    }
    if (
      this.room?.id === room.id &&
      this.account === account &&
      view === "messages"
    )
      this.timer = setTimeout(() => this.load(false), 3500);
  },
  async send(message) {
    if (this.sending) return;
    if (!this.keys || this.account !== S.user.id || !this.room)
      throw Error("Unlock private chat first.");
    this.sending = true;
    const room = this.room,
      account = this.account;
    try {
      await this.trust(room.roster);
      const id = crypto.randomUUID(),
        roster = await this.hash(room.roster),
        iv = crypto.getRandomValues(new Uint8Array(12));
      const key = await crypto.subtle.generateKey(
          { name: "AES-GCM", length: 256 },
          true,
          ["encrypt"],
        ),
        raw = await crypto.subtle.exportKey("raw", key);
      const header = {
        workspace: S.workspace_id,
        room: room.id,
        sender: account,
        id,
        roster,
      };
      const cipher = await crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv,
          additionalData: this.bytes(this.canonical(header)),
        },
        key,
        this.bytes(message),
      );
      const wraps = {};
      for (const pid of room.members) {
        const pub = await crypto.subtle.importKey(
          "jwk",
          room.roster[pid].box,
          { name: "RSA-OAEP", hash: "SHA-256" },
          false,
          ["encrypt"],
        );
        wraps[pid] = this.b64(
          await crypto.subtle.encrypt({ name: "RSA-OAEP" }, pub, raw),
        );
      }
      const payload = {
        v: 1,
        ...header,
        iv: this.b64(iv),
        cipher: this.b64(cipher),
        wraps,
      };
      const signature = this.b64(
        await crypto.subtle.sign(
          { name: "ECDSA", hash: "SHA-256" },
          this.keys.sign,
          this.bytes(this.canonical(payload)),
        ),
      );
      await api("message-send", {
        room: room.id,
        envelope: { payload, signature },
      });
      if (this.room?.id === room.id && this.account === account) {
        $("#message-text").value = "";
        await this.load(false);
        $("#message-log").scrollTop = $("#message-log").scrollHeight;
      }
    } finally {
      this.sending = false;
    }
  },
};
function messagesPage() {
  if (!Messenger.keys)
    return (
      heading(
        "Private conversations",
        "Direct messages and project groups, encrypted in your browser.",
      ) +
      '<section class="card encryption-welcome"><span class="big-symbol">' +
      icon("shield") +
      '</span><h2>Your conversations belong to you.</h2><p>Create or unlock your chat identity with a separate passphrase. Use the same passphrase to recover your encrypted keys on another device.</p><form id="keyform" class="formgrid">' +
      field("Chat passphrase (16+ characters)", "passphrase", "password") +
      '<button class="btn">Unlock private chat</button><div class="error" role="alert"></div></form><small>Keep the passphrase safe. Company administrators cannot recover it. Participant names and message times remain visible to the service.</small></section>'
    );
  const rooms = Messenger.snapshot?.rooms || [];
  return (
    heading(
      "Messages",
      "Your people, project conversations and shared context.",
      '<div class="inline">' +
        btn("Lock chat", "chat-lock", "quiet", "shield") +
        btn("New conversation", "chat-new", "btn", "plus") +
        "</div>",
    ) +
    '<section class="chat-workspace card"><aside class="conversation-list"><div class="cardhead"><h2>Conversations</h2>' +
    ib("Refresh conversations", "chat-refresh", "history") +
    "</div>" +
    rooms
      .map(
        (r) =>
          '<button class="conversation-link ' +
          (Messenger.room?.id === r.id ? "selected" : "") +
          '" data-act="chat-room" ' +
          da("id", r.id) +
          ">" +
          avatar(Messenger.title(r)) +
          "<span><strong>" +
          esc(Messenger.title(r)) +
          "</strong><small>" +
          esc(r.kind === "group" ? "Project group" : "Direct conversation") +
          "</small></span></button>",
      )
      .join("") +
    (rooms.length ? "" : empty("Use + to choose people or start a group.")) +
    '</aside><section id="conversation">' +
    (Messenger.room
      ? Messenger.conversationHTML()
      : '<div class="chat-placeholder">' +
        glyph("mail", "lilac") +
        "<h2>Choose a conversation</h2><p>Start with a colleague or bring a project team together.</p></div>") +
    "</section></section>"
  );
}
