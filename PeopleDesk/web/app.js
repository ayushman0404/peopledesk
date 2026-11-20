"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  logo: "M3 18h6v-6H3zm6-6h6V6H9zm6 6h6v-6h-6z",
  home: "m3 10 9-7 9 7v10h-6v-7H9v7H3z",
  inbox: "M4 4h16l2 11v5H2v-5zm-1 11h5l2 3h4l2-3h5",
  work: "M3 7h18v13H3zM8 7V4h8v3m-13 6h18",
  cal: "M4 6h16v15H4zM8 3v6m8-6v6M4 11h16",
  people:
    "M16 21v-3a5 5 0 0 0-10 0v3m10-17a4 4 0 0 1 0 8m3 3a4 4 0 0 1 3 4M15 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  book: "M3 4q5-1 9 3 4-4 9-3v15q-5-1-9 2-4-3-9-2zm9 3v14",
  plug: "m7 3 3 3m4-6 3 3M5 10l9-8 6 6-8 8zm3 4-5 5",
  spark: "m12 3 2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z",
  arrow: "m9 5 7 7-7 7",
  left: "m15 5-7 7 7 7",
  plus: "M12 4v16M4 12h16",
  close: "m5 5 14 14m0-14L5 19",
  check: "m4 12 5 5L20 6",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  leaf: "M4 19C1 8 9 3 21 3c0 12-5 19-15 15m-3 3L16 8",
  shield: "m12 3 8 3v6c0 5-5 8-8 10-3-2-8-5-8-10V6z",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0m-9-5v6l4 2",
  list: "M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1",
  grid: "M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z",
  menu: "M3 6h18M3 12h18M3 18h18",
  send: "m3 3 19 9-19 9 4-9zm4 9h14",
  handoff: "M3 7h14m-4-4 4 4-4 4m8 6H7m4-4-4 4 4 4",
  loc: "M5 4h14v16H5zM9 8h2m2 0h2m-6 4h2m2 0h2",
  video: "M3 6h12v12H3zm12 4 6-3v10l-6-3",
  user: "M8 8a4 4 0 1 1 8 0 4 4 0 1 1-8 0m-3 13v-2a7 7 0 0 1 14 0v2",
  history: "M3 12a9 9 0 1 0 3-7l-3 3m0-5v5h5m4 0v5l4 2",
};
const icon = (k) =>
  `<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[k] || paths.list}"/></svg>`;
const btn = (label, act, style = "btnline", ic = "", data = "") =>
  `<button type="button" class="${style}" data-act="${esc(act)}" ${data}>${ic ? icon(ic) : ""}${esc(label)}</button>`;
const ib = (label, act, ic, data = "") =>
  `<button type="button" class="iconbtn" aria-label="${esc(label)}" title="${esc(label)}" data-act="${act}" ${data}>${icon(ic)}</button>`;
const da = (key, value) => `data-${key}="${esc(value)}"`;
const pill = (s) => `<span class="pill ${esc(s)}">${esc(s)}</span>`;
const empty = (s) => `<div class="empty">${esc(s)}</div>`;
const initials = (s) =>
  s
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
const avatar = (s, i = 0) =>
  `<span aria-hidden="true" class="avatar ${["", "peach", "lilac", "blue"][i % 4]}">${esc(initials(s))}</span>`;
const glyph = (k, c = "") => `<span class="glyph ${c}">${icon(k)}</span>`;
const name = (id) =>
  S.people.find((p) => p.id === id)?.name || id || "Unassigned";
const hr = () => S?.user.role === "hr";
const jdate = (d) => new Date(d + "T12:00:00Z");
const pretty = (d, long = false) =>
  new Intl.DateTimeFormat("en-GB", {
    ...(long ? { weekday: "long", year: "numeric" } : {}),
    day: "numeric",
    month: long ? "long" : "short",
    timeZone: "UTC",
  }).format(jdate(d));
const dateCode = (d) => d.toISOString().slice(0, 10);
const nextDate = (offset) => {
  const d = jdate(S.today);
  d.setUTCDate(d.getUTCDate() + offset);
  return dateCode(d);
};
const sections = [
  ["overview", "Overview", "home"],
  ["approvals", "Approvals", "inbox"],
  ["work", "Work & handoffs", "work"],
  ["calendar", "Calendar", "cal"],
  ["directory", "Directory", "people"],
  ["handbook", "Handbook", "book"],
  ["integrations", "Integrations", "plug"],
];
const kindInfo = {
  Leave: ["leaf", ""],
  "Human review": ["shield", "peach"],
  Email: ["mail", "lilac"],
  Meeting: ["cal", "blue"],
  Task: ["list", ""],
};
let S = null,
  info,
  view = "overview",
  workTab = "Tasks",
  filter = "Pending",
  findText = "",
  selectedDay = "",
  calMonth = "",
  messages = [],
  busyChat = false,
  chatOpen = false,
  modalContext = null,
  menuOpen = false;
