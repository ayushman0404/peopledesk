/* Assistant workspace. Private message text is handled locally, never sent to the planner. */
sections.splice(
  1,
  0,
  ["assistant", "Assistant", "spark"],
  ["routines", "Routines", "clock"],
);
const Copilot = {
  turns: [],
  loaded: false,
  loading: false,
  busy: false,
  error: "",
  privateDraft: null,
  epoch: 0,
  draft: "",
  rules: [],
  routinesLoaded: false,
};
const priorReset = resetSession,
  priorDecoration = decorateWorkspace,
  priorAction = extraAction;
resetSession = function () {
  Copilot.epoch++;
  Object.assign(Copilot, {
    turns: [],
    loaded: false,
    loading: false,
    busy: false,
    error: "",
    privateDraft: null,
    draft: "",
    rules: [],
    routinesLoaded: false,
  });
  priorReset();
};
decorateWorkspace = function () {
  priorDecoration();
  document.body.classList.toggle("copilot-view", view === "assistant");
  if (view === "assistant" && !Copilot.loaded && !Copilot.loading)
    loadCopilot();
  if (view === "routines" && !Copilot.routinesLoaded) loadRoutines();
  const foot = $(".side-foot");
  if (foot && !$("#release-label"))
    foot.insertAdjacentHTML(
      "beforeend",
      '<small id="release-label" class="release-label">PeopleDesk 3 · local workspace</small>',
    );
};
async function loadCopilot() {
  const epoch = Copilot.epoch;
  Copilot.loading = true;
  try {
    const r = await api("assistant-history", {});
    if (epoch !== Copilot.epoch) return;
    Copilot.turns = r.turns;
    Copilot.loaded = true;
    Copilot.error = "";
  } catch (e) {
    if (epoch === Copilot.epoch) {
      Copilot.error = e.message;
      Copilot.loaded = true;
    }
  } finally {
    if (epoch === Copilot.epoch) {
      Copilot.loading = false;
      if (view === "assistant") draw();
    }
  }
}
function assistantPlan(p, oldVersion) {
  const labels = {
    assign: "Assign work",
    meeting: "Request meeting",
    email: "Prepare email",
    focus: "Schedule focus time",
    status: "Update task",
    routine: "Weekday task routine",
  };
  return (
    '<section class="execution-plan"><header><strong>Work plan</strong>' +
    pill(p.state) +
    "<small>Version " +
    p.version +
    "</small></header>" +
    p.steps
      .map(
        (s, i) =>
          '<div class="plan-step"><span class="step-symbol">' +
          icon(
            {
              assign: "work",
              meeting: "video",
              email: "mail",
              focus: "clock",
              status: "check",
              routine: "clock",
            }[s.kind],
          ) +
          "</span><div><strong>" +
          esc(s.title || s.reference || labels[s.kind]) +
          "</strong><p>" +
          esc(labels[s.kind]) +
          (s.person ? " · " + esc(s.person) : "") +
          (s.date ? " · " + esc(pretty(s.date)) : "") +
          (s.time
            ? " at " +
              esc(s.time) +
              " UTC" +
              (s.kind === "routine" ? " · every weekday" : " · 30 min")
            : "") +
          (s.status ? " · " + esc(s.status) : "") +
          "</p>" +
          (s.detail
            ? "<details><summary>Details</summary><p>" +
              esc(s.detail) +
              "</p></details>"
            : "") +
          "</div></div>",
      )
      .join("") +
    (p.state === "Ready"
      ? "<footer>" +
        btn(
          "Run plan",
          "co-run",
          "btn",
          "check",
          da("id", p.id) + da("version", p.version),
        ) +
        btn("Edit details", "co-edit", "btnline", "", da("id", p.id)) +
        btn("Cancel", "co-cancel", "quiet", "", da("id", p.id)) +
        "</footer>"
      : '<p class="plan-note">' +
        (p.state === "Completed"
          ? "Recorded below. Running again will not duplicate the work."
          : "No actions were created by this plan.") +
        "</p>") +
    "</section>"
  );
}
function copilotPage() {
  const prompts = [
    "Give me a workload brief",
    "Assign Karan to review the launch checklist tomorrow",
    "Draft an email to Karan asking for a launch update",
    "Message Karan: Can we review the launch tomorrow?",
  ];
  const turns = Copilot.turns
    .map((t) => {
      const b = t.body;
      return (
        '<article class="copilot-turn ' +
        (t.role === "user" ? "human" : "agent") +
        '"><div class="turn-byline">' +
        (t.role === "user" ? esc(S.user.name) : icon("spark") + " PeopleDesk") +
        '</div><p class="turn-text">' +
        esc(b.answer || "") +
        "</p>" +
        (b.sources?.length
          ? '<details class="evidence"><summary>' +
            b.sources.length +
            " supporting records</summary>" +
            b.sources
              .map(
                (s) =>
                  '<div class="source"><b>' +
                  esc(s.id) +
                  "</b>" +
                  esc(s.text) +
                  "</div>",
              )
              .join("") +
            "</details>"
          : "") +
        (b.plan &&
        Copilot.turns.findLast((x) => x.body.plan_id === b.plan_id) === t
          ? assistantPlan(b.plan)
          : "") +
        (b.receipts || [])
          .map(
            (r) =>
              '<button class="execution-receipt" data-act="co-receipt" ' +
              da("id", r.id) +
              da("destination", r.destination) +
              ">" +
              icon("check") +
              "<span><strong>" +
              esc(r.label) +
              "</strong><small>" +
              esc(r.title) +
              " · " +
              esc(r.id) +
              "</small></span>" +
              icon("book") +
              "</button>",
          )
          .join("") +
        (b.action
          ? btn("Review request", "co-legacy", "btnline", "", da("turn", t.id))
          : "") +
        "</article>"
      );
    })
    .join("");
  const privateDraft = Copilot.privateDraft;
  return (
    heading(
      "Your work, in motion.",
      "Describe the outcome. Review the plan. See what actually happened.",
      '<div class="inline">' +
        btn("Find anything", "co-search", "btnline", "grid") +
        btn("Refresh conversation", "co-refresh", "quiet", "history") +
        "</div>",
    ) +
    '<div class="copilot-layout"><section class="copilot-main card"><div id="copilot-log" class="copilot-log">' +
    (turns ||
      '<div class="copilot-welcome">' +
        glyph("spark", "lilac") +
        '<h2>What would you like to get done?</h2><p>Give someone a task, protect focus time, prepare a meeting or turn a decision into next steps.</p><div class="prompt-grid">' +
        prompts
          .map((q) => btn(q, "co-example", "prompt-card", "", da("q", q)))
          .join("") +
        "</div></div>") +
    (privateDraft
      ? '<section class="execution-plan private-preview"><header>' +
        icon("shield") +
        "<strong>Private message to " +
        esc(name(privateDraft.person)) +
        '</strong></header><p class="turn-text">' +
        esc(privateDraft.text) +
        '</p><p class="plan-note">This draft stays in this browser. Unlock Messages, then return here to send it encrypted.</p><footer>' +
        btn(
          Messenger.keys ? "Send private message" : "Unlock Messages",
          Messenger.keys ? "co-send-private" : "co-unlock",
          "btn",
          "mail",
        ) +
        btn("Discard", "co-discard", "quiet") +
        "</footer></section>"
      : "") +
    (Copilot.busy
      ? '<div class="copilot-progress" role="status"><i></i>Preparing your response… local model requests can take a minute.</div>'
      : "") +
    (Copilot.error
      ? '<p class="error copilot-error" role="alert">' +
        esc(Copilot.error) +
        "</p>"
      : "") +
    "</div>" +
    '<form id="copilotform" class="copilot-compose"><label class="sr" for="copilot-input">Tell PeopleDesk what to do</label><textarea id="copilot-input" name="q" maxlength="1500" rows="2" placeholder="Assign work, plan a meeting, or ask what needs attention…" required ' +
    (Copilot.busy ? "disabled" : "") +
    ">" +
    esc(Copilot.draft) +
    '</textarea><button type="submit" class="btn" ' +
    (Copilot.busy ? "disabled" : "") +
    ' aria-label="Send to PeopleDesk">' +
    icon("send") +
    '</button></form><p class="copilot-footnote">Company time: UTC · Plans respect your permissions · Assistant history is stored in this workspace</p></section>' +
    '<aside class="copilot-context"><section class="card tile"><span class="kicker">YOUR WORKSPACE</span><h2>' +
    esc(S.company) +
    "</h2><p>" +
    esc(roleName()) +
    " · " +
    esc(S.user.team) +
    '</p><div class="context-metric"><strong>' +
    S.tasks.filter((t) => t.status !== "Done").length +
    "</strong><span>visible unfinished tasks</span></div>" +
    btn(
      "Prioritise my work",
      "co-example",
      "btnline",
      "spark",
      da("q", "Give me a workload brief"),
    ) +
    "</section>" +
    '<section class="card tile"><h2>From conversation to action</h2><p>Tasks and focus blocks are created when you run a plan. Meetings and formal emails go to HR for approval.</p><p>Private messages use your browser chat keys. Provider accounts are connected in Connections.</p>' +
    btn(
      "Manage connections",
      "nav",
      "quiet",
      "plug",
      da("to", "integrations"),
    ) +
    "</section></aside></div>"
  );
}
function paintCopilot(scroll = true) {
  if (view !== "assistant") return;
  draw();
  if (scroll) $("#copilot-log")?.scrollTo(0, $("#copilot-log").scrollHeight);
}
async function copilotAsk(q) {
  if (Copilot.busy || !q.trim()) return;
  const epoch = Copilot.epoch;
  Copilot.draft = "";
  Copilot.error = "";
  // Explicit private messages never reach /assistant-talk or stored assistant history.
  if (/^(message|tell|send a message to)\b/i.test(q)) {
    const m = q.match(
      /^(?:message|tell|send a message to)\s+(.+?)(?::|\s+that\s+)([\s\S]+)$/i,
    );
    if (!m) {
      Copilot.error =
        "Use “Message Karan: your message”. The text stays in your browser.";
      paintCopilot();
      return;
    }
    const candidates = S.people.filter(
      (p) =>
        p.active &&
        [
          p.name.toLowerCase(),
          p.name.split(" ")[0].toLowerCase(),
          p.id.toLowerCase(),
        ].includes(m[1].trim().toLowerCase()),
    );
    if (candidates.length !== 1 || candidates[0].id === S.user.id) {
      Copilot.error = "Choose one colleague by full name.";
      paintCopilot();
      return;
    }
    Copilot.privateDraft = { person: candidates[0].id, text: m[2].trim() };
    paintCopilot();
    return;
  }
  Copilot.busy = true;
  Copilot.turns.push({ id: "pending", role: "user", body: { answer: q } });
  paintCopilot();
  try {
    await api("assistant-talk", { q });
    if (epoch !== Copilot.epoch) return;
    await loadCopilot();
  } catch (e) {
    if (epoch === Copilot.epoch) Copilot.error = e.message;
  } finally {
    if (epoch === Copilot.epoch) {
      Copilot.busy = false;
      paintCopilot();
      $("#copilot-input")?.focus();
    }
  }
}
function findPlan(id) {
  return Copilot.turns.map((t) => t.body.plan).find((p) => p?.id === id);
}
function planPerson(value) {
  if (value === "me") return value;
  const matches = S.people.filter((p) =>
    [p.id, p.name, p.name.split(" ")[0]].some(
      (v) => v.toLowerCase() === value.toLowerCase(),
    ),
  );
  return matches.length === 1 ? matches[0].name : "";
}
function editPlan(id) {
  const p = findPlan(id);
  if (!p) return;
  showModal(
    "Review your work plan",
    '<form id="editplanform" class="formgrid" ' +
      da("id", id) +
      da("version", p.version) +
      ">" +
      p.steps
        .map(
          (s, i) =>
            '<fieldset class="plan-fields"><legend>Step ' +
            (i + 1) +
            " · " +
            esc(s.kind) +
            "</legend>" +
            (["assign", "meeting", "email", "routine"].includes(s.kind)
              ? field(
                  "Colleague",
                  "person-" + i,
                  "select",
                  planPerson(s.person),
                  true,
                  [
                    ["", "Choose a colleague"],
                    ["me", "Me"],
                    ...S.people
                      .filter((p) => p.active)
                      .map((p) => [p.name, p.name]),
                  ],
                )
              : "") +
            (s.kind !== "status"
              ? field("Title", "title-" + i, "text", s.title)
              : field(
                  "Task",
                  "reference-" + i,
                  "select",
                  s.reference,
                  true,
                  S.tasks.map((t) => [t.id, t.title]),
                )) +
            (["assign", "meeting", "focus", "routine"].includes(s.kind)
              ? field("Date", "date-" + i, "date", s.date)
              : "") +
            (["meeting", "focus", "routine"].includes(s.kind)
              ? field("Time (UTC)", "time-" + i, "time", s.time)
              : "") +
            (s.kind === "status"
              ? field(
                  "Status",
                  "status-" + i,
                  "select",
                  s.status,
                  true,
                  ["Open", "In progress", "Blocked", "Done"].map((s) => [s, s]),
                )
              : "") +
            (["assign", "email", "meeting"].includes(s.kind)
              ? field(
                  s.kind === "email" ? "Email body" : "Details",
                  "detail-" + i,
                  "textarea",
                  s.detail,
                  s.kind === "email",
                )
              : "") +
            "</fieldset>",
        )
        .join("") +
      '<div class="error"></div><button type="submit" class="btn">Save plan</button></form>',
  );
}
function searchWorkspace(q = "") {
  const items = [
    ...S.tasks.map((t) => ({
      kind: "task",
      id: t.id,
      title: t.title,
      sub: "Task · " + name(t.owner),
    })),
    ...S.events.map((e) => ({
      kind: "event",
      id: e.id,
      title: e.title,
      sub: "Calendar · " + e.starts,
    })),
    ...S.people.map((p) => ({
      kind: "person",
      id: p.id,
      title: p.name,
      sub: p.team + " · " + p.title,
    })),
    ...S.policies.map((p) => ({
      kind: "policy",
      id: p.id,
      title: p.title,
      sub: p.body,
    })),
    ...S.files.map((f) => ({
      kind: "file",
      id: f.id,
      title: f.name,
      sub: "Workspace file",
    })),
  ];
  return (
    items
      .filter((i) =>
        (i.title + " " + i.sub).toLowerCase().includes(q.toLowerCase()),
      )
      .slice(0, 20)
      .map(
        (i) =>
          '<button class="row search-hit" data-act="co-found" ' +
          da("id", i.id) +
          da("kind", i.kind) +
          '><span class="grow"><strong>' +
          esc(i.title) +
          "</strong><small>" +
          esc(i.sub.slice(0, 100)) +
          "</small></span></button>",
      )
      .join("") || empty("No matching records in your workspace.")
  );
}
extraAction = async function (b) {
  const a = b.dataset.act,
    id = b.dataset.id;
  if (a === "chat-toggle") {
    chatOpen = false;
    $("#assistant").hidden = true;
    route("assistant");
    return true;
  }
  if (!a.startsWith("co-")) return priorAction(b);
  if (a === "co-routine-new") {
    routineForm();
    return true;
  }
  if (a === "co-routine-toggle") {
    await api("routine-toggle", { id, state: b.dataset.state });
    await loadRoutines();
    return true;
  }
  if (a === "co-example") {
    await copilotAsk(b.dataset.q);
    return true;
  }
  if (a === "co-refresh") {
    await loadCopilot();
    return true;
  }
  if (a === "co-edit") {
    editPlan(id);
    return true;
  }
  if (a === "co-discard") {
    Copilot.privateDraft = null;
    paintCopilot();
    return true;
  }
  if (a === "co-unlock") {
    route("messages");
    return true;
  }
  if (a === "co-send-private") {
    const d = Copilot.privateDraft;
    if (!d) return true;
    await Messenger.fetch();
    if (!Messenger.snapshot.keys.some((k) => k.person === d.person))
      throw Error(
        name(d.person) +
          " must activate Messages before you can send an encrypted message.",
      );
    const r = await api("room-create", {
      kind: "direct",
      members: [d.person],
      title: "Conversation",
    });
    await Messenger.fetch();
    route("messages");
    await Messenger.open(r.id);
    await Messenger.send(d.text);
    Copilot.privateDraft = null;
    toast("Private message sent.");
    return true;
  }
  if (a === "co-run" || a === "co-cancel") {
    await api(a === "co-run" ? "assistant-run" : "assistant-cancel", {
      id,
      version: Number(b.dataset.version),
    });
    Copilot.routinesLoaded = false;
    await refresh();
    await loadCopilot();
    paintCopilot();
    return true;
  }
  if (a === "co-receipt") {
    if (b.dataset.destination === "routine") {
      Copilot.routinesLoaded = false;
      route("routines");
      return true;
    }
    if (b.dataset.destination === "task") taskDetail(id);
    else if (b.dataset.destination === "event") eventDetail(id);
    else requestDetail(id);
    return true;
  }
  if (a === "co-legacy") {
    const t = Copilot.turns.find((t) => String(t.id) === b.dataset.turn);
    if (t) openForm(t.body.action.type, t.body.action);
    return true;
  }
  if (a === "co-search") {
    showModal(
      "Find in your workspace",
      '<label class="field">Search people, tasks, meetings, policies and files<input id="workspace-search" autocomplete="off" placeholder="Search your accessible records…"></label><div id="search-results">' +
        searchWorkspace() +
        "</div>",
    );
    $("#workspace-search").focus();
    return true;
  }
  if (a === "co-found") {
    modal.close();
    if (b.dataset.kind === "task") taskDetail(id);
    else if (b.dataset.kind === "event") eventDetail(id);
    else if (b.dataset.kind === "person") personDetail(id);
    else if (b.dataset.kind === "file") {
      showModal(
        "Workspace file",
        '<a class="btn" href="/export/shared/' +
          encodeURIComponent(id) +
          '">Download file</a>',
      );
    } else {
      const p = S.policies.find((p) => p.id === id);
      showModal(p.title, '<p class="turn-text">' + esc(p.body) + "</p>");
    }
    return true;
  }
  return false;
};
document.addEventListener("input", (e) => {
  if (e.target.id === "workspace-search")
    $("#search-results").innerHTML = searchWorkspace(e.target.value);
  if (e.target.id === "copilot-input") Copilot.draft = e.target.value;
});
document.addEventListener("keydown", (e) => {
  if (S && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    extraAction({ dataset: { act: "co-search" } });
  }
  if (e.target.id === "copilot-input" && e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    copilotAsk(e.target.value);
  }
});
document.addEventListener(
  "submit",
  async (e) => {
    const f = e.target;
    if (!["copilotform", "editplanform", "routineform"].includes(f.id)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (f.id === "copilotform") return copilotAsk(new FormData(f).get("q"));
    if (f.id === "routineform") {
      const button = f.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        await api("assistant-create", {
          steps: [{ ...Object.fromEntries(new FormData(f)), kind: "routine" }],
        });
        modal.close();
        route("assistant");
        await loadCopilot();
      } catch (e) {
        f.querySelector(".error").textContent = e.message;
      } finally {
        button.disabled = false;
      }
      return;
    }
    const p = findPlan(f.dataset.id),
      data = new FormData(f),
      steps = p.steps.map((s, i) =>
        Object.fromEntries(
          Object.entries(s).map(([k, v]) => [
            k,
            data.has(k + "-" + i) ? data.get(k + "-" + i) : v,
          ]),
        ),
      );
    const button = f.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await api("assistant-edit", {
        id: p.id,
        version: Number(f.dataset.version),
        steps,
      });
      modal.close();
      await loadCopilot();
    } catch (e) {
      f.querySelector(".error").textContent = e.message;
    } finally {
      button.disabled = false;
    }
  },
  true,
);
async function loadRoutines() {
  const epoch = Copilot.epoch;
  Copilot.routinesLoaded = true;
  try {
    const r = await api("routine-list", {});
    if (epoch !== Copilot.epoch) return;
    Copilot.rules = r.rules;
    if (view === "routines") draw();
  } catch (e) {
    toast(e.message);
  }
}
function routineForm() {
  showModal(
    "Automate weekday work",
    '<form id="routineform" class="formgrid">' +
      field("Task title", "title") +
      field(
        "Responsible colleague",
        "person",
        "select",
        S.user.name,
        true,
        S.people.filter((p) => p.active).map((p) => [p.name, p.name]),
      ) +
      field("First date", "date", "date", S.today) +
      field("Time (UTC)", "time", "time", "09:00") +
      field("Instructions", "detail", "textarea", "", false) +
      '<p class="summary-note">Creates one task each weekday while the company service is running. Missed runs collapse to one catch-up task. You can pause it any time.</p><div class="error"></div><button type="submit" class="btn">Review routine</button></form>',
  );
}
function routinesPage() {
  return (
    heading(
      "Work that keeps moving.",
      "Schedule recurring weekday tasks with a visible record of every run.",
      btn("Create routine", "co-routine-new", "btn", "plus"),
    ) +
    '<p class="notice">The company service must stay running. Routines check every 30 seconds and use UTC. Access changes pause affected routines.</p><br>' +
    (Copilot.rules.length
      ? '<div class="tiles">' +
        Copilot.rules
          .map(
            (r) =>
              '<section class="card tile">' +
              pill(r.state) +
              "<h2>" +
              esc(r.title) +
              "</h2><p>For " +
              esc(name(r.owner)) +
              " · weekdays at " +
              esc(r.clock) +
              " UTC</p><p>Next date: " +
              esc(r.next_date) +
              "</p><small>" +
              esc(r.last_note || "Awaiting first run") +
              "</small>" +
              btn(
                r.state === "Active" ? "Pause routine" : "Resume routine",
                "co-routine-toggle",
                "btnline",
                "",
                da("id", r.id) +
                  da("state", r.state === "Active" ? "Paused" : "Active"),
              ) +
              "<details><summary>Recent runs (" +
              r.runs.length +
              ")</summary>" +
              r.runs
                .map(
                  (run) =>
                    '<button class="row" data-act="task-detail" ' +
                    da("id", run.task) +
                    ">" +
                    esc(run.scheduled) +
                    " · " +
                    esc(run.task) +
                    "</button>",
                )
                .join("") +
              "</details></section>",
          )
          .join("") +
        "</div>"
      : card(
          "Your routines",
          empty(
            "Create a routine for recurring checks, reviews or daily preparation.",
          ),
        ))
  );
}
boot();