async function api(op, data, token) {
  const options = { credentials: "same-origin", cache: "no-store" };
  if (data !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(token ? { ...data, token } : data);
  }
  const res = await fetch("/api/" + op, options),
    out = await res.json();
  if (!res.ok) throw Error(out.error || "The request could not be completed.");
  return out;
}
async function refresh() {
  S = await api("state");
  if (!selectedDay) selectedDay = S.today;
  if (!calMonth) calMonth = selectedDay.slice(0, 7);
  draw();
}
let toastTimer;
function toast(s) {
  $("#toast").textContent = s;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").textContent = ""), 4200);
}
function showLogin() {
  S = null;
  $("#workspace").innerHTML =
    `<div class="login"><div class="card loginbox"><div class="brand"><span class="mark">${icon("logo")}</span>PeopleDesk</div><h1>${esc(info.company)}</h1><p class="sub">${info.demo ? "Choose a role to explore the fictional company." : "Sign in with your company email and password."}</p>${info.demo ? `<div class="form-actions">${btn("Employee workspace", "login-employee")}${btn("HR workspace", "login-hr", "btn")}</div>` : ""}<form id="loginform" class="formgrid">${field("Work email", "email", "email")}${field("Password", "password", "password")}<div class="error" role="alert"></div><button class="btn">Sign in</button></form></div></div>`;
}
async function boot() {
  try {
    info = await api("info");
    if (!info.signed && info.demo && !sessionStorage.getItem("pd_signedout"))
      await api("login", { demo: "hr" });
    else if (!info.signed) return showLogin();
    await refresh();
    route(location.hash.slice(1) || "overview");
  } catch (e) {
    $("#workspace").innerHTML =
      `<main class="loading">${esc(e.message)} ${btn("Retry", "boot")}</main>`;
  }
}
function route(v) {
  if (!sections.some((s) => s[0] === v) || (!hr() && v === "members"))
    v = "overview";
  view = v;
  menuOpen = false;
  findText = "";
  history.replaceState(null, "", "#" + v);
  draw();
}
function card(title, body, right = "") {
  return `<section class="card"><div class="cardhead"><h2>${esc(title)}</h2>${right}</div>${body}</section>`;
}
function heading(title, sub, action = "") {
  return `<header class="headline"><div><h1>${esc(title)}</h1><p class="sub">${esc(sub)}</p></div>${action}</header>`;
}
function draw() {
  if (!S) return;
  const pending = S.requests.filter((r) => r.status === "Pending").length;
  const nav = sections
    .filter((x) => hr() || x[0] !== "members")
    .map(
      ([id, label, ic]) =>
        `<button class="nav ${view === id ? "active" : ""}" data-act="nav" data-to="${id}">${icon(ic)}<span>${!hr() && id === "approvals" ? "My requests" : !hr() && id === "work" ? "My work" : label}</span>${id === "approvals" && pending ? `<span class="count">${pending}</span>` : ""}</button>`,
    )
    .join("");
  const section = sections.find((x) => x[0] === view)[1];
  const pages = {
    overview,
    approvals,
    work,
    calendarPage,
    directory,
    handbook,
    integrations,
    team: teamPage,
    messages: messagesPage,
    files: filesPage,
    members: membersPage,
    assistant: copilotPage,
    routines: routinesPage,
  };
  $("#workspace").innerHTML =
    `<div class="shell ${menuOpen ? "openmenu" : ""}"><aside class="sidebar"><div class="brand"><span class="mark">${icon("logo")}</span>PeopleDesk <button class="mobilemenu quiet" aria-label="Close menu" data-act="menu">${icon("close")}</button></div><div class="tenant">${icon("loc")}<b>${esc(S.company)}</b></div><nav aria-label="Workspace">${nav}</nav><div class="side-foot"><div class="usercard">${avatar(S.user.name)}<div><strong>${esc(S.user.name)}</strong><small>${hr() ? "HR administrator" : "Employee workspace"}</small></div></div><div>${S.mode === "demo" ? btn(hr() ? "View employee demo" : "View HR demo", hr() ? "login-employee" : "login-hr", "sidebtn") : ""} ${S.mode === "company" ? btn("Change password", "new-password", "sidebtn") : ""} ${btn("Sign out", "logout", "sidebtn")}${hr() && location.hostname === "127.0.0.1" ? btn("Stop local service", "stop-local", "sidebtn") : ""}</div></div></aside><main class="content"><div class="topbar"><span class="crumb"><button class="mobilemenu iconbtn" aria-label="Open menu" data-act="menu">${icon("menu")}</button>Workspace ${icon("arrow")} <b>${esc(section)}</b></span><div class="inline">${S.mode === "demo" ? '<span class="badgenote">Demo company</span>' : ""}<span class="tag badgewide"><i class="dot"></i>${hr() ? "HR workspace" : "Employee workspace"}</span></div></div><div class="view">${pages[view === "calendar" ? "calendarPage" : view]()}</div></main></div><button class="assistant-open" data-act="chat-toggle">${icon("spark")} Ask PeopleDesk</button>`;
  if (chatOpen) renderChat();
  decorateWorkspace();
}
function reqRow(r) {
  const [ic, c] = kindInfo[r.kind] || ["inbox", ""];
  return `<button class="row" data-act="request-detail" ${da("id", r.id)}>${glyph(ic, c)}<span class="grow"><strong>${esc(r.title)}</strong><small>${esc(r.kind)} · ${esc(name(r.creator))}</small></span>${pill(r.status)}${icon("arrow")}</button>`;
}
function taskRow(t) {
  return `<button class="row" data-act="task-detail" ${da("id", t.id)}><span class="check ${t.status === "Done" ? "done" : ""}">${t.status === "Done" ? icon("check") : ""}</span><span class="grow"><strong>${esc(t.title)}</strong><small>${esc(name(t.owner))}${t.helper ? " + " + esc(name(t.helper)) : ""} · ${esc(pretty(t.due))}</small></span>${icon("arrow")}</button>`;
}
function stat(value, label, ic, to) {
  return `<button class="stat" data-act="nav" data-to="${to}"><span class="tileicon">${icon(ic)}</span><span><strong>${value}</strong><small>${esc(label)}</small></span></button>`;
}
function eventOn(e, d) {
  return e.starts < d + "T24:00" && e.ends > d + "T00:00";
}
function calendarGrid(large = false) {
  const [y, m] = calMonth.split("-").map(Number),
    start = new Date(Date.UTC(y, m - 1, 1, 12));
  const offset = (start.getUTCDay() + 6) % 7;
  const n = new Date(Date.UTC(y, m, 0)).getUTCDate();
  let cells = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    .map((s) => `<span class="wk">${s}</span>`)
    .join("");
  for (let i = 0; i < Math.ceil((offset + n) / 7) * 7; i++) {
    const d = new Date(Date.UTC(y, m - 1, 1 - offset + i, 12)),
      key = dateCode(d);
    cells += `<button class="date ${key === selectedDay ? "active" : ""} ${key === S.today ? "current" : ""} ${d.getUTCMonth() !== m - 1 ? "faded" : ""} ${S.events.some((e) => eventOn(e, key)) ? "has" : ""}" data-act="day" data-date="${key}" aria-label="${esc(pretty(key, true))}" aria-pressed="${key === selectedDay}">${d.getUTCDate()}</button>`;
  }
  const month = new Intl.DateTimeFormat("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(start);
  return card(
    month,
    `<div class="calendar ${large ? "large" : ""}">${cells}</div>`,
    `<div class="inline">${ib("Previous month", "month-prev", "left")}${ib("Next month", "month-next", "arrow")}</div>`,
  );
}
function agenda() {
  const a = S.events.filter((e) => eventOn(e, selectedDay));
  return card(
    "Agenda · " + pretty(selectedDay),
    a
      .map(
        (e) =>
          `<button class="row" data-act="event-detail" ${da("id", e.id)}>${glyph("clock", "lilac")}<span class="grow"><strong>${esc(e.title)}</strong><small>${esc(e.starts.slice(11))}–${esc(e.ends.slice(11))} UTC</small></span>${icon("arrow")}</button>`,
      )
      .join("") || empty("No events scheduled for this date."),
    ib("Schedule a meeting", "new-meeting", "plus"),
  );
}
function overview() {
  const p = S.requests.filter((r) => r.status === "Pending"),
    t = S.tasks.filter((t) => t.status === "Open"),
    events = S.events.filter((e) => eventOn(e, S.today));
  const welcome = hr() ? "Operations overview" : "My workspace";
  return (
    heading(
      welcome,
      pretty(S.today, true),
      btn("New request", "new-request", "btn", "plus"),
    ) +
    `<div class="stats">${stat(p.length, hr() ? "Awaiting approval" : "Pending requests", "inbox", "approvals")}${stat(t.length, hr() ? "Open tasks" : "My open tasks", "work", "work")}${stat(events.length, "Meetings today", "cal", "calendar")}</div><div class="dashboard"><div class="stack">${card(hr() ? "Approval inbox" : "My requests", p.slice(0, 5).map(reqRow).join("") || empty("No pending requests."), btn("View all", "nav", "quiet", "", da("to", "approvals")))}${card(hr() ? "Team work queue" : "My tasks", t.slice(0, 4).map(taskRow).join("") || empty("No open tasks."), btn("View all", "nav", "quiet", "", da("to", "work")))}</div><div class="stack">${calendarGrid()}${agenda()}</div></div>${reminderList()}`
  );
}
function approvals() {
  const matching = S.requests.filter(
    (r) => filter === "All" || r.status === filter,
  );
  return (
    heading(
      hr() ? "Approval inbox" : "My requests",
      hr()
        ? "Review requests and keep a record of the decision."
        : "Track requests you submitted.",
      btn("New request", "new-request", "btn", "plus"),
    ) +
    `<div class="toolbar">${["Pending", "Approved", "Declined", "All"].map((f) => btn(f, "filter", "chip " + (filter === f ? "on" : ""), "", da("filter", f))).join("")}</div><section class="card">${matching.map(reqRow).join("") || empty("No matching requests.")}</section>`
  );
}
function work() {
  const tabs = hr()
    ? ["Tasks", "Workflows", "Handoffs", "Activity"]
    : ["Tasks"];
  if (!tabs.includes(workTab)) workTab = "Tasks";
  const action =
    workTab === "Tasks" && hr()
      ? btn("Assign task", "new-task", "btn", "plus")
      : workTab === "Workflows"
        ? btn("Start workflow", "new-flow", "btn", "plus")
        : workTab === "Handoffs"
          ? btn("Build handoff", "new-handoff", "btn", "spark")
          : "";
  let body = "";
  if (workTab === "Tasks")
    body = card(
      "Assigned work",
      S.tasks.map(taskRow).join("") || empty("No assigned tasks."),
    );
  if (workTab === "Workflows")
    body = `<div class="tiles">${
      S.flows
        .map((f) => {
          const ts = S.tasks.filter((t) => t.flow === f.id),
            done = ts.filter((t) => t.status === "Done").length;
          return `<div class="card tile">${glyph("work")}<h2>${esc(f.title)}</h2><p>${esc(f.kind)} · ${esc(name(f.subject))}</p><div class="prog"><i style="width:${(100 * done) / (ts.length || 1)}%"></i></div><small>${done} of ${ts.length} tasks complete</small>${btn("Open checklist", "flow-detail", "btnline", "", da("id", f.id))}</div>`;
        })
        .join("") || empty("Start a workflow to create its checklist.")
    }</div>`;
  if (workTab === "Handoffs")
    body = card(
      "Meeting handoffs",
      S.handoffs
        .map(
          (h) =>
            `<button class="row" data-act="handoff-detail" ${da("id", h.id)}>${glyph("handoff", "lilac")}<span class="grow"><strong>${esc(h.items[0]?.source || h.id)}</strong><small>${esc(h.id)} · ${h.items.length} source-linked items</small></span>${icon("arrow")}</button>`,
        )
        .join("") ||
        empty(
          "Build a handoff from meeting notes. Review an item to turn it into an assignment or HR case.",
        ),
    );
  if (workTab === "Activity")
    body = card(
      "Activity history",
      S.activity
        .map(
          (a) =>
            `<div class="row">${glyph("history")}<div class="grow"><strong>${esc(a.verb)}</strong><small>${esc(a.object)} · ${esc(name(a.actor))} · ${esc(a.at.replace("T", " "))} UTC</small></div></div>`,
        )
        .join("") || empty("No activity recorded."),
    );
  return (
    heading(
      hr() ? "Work & handoffs" : "My work",
      hr()
        ? "Coordinate assignments, checklists and meeting follow-ups."
        : "Tasks assigned to you or shared with you.",
      action,
    ) +
    `<div class="tabbar">${tabs.map((t) => btn(t, "worktab", t === workTab ? "on" : "", "", da("tab", t))).join("")}</div>` +
    body
  );
}
function reminderList() {
  const ids = S.reminders || [];
  if (!ids.length) return "";
  return (
    "<br>" +
    card(
      "Follow-ups due",
      ids
        .slice(0, 5)
        .map((id) => {
          const t = S.tasks.find((x) => x.id === id);
          return (
            '<div class="row">' +
            glyph("clock", "peach") +
            '<div class="grow"><strong>' +
            esc(t.title) +
            "</strong><small>" +
            esc(name(t.owner)) +
            " · " +
            esc(pretty(t.due)) +
            "</small></div>" +
            btn("Tomorrow", "snooze", "quiet", "", da("id", id)) +
            btn("Open", "task-detail", "btnline", "", da("id", id)) +
            "</div>"
          );
        })
        .join(""),
    )
  );
}
function calendarPage() {
  return (
    heading(
      "People calendar",
      "Schedule team work in company time (UTC).",
      '<div class="inline">' +
        btn("Work block", "new-block", "btnline", "clock") +
        btn("Schedule meeting", "new-meeting", "btn", "plus") +
        "</div>",
    ) +
    `<div class="two">${calendarGrid(true)}<div class="stack">${agenda()}${card(
      "Tasks due · " + pretty(selectedDay),
      S.tasks
        .filter((t) => t.due === selectedDay)
        .map(taskRow)
        .join("") || empty("No tasks due on this date."),
    )}</div></div>`
  );
}
function directory() {
  return (
    heading(
      "Employee directory",
      `${S.people.length} people in ${S.company}.`,
      hr() ? btn("Add employee", "new-person", "btn", "plus") : "",
    ) +
    `<div class="toolbar"><input class="search" id="people-search" placeholder="Find a name, team or role" aria-label="Search employees" value="${esc(findText)}"></div><div class="card" id="directory-list">${directoryRows()}</div>`
  );
}
function directoryRows() {
  return (
    S.people
      .filter((p) =>
        [p.name, p.team, p.title]
          .join(" ")
          .toLowerCase()
          .includes(findText.toLowerCase()),
      )
      .map(
        (p, i) =>
          `<button class="row" data-act="person-detail" ${da("id", p.id)}>${avatar(p.name, i)}<span class="grow"><strong>${esc(p.name)}</strong><small>${esc(p.title)} · ${esc(p.team)}</small></span>${icon("arrow")}</button>`,
      )
      .join("") || empty("No employees match this search.")
  );
}
function handbook() {
  return (
    heading(
      "Company handbook",
      "Published policies available to employees and the assistant.",
      hr() ? btn("Add policy", "new-policy", "btn", "plus") : "",
    ) +
    `<div class="tiles">${S.policies.map((p) => `<section class="card tile">${glyph("book")}<small>${esc(p.id)} · v${esc(p.version)}</small><h2>${esc(p.title)}</h2><p>${esc(p.body)}</p>${hr() ? btn("Edit policy", "edit-policy", "quiet", "", da("id", p.id)) : ""}</section>`).join("") || empty("HR has not published any policies.")}</div>`
  );
}
function integrations() {
  const g = S.integrations;
  const demo = S.mode === "demo";
  return (
    heading(
      "Integrations",
      "Manage account connections and control when an approved item leaves the workspace.",
    ) +
    (demo
      ? `<p class="notice">Demo company · use .ics and .eml exports here. Live account linking is available in company mode.</p><br>`
      : "") +
    `<div class="tiles">${[
      [
        "Google Calendar",
        "cal",
        "Refresh the next 31 days of your primary calendar and publish approved meeting invitations.",
      ],
      [
        "Gmail",
        "mail",
        "Create an approved draft in Gmail, then choose whether to send it.",
      ],
      [
        "Zoom",
        "video",
        "Create an approved Zoom meeting and attach the returned join link to the calendar event.",
      ],
    ]
      .map(
        ([title, k, desc]) =>
          `<section class="card tile">${glyph(k, "blue")}<h2>${title}</h2><p>${desc}</p><small>${demo ? "Local demo" : title === "Zoom" ? (g.zoomConfigured ? "Credentials configured" : "Configuration required") : g.googleLinked ? "Google connected" : g.googleConfigured ? "Ready to connect" : "Configuration required"}</small>${!demo && (title === "Zoom" ? g.zoomConfigured : g.googleConfigured) ? btn(title === "Zoom" ? "Test credentials" : g.googleLinked ? (title === "Gmail" ? "Disconnect Google" : "Refresh calendar") : "Connect Google", title === "Zoom" ? "test-zoom" : g.googleLinked ? (title === "Gmail" ? "disconnect-google" : "refresh-calendar") : "connect-google") : ""}</section>`,
      )
      .join("")}</div>`
  );
}

const modal = $("#modal");
const options = (items, sel) =>
  items
    .map(
      ([v, label]) =>
        `<option value="${esc(v)}" ${v === sel ? "selected" : ""}>${esc(label)}</option>`,
    )
    .join("");
const personOptions = () => S.people.map((p) => [p.id, p.name]);
function field(
  label,
  n,
  type = "text",
  value = "",
  required = true,
  items = [],
) {
  const a = `name="${esc(n)}" ${required ? "required" : ""}`,
    v = esc(value);
  let node;
  if (type === "select")
    node = `<select ${a}>${options(items, value)}</select>`;
  else if (type === "textarea")
    node = `<textarea ${a} maxlength="4500">${v}</textarea>`;
  else if (type === "checkbox")
    node = `<input type="checkbox" name="${esc(n)}" ${value ? "checked" : ""}>`;
  else
    node = `<input ${a} type="${type}" value="${v}" ${type === "password" ? 'autocomplete="current-password"' : ""}>`;
  return `<label class="field"><span>${esc(label)}</span>${node}</label>`;
}
function personField(label, n, sel = S.user.id, optional = false) {
  return field(label, n, "select", sel, !optional, [
    ...(optional ? [["", "No collaborator"]] : [["", "Choose an employee"]]),
    ...personOptions(),
  ]);
}
function showModal(title, content) {
  $("#modal-body").innerHTML =
    `<div class="modalhead"><h2>${esc(title)}</h2>${ib("Close", "close", "close")}</div><div class="pad">${content}</div>`;
  if (!modal.open) modal.showModal();
}
function form(title, op, body, submit, context = {}) {
  modalContext = { op, context, token: crypto.randomUUID() };
  showModal(
    title,
    `<form id="actionform" class="formgrid">${body}<div class="error" role="alert"></div><div class="form-actions">${btn("Cancel", "close", "quiet")}<button class="btn" type="submit">${esc(submit)}</button></div></form>`,
  );
}
function openForm(type, p = {}) {
  const subject = hr()
    ? personField("Employee", "subject", p.subjectId || S.user.id)
    : "";
  if (type === "password")
    form(
      "Change password",
      "change-password",
      field("Current password", "current", "password") +
        field("New password (12+ characters)", "new", "password"),
      "Change password",
    );
  if (type === "block")
    form(
      "Reserve a work block",
      "work-block",
      field("Work to schedule", "title") +
        field(
          "Start time · UTC",
          "starts",
          "datetime-local",
          (selectedDay > S.today ? selectedDay : nextDate(1)) + "T10:00",
        ) +
        field("Duration (minutes)", "minutes", "number", 30),
      "Add to my calendar",
    );
  if (type === "note")
    form(
      "Add a workflow record",
      "flow-note",
      field("Private HR note", "note", "textarea") +
        '<label class="field">Supporting document (optional, up to 2 MB)<input name="attachment" type="file" accept=".pdf,.txt,.png,.jpg,.jpeg,.csv,.docx"></label>',
      "Save to workflow",
      { flow: p.id },
    );
  if (type === "edit-email")
    form(
      "Edit pending email",
      "revise-email",
      field("Recipient", "to", "email", p.to) +
        field("Subject", "title", "text", p.subject) +
        field("Body", "message", "textarea", p.message),
      "Save draft",
      { id: p.id, revision: p.revision },
    );
  if (type === "leave")
    form(
      "Request annual leave",
      "request",
      subject +
        `<div class="duo">${field("First day", "start", "date", p.start || nextDate(1))}${field("Last day", "end", "date", p.end || nextDate(1))}</div>` +
        field("Reason", "reason", "textarea", "Annual leave"),
      "Submit for approval",
      { kind: "Leave" },
    );
  if (type === "case")
    form(
      "Confidential HR case",
      "request",
      field("Subject", "title", "text", p.title || "") +
        field(
          "Case type",
          "topic",
          "select",
          "Employee relations",
          true,
          [
            "Employee relations",
            "Access and security",
            "Payroll question",
            "Attendance correction",
            "Hiring decision",
            "Manager review",
            "Policy question",
            "Other",
          ].map((s) => [s, s]),
        ) +
        field("Private notes for HR", "details", "textarea", p.details || "") +
        `<p class="notice">Visible to the submitter and the HR reviewer.</p>`,
      "Send to HR",
      { kind: "Human review" },
    );
  if (type === "meeting") {
    const people = p.people || [S.user.id];
    const start =
      p.starts ??
      (selectedDay > S.today ? selectedDay : nextDate(1)) + "T10:00";
    form(
      "Schedule a meeting",
      "request",
      field("Meeting title", "title", "text", p.title || "") +
        `<div class="duo">${field("Start time · UTC", "starts", "datetime-local", start)}${field("Duration (minutes)", "minutes", "number", 30)}</div><fieldset class="field"><legend>Attendees</legend><div class="checkgroup">${S.people.map((x) => `<label><input type="checkbox" name="people" value="${esc(x.id)}" ${people.includes(x.id) ? "checked" : ""}> ${esc(x.name)}</label>`).join("")}</div></fieldset>` +
        field(
          "Request a Zoom meeting link",
          "zoom",
          "checkbox",
          p.zoom || false,
          false,
        ),
      "Submit meeting",
      { kind: "Meeting" },
    );
  }
  if (type === "email") {
    const addr =
      p.to ||
      (p.subjectId ? S.people.find((x) => x.id === p.subjectId)?.email : "") ||
      "";
    form(
      "Draft a formal email",
      "request",
      field("Recipient email", "to", "email", addr) +
        field(
          "What should the email communicate?",
          "brief",
          "textarea",
          p.brief || "",
          false,
        ) +
        btn("Draft with local Qwen", "draft-mail", "btnline", "spark") +
        field("Subject for approval", "title", "text", p.title || "") +
        field(
          "Email body for approval",
          "message",
          "textarea",
          p.message || "",
        ),
      "Submit draft for approval",
      { kind: "Email" },
    );
  }
  if (type === "task" || type === "promote") {
    form(
      type === "promote" ? "Review handoff assignment" : "Assign a task",
      type === "promote" ? "promote" : "request",
      (p.source
        ? `<div class="source"><b>Original note</b>${esc(p.source)}</div>`
        : "") +
        field("Task", "title", "text", p.title || "") +
        personField(
          "Responsible employee",
          "owner",
          p.owner || (type === "promote" ? "" : S.user.id),
        ) +
        personField("Collaborator", "helper", "", true) +
        field(
          "Due date",
          "due",
          "date",
          p.due || (type === "promote" ? "" : nextDate(1)),
        ),
      "Submit for approval",
      type === "promote"
        ? { handoff: p.handoff, item: p.item }
        : { kind: "Task" },
    );
  }
  if (type === "flow")
    form(
      "Start an HR workflow",
      "flow",
      field(
        "Workflow type",
        "kind",
        "select",
        p.kind || "Onboarding",
        true,
        Object.keys(S.playbooks).map((k) => [k, k]),
      ) +
        field("Checklist name", "title") +
        personField("Employee / coordinator", "subject") +
        field("Start date", "begin", "date", S.today) +
        `<div class="source" id="playbook-preview"></div>`,
      "Create checklist",
    );
  if (type === "handoff")
    form(
      "Build a meeting handoff",
      "handoff",
      `<p class="summary-note">Local Qwen reads each sentence. Each item keeps its original wording for review.</p>` +
        field(
          "Meeting notes",
          "notes",
          "textarea",
          "We agreed to use a buddy for new starters.\nKaran will send the setup checklist on Friday.\nWho approves access to the payroll folder?",
        ),
      "Build handoff",
    );
  if (type === "policy")
    form(
      p.id ? "Edit handbook policy" : "Add handbook policy",
      "policy",
      field("Section title", "title", "text", p.title || "") +
        field("Search terms", "keywords", "text", p.keywords || "") +
        field("Version", "version", "text", p.version || "1.0") +
        field("Published policy text", "body", "textarea", p.body || ""),
      "Publish policy",
      p.id ? { id: p.id } : {},
    );
  if (type === "person")
    form(
      "Add employee",
      "add-person",
      field("Full name", "name") +
        field("Work email", "email", "email") +
        `<div class="duo">${field("Team", "team")}${field("Role title", "title")}</div>` +
        field("Location", "location") +
        personField("Coordinator / manager", "manager") +
        `<div class="duo">${field("Start date", "start", "date", S.today)}${field("Opening leave days", "balance", "number", 0)}</div>` +
        field(
          "Initial account password (12+ characters)",
          "password",
          "password",
        ),
      "Create employee",
    );
  if (type === "flow") playbookPreview();
}
function playbookPreview() {
  const node = $("#playbook-preview");
  if (!node) return;
  const kind = $("#actionform [name=kind]").value;
  node.innerHTML = `<b>Checklist</b>${(S.playbooks[kind] || []).map(esc).join("<br>")}`;
}
function newRequest() {
  modalContext = null;
  showModal(
    "New request",
    `<div class="list">${[["leave", "Annual leave", "leaf"], ["meeting", "Meeting", "cal"], ["email", "Formal email draft", "mail"], ["case", "Confidential HR case", "shield"], ...(hr() ? [["task", "Team assignment", "work"]] : [])].map(([t, l, i]) => btn(l, "new-" + t, "btnline", i)).join("")}</div>`,
  );
}
function pair(k, v) {
  return `<dt>${esc(k)}</dt><dd>${esc(v ?? "")}</dd>`;
}
function requestDetail(id) {
  const r = S.requests.find((v) => v.id === id);
  if (!r) return;
  const b = r.body;
  let facts = [
    ["Reference", r.id],
    ["Submitted by", name(r.creator)],
    ["Employee", name(r.subject)],
  ];
  if (r.kind === "Leave")
    facts.push(
      ["Dates", pretty(b.start) + " – " + pretty(b.end)],
      ["Working days", b.days],
      ["Reason", b.reason],
    );
  if (r.kind === "Meeting")
    facts.push(
      ["Start (UTC)", b.starts.replace("T", " ")],
      ["Duration", b.minutes + " minutes"],
      ["Attendees", b.people.map(name).join(", ")],
      ["Video link", b.zoom ? "Zoom requested" : "In person / other"],
    );
  if (r.kind === "Email")
    facts.push(
      ["Recipient", b.to],
      ["Subject", b.subject],
      ["Body", b.message],
    );
  if (r.kind === "Human review")
    facts.push(["Type", b.topic], ["Private notes", b.details]);
  if (r.kind === "Task")
    facts.push(
      ["Owner", name(b.owner)],
      ["Collaborator", b.helper ? name(b.helper) : "None"],
      ["Due", pretty(b.due)],
      ["Source", b.source],
    );
  if (r.reviewer)
    facts.push(
      ["Reviewed by", name(r.reviewer)],
      ["Reviewer note", r.note || "—"],
    );
  let actions = "";
  if (hr() && r.status === "Pending")
    actions =
      field(
        "Reviewer note" +
          (r.kind === "Human review" ? " (required to close)" : " (optional)"),
        "note",
        "textarea",
        "",
        false,
      ) +
      `<div class="form-actions">${btn("Decline", "decline", "btnline danger", "", da("id", id))}${btn(r.kind === "Human review" ? "Record human review" : "Approve", "approve", "btn", "check", da("id", id))}</div>`;
  if (hr() && r.status === "Pending" && r.kind === "Email")
    actions += btn(
      "Edit draft",
      "revise-email",
      "btnline",
      "mail",
      da("id", id),
    );
  if (hr() && r.status === "Approved") {
    if (r.kind === "Email")
      actions += `<a class="btnline" href="/export/email/${encodeURIComponent(id)}">Download email draft (.eml)</a>`;
    if (r.kind === "Meeting")
      actions += `<a class="btnline" href="/export/meeting/${encodeURIComponent(id)}">Download meeting (.ics)</a>`;
    if (S.mode === "company") {
      const set =
        r.kind === "Email"
          ? ["Gmail draft", "Gmail send"]
          : r.kind === "Meeting"
            ? [...(b.zoom ? ["Zoom"] : []), "Google Calendar"]
            : [];
      actions += set
        .map((c) => {
          const existing = r.actions.find((a) => a.channel === c);
          return existing && existing.status !== "Failed"
            ? `<p class="source"><b>${esc(c)} · ${esc(existing.status)}</b>${esc(existing.details)}</p>`
            : btn(
                c === "Gmail send"
                  ? "Send approved email"
                  : c === "Gmail draft"
                    ? "Create Gmail draft"
                    : c === "Zoom"
                      ? "Create Zoom meeting"
                      : "Publish and invite attendees",
                "deliver",
                "btnline",
                "",
                da("id", id) + " " + da("channel", c),
              );
        })
        .join(" ");
    }
  }
  modalContext = { op: "detail", context: { id }, token: crypto.randomUUID() };
  showModal(
    r.title,
    `<div class="inline">${pill(r.status)}<span class="muted">${esc(r.kind)}</span></div><dl class="details">${facts.map((x) => pair(...x)).join("")}</dl><div class="formgrid">${actions}<div class="error" role="alert"></div></div>`,
  );
}
function taskDetail(id) {
  const t = S.tasks.find((t) => t.id === id);
  if (!t) return;
  showModal(
    t.title,
    `${pill(t.status)}<dl class="details">${pair("Owner", name(t.owner))}${pair("Collaborator", t.helper ? name(t.helper) : "None")}${pair("Due", pretty(t.due))}${pair("Source", t.source)}</dl><div class="error"></div><div class="form-actions">${btn(t.status === "Open" ? "Mark complete" : "Reopen task", "task-status", "btn", "check", da("id", id))}</div>`,
  );
}
function flowDetail(id) {
  const f = S.flows.find((x) => x.id === id);
  const notes = (f.notes || [])
    .map(
      (n) =>
        '<div class="source"><b>' +
        esc(name(n.actor)) +
        " · " +
        esc(n.at) +
        "</b>" +
        esc(n.note) +
        (n.filename
          ? '<br><a href="/export/document/' +
            encodeURIComponent(n.id) +
            '">Download ' +
            esc(n.filename) +
            "</a>"
          : "") +
        "</div>",
    )
    .join("");
  showModal(
    f.title,
    `<p class="summary-note">${esc(f.kind)} · ${esc(name(f.subject))}</p>${S.tasks
      .filter((t) => t.flow === id)
      .map(taskRow)
      .join(
        "",
      )}<div class="form-actions">${btn("Add note or document", "add-flow-note", "btnline", "plus", da("id", id))}</div>${notes}`,
  );
}
function handoffDetail(id) {
  const h = S.handoffs.find((x) => x.id === id);
  showModal(
    "Review handoff",
    `<small>${esc(id)} · Local Qwen</small>${h.items.map((i) => `<div class="list-item"><span class="tag">${esc(i.kind)}</span><p><b>${esc(i.draft)}</b></p><div class="source"><b>Source S${i.id}</b>${esc(i.source)}</div>${i.kind === "Action" ? `<small>Owner: ${esc(i.owner || "Unassigned")} · Due: ${esc(i.when || "Unspecified")}</small><br>` : ""}${h.promoted[i.id] ? btn("Open submitted request", "request-detail", "quiet", "", da("id", h.promoted[i.id])) : btn(i.kind === "Action" ? "Review assignment" : "Refer to HR", "promote-item", "btnline", "", da("id", id) + " " + da("item", i.id))}</div>`).join("")}`,
  );
}
function personDetail(id) {
  const p = S.people.find((x) => x.id === id);
  showModal(
    p.name,
    `<div class="inline">${avatar(p.name)}<b>${esc(p.title)}</b></div><dl class="details">${pair("Employee ID", p.id)}${pair("Team", p.team)}${pair("Work email", p.email)}${hr() ? pair("Manager", p.manager ? name(p.manager) : "—") + pair("Location", p.location) + pair("Start date", p.start) + pair("Leave balance", p.balance == null ? "No ledger" : p.balance + " working days") : ""}</dl>`,
  );
}
function eventDetail(id) {
  const e = S.events.find((x) => x.id === id);
  showModal(
    e.title,
    `<dl class="details">${pair("Start (UTC)", e.starts.replace("T", " "))}${pair("End (UTC)", e.ends.replace("T", " "))}${pair("Participants", e.people.map(name).join(", "))}${pair("Calendar", e.source)}</dl><div class="form-actions">${e.link && e.link.startsWith("https://") ? `<a class="btn" href="${esc(e.link)}" target="_blank" rel="noreferrer">Open meeting link</a>` : ""}<a class="btnline" href="/export/meeting/${encodeURIComponent(id)}">Download .ics</a></div>`,
  );
}
function renderChat() {
  const panel = $("#assistant");
  panel.hidden = !chatOpen;
  if (!chatOpen) return;
  const examples = [
    hr()
      ? "How many leave days does Karan have remaining?"
      : "How many leave days do I have remaining?",
    "What is the reimbursement policy?",
    "Schedule a Zoom meeting with Karan tomorrow at 3 pm",
  ];
  panel.innerHTML = `<div class="chathead">${icon("spark")}<div class="grow"><b>PeopleDesk assistant</b></div>${ib("Close assistant", "chat-toggle", "close")}</div><div class="chatlog"><div class="bubble">Ask about a company record, check a policy or prepare a request.</div><div class="chat-options">${examples.map((q, i) => btn(q, "chat-example", "chip", "", da("q", q))).join("")}</div>${messages.map((m, i) => `<div class="bubble ${m.mine ? "mine" : ""}">${esc(m.text)}${(m.sources || []).map((s) => `<div class="source"><b>${esc(s.id)}</b>${esc(s.text)}</div>`).join("")}${m.action ? `<br>${btn({ meeting: "Review meeting", email: "Open email draft", leave: "Request leave", case: "Open HR case" }[m.action.type] || "Review", "chat-action", "btnline", "", da("index", i))}` : ""}</div>`).join("")}${busyChat ? '<div class="bubble">Checking company records…</div>' : ""}</div><form id="chat-form" class="chatinput"><input name="q" maxlength="1000" placeholder="Ask a question…" aria-label="Ask the assistant" required ${busyChat ? "disabled" : ""}><button class="btn" aria-label="Send question" ${busyChat ? "disabled" : ""}>${icon("send")}</button></form>`;
  const log = panel.querySelector(".chatlog");
  log.scrollTop = log.scrollHeight;
}
let conversation = 0;
async function ask(q) {
  if (busyChat || !q) return;
  const gen = conversation;
  busyChat = true;
  messages.push({ mine: true, text: q });
  renderChat();
  try {
    const out = await api("chat", { q });
    if (gen === conversation)
      messages.push({
        text: out.answer,
        sources: out.sources,
        action: out.action,
      });
  } catch (e) {
    if (gen === conversation) messages.push({ text: e.message });
  } finally {
    if (gen === conversation) {
      busyChat = false;
      renderChat();
      $("#chat-form input")?.focus();
    }
  }
}
function resetSession() {
  conversation++;
  messages = [];
  busyChat = false;
  chatOpen = false;
  $("#assistant").hidden = true;
  selectedDay = "";
  calMonth = "";
  filter = "Pending";
  workTab = "Tasks";
  if (modal.open) modal.close();
}

async function activate(b) {
  if (await extraAction(b)) return;
  const a = b.dataset.act,
    id = b.dataset.id;
  if (a === "close") {
    modal.close();
    return;
  }
  if (a === "boot") return boot();
  if (a === "menu") {
    menuOpen = !menuOpen;
    draw();
    return;
  }
  if (a === "nav") return route(b.dataset.to);
  if (a === "filter") {
    filter = b.dataset.filter;
    draw();
    return;
  }
  if (a === "worktab") {
    workTab = b.dataset.tab;
    draw();
    return;
  }
  if (a === "month-prev" || a === "month-next") {
    let d = jdate(calMonth + "-01");
    d.setUTCMonth(d.getUTCMonth() + (a === "month-next" ? 1 : -1));
    calMonth = dateCode(d).slice(0, 7);
    draw();
    return;
  }
  if (a === "day") {
    selectedDay = b.dataset.date;
    calMonth = selectedDay.slice(0, 7);
    draw();
    return;
  }
  if (a === "add-flow-note") return openForm("note", { id });
  if (a === "revise-email") {
    const r = S.requests.find((r) => r.id === id);
    return openForm("edit-email", { id, revision: r.revision, ...r.body });
  }
  if (a === "snooze") {
    await api("snooze", { id }, crypto.randomUUID());
    await refresh();
    toast("Reminder snoozed until tomorrow.");
    return;
  }
  if (a === "new-request") return newRequest();
  if (a.startsWith("new-")) return openForm(a.slice(4));
  if (a === "edit-policy")
    return openForm(
      "policy",
      S.policies.find((p) => p.id === id),
    );
  if (a === "request-detail") return requestDetail(id);
  if (a === "task-detail") return taskDetail(id);
  if (a === "flow-detail") return flowDetail(id);
  if (a === "handoff-detail") return handoffDetail(id);
  if (a === "person-detail") return personDetail(id);
  if (a === "event-detail") return eventDetail(id);
  if (a === "chat-toggle") {
    chatOpen = !chatOpen;
    renderChat();
    if (chatOpen) $("#chat-form input")?.focus();
    return;
  }
  if (a === "chat-example") return ask(b.dataset.q);
  if (a === "chat-action") {
    const p = messages[+b.dataset.index].action;
    return openForm(p.type, p);
  }
  if (a === "stop-local") {
    if (
      !confirm(
        "Stop PeopleDesk on this computer? Reopen the app to start it again.",
      )
    )
      return;
    await api("stop-local", {});
    resetSession();
    S = null;
    $("#workspace").innerHTML =
      '<main class="loading"><h1>PeopleDesk is closed.</h1><p class="sub">Open PeopleDesk.exe to start your workspace again.</p></main>';
    return;
  }
  if (a === "logout") {
    await api("logout", {});
    sessionStorage.setItem("pd_signedout", "yes");
    resetSession();
    showLogin();
    return;
  }
  if (a.startsWith("login-")) {
    resetSession();
    await api("login", { demo: a.slice(6) });
    sessionStorage.removeItem("pd_signedout");
    view = "overview";
    await refresh();
    return;
  }
  if (a === "approve" || a === "decline") {
    await api(
      "review",
      {
        id,
        revision: S.requests.find((r) => r.id === id).revision,
        decision: a === "approve" ? "Approved" : "Declined",
        note: $("#modal [name=note]").value,
      },
      modalContext.token,
    );
    modal.close();
    await refresh();
    toast("Review recorded.");
    return;
  }
  if (a === "task-status") {
    const t = S.tasks.find((x) => x.id === id);
    await api(
      "task-status",
      { id, status: t.status === "Open" ? "Done" : "Open" },
      crypto.randomUUID(),
    );
    modal.close();
    await refresh();
    toast("Task updated.");
    return;
  }
  if (a === "promote-item") {
    const h = S.handoffs.find((v) => v.id === id),
      i = h.items.find((v) => v.id === +b.dataset.item);
    if (i.kind !== "Action") {
      await api("promote", { handoff: id, item: i.id }, crypto.randomUUID());
      await refresh();
      handoffDetail(id);
      return;
    }
    const matched = S.people.filter(
      (p) =>
        p.name === i.owner ||
        p.name.split(" ")[0].toLowerCase() === i.owner.toLowerCase(),
    );
    return openForm("promote", {
      handoff: id,
      item: i.id,
      title: i.draft,
      source: i.source,
      owner: matched.length === 1 ? matched[0].id : "",
      due: i.when.match(/\b\d{4}-\d{2}-\d{2}\b/)?.[0] || "",
    });
  }
  if (a === "draft-mail") {
    const f = $("#actionform");
    if (!f.to.reportValidity()) return;
    if (!f.brief.value.trim())
      throw Error("Add the facts you want in the email first.");
    const out = await api("draft", { brief: f.brief.value, to: f.to.value });
    f.elements.title.value = out.subject;
    f.message.value = out.message;
    return;
  }
  if (a === "deliver") {
    const channel = b.dataset.channel;
    if (
      !confirm(
        (channel === "Gmail send"
          ? "Send the approved email to its recipient"
          : channel === "Google Calendar"
            ? "Publish the meeting and invite its attendees"
            : channel === "Zoom"
              ? "Create the meeting on the configured Zoom account"
              : "Create a draft in the connected Gmail account") + "?",
      )
    )
      return;
    try {
      const out = await api("external", { id, channel });
      toast(out.message);
    } finally {
      await refresh();
      requestDetail(id);
    }
    return;
  }
  if (
    [
      "connect-google",
      "disconnect-google",
      "refresh-calendar",
      "test-zoom",
    ].includes(a)
  ) {
    if (
      a === "disconnect-google" &&
      !confirm("Disconnect Google from this installation?")
    )
      return;
    const out = await api(a, {});
    if (out.url) location.assign(out.url);
    else {
      await refresh();
      toast(out.message);
    }
    return;
  }
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b || b.disabled) return;
  const old = b.textContent;
  const slow = [
    "draft-mail",
    "refresh-calendar",
    "deliver",
    "test-zoom",
  ].includes(b.dataset.act);
  if (slow) b.textContent = "Working…";
  b.disabled = true;
  try {
    await activate(b);
  } catch (err) {
    const el = modal.open && $("#modal .error");
    if (el) el.textContent = err.message;
    else toast(err.message);
  } finally {
    if (b.isConnected) {
      b.disabled = false;
      if (slow) b.textContent = old;
    }
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "people-search") {
    findText = e.target.value;
    $("#directory-list").innerHTML = directoryRows();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.name === "kind") playbookPreview();
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (["joinform", "setupform", "keyform", "composeform"].includes(f.id))
    return extraSubmit(f);
  const data = new FormData(f),
    d = Object.fromEntries(data);
  if (f.id === "chat-form") return ask(d.q.trim());
  const submit = f.querySelector("[type=submit],button:not([type])");
  const original = submit?.textContent;
  if (submit) {
    submit.disabled = true;
    submit.textContent =
      modalContext?.op === "handoff" ? "Reading notes with Qwen…" : "Saving…";
  }
  try {
    if (f.id === "loginform") {
      await api("login", d);
      resetSession();
      sessionStorage.removeItem("pd_signedout");
      view = "overview";
      await refresh();
      return;
    }
    if (f.id !== "actionform") return;
    const m = modalContext;
    if (m.op === "room-create") d.members = data.getAll("members");
    if (m.context.kind === "Meeting") {
      d.people = data.getAll("people");
      d.zoom = data.has("zoom");
    }
    if (m.op === "flow-note" || m.op === "share-file") {
      const file = data.get("attachment");
      delete d.attachment;
      if (file?.size) {
        if (file.size > (m.op === "share-file" ? 5242880 : 2097152))
          throw Error("The file is too large.");
        d.filename = file.name;
        d.attachment = (
          await new Promise((ok, fail) => {
            const reader = new FileReader();
            reader.onload = () => ok(reader.result);
            reader.onerror = fail;
            reader.readAsDataURL(file);
          })
        ).split(",")[1];
      }
    }
    const result = await api(m.op, { ...d, ...m.context }, m.token);
    if (modal.open) modal.close();
    if (m.op === "change-password") {
      resetSession();
      showLogin();
      toast("Password updated. Sign in again.");
      return;
    }
    await refresh();
    if (await afterExtra(m, result, d)) return;
    if (m.op === "revise-email") requestDetail(result.id);
    else if (m.op === "flow-note") flowDetail(result.flow);
    else if (m.op === "work-block") {
      selectedDay = d.starts.slice(0, 10);
      calMonth = selectedDay.slice(0, 7);
      route("calendar");
      eventDetail(result.id);
    } else if (m.op === "handoff") {
      workTab = "Handoffs";
      route("work");
      handoffDetail(result.id);
    } else if (m.op === "flow") {
      workTab = "Workflows";
      route("work");
      flowDetail(result.id);
    } else if (["request", "promote"].includes(m.op)) {
      filter = "Pending";
      route("approvals");
      requestDetail(result.id);
    } else toast("Saved to the company workspace.");
  } catch (err) {
    const target = f.querySelector(".error");
    if (target) target.textContent = err.message;
    else toast(err.message);
  } finally {
    if (submit?.isConnected) {
      submit.disabled = false;
      submit.textContent = original;
    }
  }
});
window.addEventListener("hashchange", () => {
  if (S) route(location.hash.slice(1));
});
