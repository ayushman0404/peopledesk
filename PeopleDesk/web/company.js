/* Personal workspace, organisation membership and provider connection interfaces. */
sections.splice(1, 0, ["team", "Team workspace", "people"]);
sections.splice(
  5,
  0,
  ["messages", "Messages", "mail"],
  ["files", "Files", "book"],
);
sections.push(["members", "People & access", "shield"]);
sections.find((x) => x[0] === "integrations")[1] = "Connections";
const originalOverview = overview,
  originalTaskDetail = taskDetail,
  originalReset = resetSession;
const isLeader = () =>
  ["owner", "hr", "manager", "lead"].includes(S?.user.access);
const isOwner = () => S?.user.access === "owner";
let planDay = "today",
  fileView = "local",
  deferredInstall = null;

resetSession = function () {
  Messenger.lock();
  originalReset();
};
function roleName(p = S.user) {
  return S.roles?.[p.access] || p.access || "Team member";
}
function decorateWorkspace() {
  document.body.classList.toggle("chat-view", view === "messages");
  const label = $(".usercard small");
  if (label) label.textContent = roleName();
  const tag = $(".tag.badgewide");
  if (tag) tag.innerHTML = '<i class="dot"></i>' + esc(S.user.team);
  const sidebar = $(".side-foot");
  if (S.mode === "demo" && sidebar && !$("#demo-role")) {
    sidebar.insertAdjacentHTML(
      "beforeend",
      '<label class="field demo-role">Demo role<select id="demo-role"><option value="">Choose a perspective</option><option value="hr">Founder / administrator</option><option value="people">HR coordinator</option><option value="manager">Engineering manager</option><option value="lead">Operations lead</option><option value="employee">Karan · engineer</option></select></label>',
    );
  }
  const bar = $(".topbar > .inline");
  if (bar)
    bar.insertAdjacentHTML(
      "afterbegin",
      btn(
        "Updates" +
          (S.notifications.some((n) => !n.seen)
            ? " · " + S.notifications.filter((n) => !n.seen).length
            : ""),
        "notifications",
        "quiet",
        "inbox",
      ) +
        btn("Install portal", "install-portal", "quiet", "grid") +
        (view === "messages"
          ? ib("Ask PeopleDesk", "chat-toggle", "spark")
          : ""),
    );
  if (view === "messages" && Messenger.keys && Messenger.room)
    Messenger.load(false);
  else clearTimeout(Messenger.timer);
}
overview = function () {
  if (hr() && location.pathname !== "/employee")
    return originalOverview() + "<br>" + announcementPanel();
  const my = S.tasks.filter(
    (t) => t.owner === S.user.id || t.helper === S.user.id,
  );
  const due = planDay === "tomorrow" ? nextDate(1) : S.today;
  const work = my.filter((t) => t.due === due && t.status !== "Done");
  const upcoming = S.events.filter(
    (e) => e.people.includes(S.user.id) && eventOn(e, due),
  );
  return (
    heading(
      "My day",
      "Welcome, " +
        S.user.name.split(" ")[0] +
        ". Here is your work and the people behind it.",
      btn("Plan work", "personal-assign", "btn", "plus"),
    ) +
    '<div class="day-banner"><div><span class="kicker">' +
    esc(S.user.team) +
    " · " +
    esc(S.user.title) +
    "</span><h2>" +
    esc(pretty(due, true)) +
    "</h2><p>" +
    work.length +
    " tasks scheduled · " +
    upcoming.length +
    ' meetings</p></div><div class="inline">' +
    btn("Today", "plan-today", "chip " + (planDay === "today" ? "on" : "")) +
    btn(
      "Tomorrow",
      "plan-tomorrow",
      "chip " + (planDay === "tomorrow" ? "on" : ""),
    ) +
    "</div></div>" +
    '<div class="dashboard"><div class="stack">' +
    card(
      "My work plan",
      work.map(personalTaskRow).join("") ||
        empty("No tasks scheduled for this day."),
      btn("All my work", "nav", "quiet", "", da("to", "work")),
    ) +
    announcementPanel() +
    '</div><div class="stack">' +
    card(
      "Scheduled meetings",
      upcoming
        .map(
          (e) =>
            '<button class="row" data-act="event-detail" ' +
            da("id", e.id) +
            ">" +
            glyph("video", "lilac") +
            '<span class="grow"><strong>' +
            esc(e.title) +
            "</strong><small>" +
            esc(e.starts.slice(11)) +
            " UTC · " +
            esc(e.source) +
            "</small></span></button>",
        )
        .join("") || empty("Your schedule is clear."),
      ib("Schedule meeting", "new-meeting", "plus"),
    ) +
    card(
      "Your team",
      S.people
        .filter((p) => p.team === S.user.team && p.id !== S.user.id)
        .slice(0, 5)
        .map(
          (p) =>
            '<div class="row">' +
            avatar(p.name) +
            '<div class="grow"><strong>' +
            esc(p.name) +
            "</strong><small>" +
            esc(p.title) +
            "</small></div>" +
            btn("Chat", "contact-chat", "quiet", "mail", da("id", p.id)) +
            "</div>",
        )
        .join("") || empty("Your team will appear here."),
    ) +
    "</div></div>"
  );
};
function announcementPanel() {
  return card(
    "Company updates",
    S.announcements
      .map(
        (n) =>
          '<article class="list-item pad"><h3>' +
          esc(n.title) +
          "</h3><p>" +
          esc(n.body) +
          "</p><small>" +
          esc(name(n.author)) +
          " · " +
          esc(pretty(n.created.slice(0, 10))) +
          "</small></article>",
      )
      .join("") || empty("Company announcements appear here."),
    isLeader() ? btn("Post update", "new-announcement", "quiet", "plus") : "",
  );
}
function personalTaskRow(t) {
  return (
    '<button class="row task-card" data-act="task-detail" ' +
    da("id", t.id) +
    '><span class="check ' +
    (t.status === "Done" ? "done" : "") +
    '">' +
    (t.status === "Done" ? icon("check") : "") +
    '</span><span class="grow"><strong>' +
    esc(t.title) +
    "</strong><small>" +
    (t.assigner
      ? "Assigned by " + esc(name(t.assigner))
      : "Source · " + esc(t.source)) +
    (t.helper ? " · with " + esc(name(t.helper)) : "") +
    "</small></span>" +
    pill(!t.accepted ? "Invitation" : t.status) +
    "</button>"
  );
}
taskRow = personalTaskRow;
function teamPage() {
  const folks = isLeader()
    ? S.people.filter((p) => hr() || p.team === S.user.team)
    : S.people.filter((p) => p.team === S.user.team);
  return (
    heading(
      isLeader() ? "Team workspace" : "My team",
      "See who owns each piece of work and coordinate the next step.",
      btn("Create assignment", "personal-assign", "btn", "plus"),
    ) +
    '<div class="tiles">' +
    folks
      .map((p) => {
        const tasks = S.tasks.filter(
          (t) => t.owner === p.id && t.status !== "Done",
        );
        return (
          '<article class="card tile"><div class="inline">' +
          avatar(p.name) +
          "<div><h2>" +
          esc(p.name) +
          "</h2><small>" +
          esc(p.title) +
          '</small></div></div><span class="tag">' +
          esc(S.roles[p.access] || "Team member") +
          "</span><p>" +
          esc(p.team) +
          "</p>" +
          (isLeader()
            ? "<strong>" + tasks.length + " visible open tasks</strong>"
            : "") +
          tasks
            .slice(0, 3)
            .map(
              (t) =>
                '<button class="team-task" data-act="task-detail" ' +
                da("id", t.id) +
                ">" +
                esc(t.title) +
                "<small>" +
                esc(pretty(t.due)) +
                " · " +
                esc(t.status) +
                "</small></button>",
            )
            .join("") +
          '<div class="inline">' +
          btn("Message", "contact-chat", "btnline", "mail", da("id", p.id)) +
          btn("Assign work", "assign-person", "quiet", "plus", da("id", p.id)) +
          "</div></article>"
        );
      })
      .join("") +
    "</div>"
  );
}
taskDetail = function (id) {
  const t = S.tasks.find((t) => t.id === id);
  if (!t) return;
  showModal(
    t.title,
    '<div class="inline">' +
      pill(t.status) +
      '<span class="tag">' +
      esc(t.priority || "Normal") +
      '</span></div><dl class="details">' +
      pair("Assigned by", t.assigner ? name(t.assigner) : t.source) +
      pair("Responsible", name(t.owner)) +
      pair("Collaborator", t.helper ? name(t.helper) : "—") +
      pair("Due", pretty(t.due)) +
      pair("Project", t.project || "—") +
      pair("Details", t.description || "—") +
      "</dl>" +
      (!t.accepted
        ? '<div class="notice">Collaboration invitation · the responsible employee can accept it.</div>' +
          btn("Accept task", "accept-task", "btn", "check", da("id", id))
        : '<div class="inline">' +
          ["Open", "In progress", "Blocked", "Done"]
            .map((s) =>
              btn(
                s,
                "progress",
                "chip " + (s === t.status ? "on" : ""),
                "",
                da("id", id) + " " + da("status", s),
              ),
            )
            .join("")) +
      '<h3 class="space-top">Progress notes</h3>' +
      t.comments
        .map(
          (c) =>
            '<div class="source"><b>' +
            esc(name(c.author)) +
            "</b>" +
            esc(c.body) +
            "</div>",
        )
        .join("") +
      '<div class="form-actions">' +
      btn("Add update", "comment-task", "btnline", "plus", da("id", id)) +
      btn(
        "Sync to my Google Tasks",
        "sync-task",
        "quiet",
        "plug",
        da("id", id),
      ) +
      '</div><div class="error"></div>',
  );
};
function filesPage() {
  const google = S.cloud.filter((x) => x.kind === "files");
  return (
    heading(
      "Files",
      "Company resources, team documents and your connected Drive.",
      btn("Share a file", "share-file", "btn", "plus"),
    ) +
    '<div class="tabbar">' +
    btn("Workspace files", "files-local", fileView === "local" ? "on" : "") +
    btn("My Google Drive", "files-google", fileView === "google" ? "on" : "") +
    '</div><section class="card">' +
    (fileView === "google"
      ? google
          .map((v) => {
            const f = v.body;
            return (
              '<div class="row">' +
              glyph("book", "blue") +
              '<div class="grow"><strong>' +
              esc(f.name) +
              "</strong><small>Private Google Drive connection</small></div>" +
              (safeURL(f.webViewLink)
                ? '<a class="btnline" target="_blank" rel="noreferrer" href="' +
                  esc(f.webViewLink) +
                  '">Open file</a>'
                : "") +
              "</div>"
            );
          })
          .join("") ||
        empty("Connect Google, then refresh to see your Drive files.")
      : S.files
          .map(
            (f) =>
              '<div class="row">' +
              glyph("book") +
              '<div class="grow"><strong>' +
              esc(f.name) +
              "</strong><small>" +
              esc(name(f.owner)) +
              " · " +
              esc(f.audience) +
              " · " +
              Math.ceil(f.size / 1024) +
              ' KB</small></div><a class="btnline" href="/export/shared/' +
              encodeURIComponent(f.id) +
              '">Download</a></div>',
          )
          .join("") || empty("Share a file with your team or the company.")) +
    "</section>"
  );
}
function safeURL(u) {
  try {
    return new URL(u).protocol === "https:";
  } catch {
    return false;
  }
}
function membersPage() {
  return (
    heading(
      "People & access",
      "Invite colleagues, review registrations and assign company roles.",
      btn("Invite colleague", "invite-member", "btn", "plus"),
    ) +
    card(
      "Registration requests",
      S.registrations
        .map(
          (r) =>
            '<div class="row">' +
            avatar(r.name) +
            '<div class="grow"><strong>' +
            esc(r.name) +
            "</strong><small>" +
            esc(r.email) +
            " · " +
            esc(r.team) +
            "</small></div>" +
            btn("Review", "review-member", "btnline", "", da("id", r.id)) +
            "</div>",
        )
        .join("") || empty("No registrations await review."),
    ) +
    "<br>" +
    card(
      "Company members",
      S.people
        .map(
          (p) =>
            '<div class="row">' +
            avatar(p.name) +
            '<div class="grow"><strong>' +
            esc(p.name) +
            "</strong><small>" +
            esc(p.team) +
            " · " +
            esc(S.roles[p.access]) +
            (p.active ? "" : " · Deactivated") +
            "</small></div>" +
            btn(
              (p.balance ?? 0) + " leave days",
              "adjust-leave",
              "quiet",
              "leaf",
              da("id", p.id),
            ) +
            (isOwner()
              ? btn("Manage", "edit-member", "btnline", "", da("id", p.id))
              : "") +
            "</div>",
        )
        .join(""),
    )
  );
}
integrations = function () {
  const g = S.integrations;
  const cards = [
    [
      "Google Calendar",
      "cal",
      "Read your upcoming meetings and copy a PeopleDesk meeting to your personal calendar.",
    ],
    [
      "Gmail",
      "mail",
      "See recent inbox subjects and send your work plan to your own email.",
    ],
    [
      "Google Drive",
      "book",
      "Browse your recent documents from your private Google connection.",
    ],
    [
      "Google Tasks",
      "list",
      "View your default task list and sync assigned work, due dates and completion status.",
    ],
    [
      "Zoom",
      "video",
      "HR can create an approved Zoom meeting and distribute its join link.",
    ],
  ];
  return (
    heading(
      "Your connections",
      "Your provider account is connected to your own company profile.",
      isOwner()
        ? btn("Company provider setup", "provider-settings", "btnline", "plug")
        : "",
    ) +
    (S.mode === "demo"
      ? '<p class="notice">Use company mode to connect live provider accounts. The demo uses local company records.</p><br>'
      : "") +
    '<div class="connection-banner"><div>' +
    glyph("plug") +
    " <strong>" +
    esc(g.email || "Connect your work account") +
    "</strong><p>" +
    esc(
      g.googleLinked
        ? "Google is connected. Refresh to pull your recent records."
        : g.googleConfigured
          ? "Google is configured. Sign in and choose the permissions to grant."
          : "Your administrator can configure Google and Zoom in Company provider setup.",
    ) +
    '</p></div><div class="inline">' +
    btn(
      g.googleLinked ? "Refresh Google" : "Connect Google",
      g.googleLinked ? "cloud-refresh" : "cloud-connect",
      "btn",
      "plug",
    ) +
    (g.googleLinked ? btn("Disconnect", "cloud-disconnect", "quiet") : "") +
    "</div></div>" +
    '<div class="tiles">' +
    cards
      .map(
        ([title, ic, desc]) =>
          '<article class="card tile">' +
          glyph(ic, "blue") +
          "<h2>" +
          title +
          "</h2><p>" +
          desc +
          "</p><small>" +
          (title === "Zoom"
            ? g.zoomConfigured
              ? "Company credentials configured"
              : "Company setup required"
            : g.googleLinked
              ? "Account connected"
              : "Awaiting connection") +
          "</small>" +
          (title === "Gmail"
            ? btn("Email my work plan", "email-digest", "btnline", "mail")
            : title === "Zoom" && hr()
              ? btn("Test Zoom connection", "cloud-test-zoom", "btnline")
              : "") +
          "</article>",
      )
      .join("") +
    "</div>" +
    "<br>" +
    card(
      "Recent inbox",
      S.cloud
        .filter((c) => c.kind === "mail")
        .map((c) => {
          const headers = c.body.payload?.headers || [],
            get = (n) =>
              headers.find((h) => h.name.toLowerCase() === n)?.value || "";
          return (
            '<div class="row">' +
            glyph("mail", "lilac") +
            '<div class="grow"><strong>' +
            esc(get("subject") || "(No subject)") +
            "</strong><small>" +
            esc(get("from")) +
            "</small></div></div>"
          );
        })
        .join("") || empty("Your inbox subjects appear here after refresh."),
    ) +
    "<br>" +
    card(
      "My Google Tasks",
      S.cloud
        .filter((c) => c.kind === "tasks")
        .map((c) => {
          const t = c.body;
          return (
            '<div class="row">' +
            glyph("list", "blue") +
            '<div class="grow"><strong>' +
            esc(t.title || "Untitled task") +
            "</strong><small>" +
            (t.due ? "Due " + esc(pretty(t.due.slice(0, 10))) : "No due date") +
            "</small></div>" +
            pill(t.status === "completed" ? "Done" : "Open") +
            "</div>"
          );
        })
        .join("") ||
        empty("Your default Google Tasks list appears here after refresh."),
    ) +
    "<br>" +
    card(
      "Sync activity",
      S.cloud_jobs
        .map(
          (j) =>
            '<div class="row"><div class="grow"><strong>' +
            esc(j.provider) +
            " · " +
            esc(j.object) +
            "</strong><small>" +
            esc(j.detail) +
            "</small></div>" +
            pill(j.state) +
            "</div>",
        )
        .join("") || empty("No provider writes recorded."),
    )
  );
};
showLogin = function () {
  S = null;
  const invitation =
    new URLSearchParams(location.hash.slice(1)).get("invite") || "";
  const setupToken =
    new URLSearchParams(location.hash.slice(1)).get("setup") ||
    sessionStorage.getItem("pd_setup") ||
    "";
  if (setupToken) sessionStorage.setItem("pd_setup", setupToken);
  let content;
  if (info.setup)
    content =
      '<h1>Create your company workspace</h1><p class="sub">Set up the first administrator on this company host.</p><form id="setupform" class="formgrid">' +
      field("Company name", "company") +
      field("Your name", "name") +
      field("Work email", "email", "email") +
      field("Password (12+ characters)", "password", "password") +
      '<input type="hidden" name="setup_token" value="' +
      esc(setupToken) +
      '"><button class="btn">Create workspace</button><div class="error"></div></form>';
  else if (location.pathname === "/join" || invitation)
    content =
      "<h1>Join " +
      esc(info.company) +
      '</h1><p class="sub">' +
      (invitation
        ? "Accept your company invitation."
        : "Your company reviews new registrations before access is granted.") +
      '</p><form id="joinform" class="formgrid">' +
      field("Full name", "name") +
      field("Work email", "email", "email") +
      field("Password (12+ characters)", "password", "password") +
      (invitation ? "" : field("Team", "team") + field("Job title", "title")) +
      '<input type="hidden" name="invitation" value="' +
      esc(invitation) +
      '"><button class="btn">Create account</button><div class="error"></div></form><a class="quiet" href="/">Back to sign in</a>';
  else
    content =
      '<h1>Your work, together.</h1><p class="sub">Sign in to ' +
      esc(info.company) +
      ".</p>" +
      (info.demo
        ? '<div class="form-actions">' +
          btn("Employee demo", "login-employee") +
          btn("HR demo", "login-hr", "btn") +
          "</div>"
        : btn("Continue with Google", "google-login", "google-button")) +
      '<form id="loginform" class="formgrid">' +
      field("Work email", "email", "email") +
      field("Password", "password", "password") +
      '<button class="btn">Sign in</button><div class="error"></div></form>' +
      (!info.demo
        ? '<p class="sub">New here? <a href="/join">Request company access</a></p>'
        : "") +
      (location.search.includes("registration=pending")
        ? '<p class="notice">Your Google registration is awaiting company approval.</p>'
        : "");
  $("#workspace").innerHTML =
    '<div class="auth-shell"><aside class="auth-story"><div class="brand"><span class="mark">' +
    icon("logo") +
    '</span>PeopleDesk</div><h2>A place for your people<br>and the work you share.</h2><p>Personal work plans. Connected calendars.<br>Private conversations. One company workspace.</p><div class="auth-decoration"><div></div><div></div><div></div></div></aside><main class="login"><section class="card loginbox">' +
    content +
    "</section></main></div>";
};
const oldBoot = boot;
boot = async function () {
  try {
    info = await api("info");
    if (
      info.setup ||
      location.pathname === "/join" ||
      location.hash.startsWith("#invite=")
    )
      return showLogin();
    if (!info.signed && info.demo && !sessionStorage.getItem("pd_signedout"))
      await api("login", {
        demo: location.pathname === "/employee" ? "employee" : "hr",
      });
    else if (!info.signed) return showLogin();
    await refresh();
    route(location.hash.slice(1) || "overview");
  } catch (e) {
    $("#workspace").innerHTML =
      '<main class="loading">' +
      esc(e.message) +
      btn("Retry", "boot") +
      "</main>";
  }
};
function roleOptions() {
  return Object.entries(S.roles).filter(
    ([r]) => isOwner() || !["owner", "hr"].includes(r),
  );
}
function assignment(p = {}) {
  form(
    "Plan an assignment",
    "assign",
    field("Task title", "title", "text", p.title || "") +
      field("Description", "description", "textarea", "", false) +
      personField("Responsible person", "owner", p.owner || S.user.id) +
      personField("Collaborator", "helper", "", true) +
      '<div class="duo">' +
      field("Due date", "due", "date", nextDate(1)) +
      field(
        "Priority",
        "priority",
        "select",
        "Normal",
        true,
        ["Low", "Normal", "High"].map((x) => [x, x]),
      ) +
      "</div>" +
      field("Project or initiative", "project", "text", "", false) +
      '<p class="summary-note">Assignments within your management scope are scheduled directly. Other colleagues receive a collaboration invitation.</p>',
    "Create assignment",
  );
}
async function extraAction(b) {
  const a = b.dataset.act,
    id = b.dataset.id;
  if (a === "google-login") {
    const r = await api(a, {});
    location.assign(r.url);
    return true;
  }
  if (a === "personal-assign" || a === "assign-person") {
    assignment({ owner: id });
    return true;
  }
  if (a === "plan-today" || a === "plan-tomorrow") {
    planDay = a.slice(5);
    draw();
    return true;
  }
  if (a === "files-local" || a === "files-google") {
    fileView = a.slice(6);
    draw();
    return true;
  }
  if (a === "notifications") {
    showModal(
      "Your updates",
      S.notifications
        .map(
          (n) =>
            '<div class="source"><b>' +
            esc(n.created.replace("T", " ")) +
            " UTC</b>" +
            esc(n.title) +
            "</div>",
        )
        .join("") || empty("You are up to date."),
    );
    await api("read-notifications", {}, crypto.randomUUID());
    return true;
  }
  if (a === "new-announcement") {
    form(
      "Company update",
      "publish-notice",
      field("Title", "title") + field("Update", "body", "textarea"),
      "Publish update",
    );
    return true;
  }
  if (a === "adjust-leave") {
    const p = S.people.find((x) => x.id === id);
    form(
      "Adjust leave for " + p.name,
      "leave-adjust",
      '<p class="summary-note">Current balance: ' +
        (p.balance ?? 0) +
        " working days. Add the approved entitlement or record a correction with a reason.</p>" +
        field("Days to add (negative to deduct)", "days", "number") +
        field("Reason", "reason", "textarea"),
      "Record adjustment",
      { id },
    );
    return true;
  }
  if (a === "accept-task" || a === "progress") {
    await api(
      a === "progress" ? "task-progress" : a,
      { id, status: b.dataset.status },
      crypto.randomUUID(),
    );
    await refresh();
    taskDetail(id);
    return true;
  }
  if (a === "comment-task") {
    form(
      "Progress update",
      "task-comment",
      field("Update", "body", "textarea"),
      "Add note",
      { id },
    );
    return true;
  }
  if (a === "share-file") {
    form(
      "Share a workspace file",
      "share-file",
      '<label class="field">File (up to 5 MB)<input name="attachment" type="file" required></label>' +
        field("Access", "audience", "select", "team:" + S.user.team, true, [
          ["private", "Only me"],
          ["team:" + S.user.team, "My team"],
          ["company", "Entire company"],
        ]),
      "Upload file",
    );
    return true;
  }
  if (a === "invite-member") {
    form(
      "Invite a colleague",
      "invite",
      field("Work email", "email", "email") +
        field("Team", "team") +
        field("Job title", "title") +
        field(
          "Workspace role",
          "access",
          "select",
          "employee",
          true,
          roleOptions(),
        ) +
        personField("Manager / coordinator", "manager"),
      "Create invitation",
    );
    return true;
  }
  if (a === "review-member") {
    const r = S.registrations.find((x) => x.id === id);
    form(
      "Review registration",
      "membership",
      '<div class="source"><b>' +
        esc(r.name) +
        "</b>" +
        esc(r.email) +
        "<br>" +
        esc(r.team) +
        " · " +
        esc(r.title) +
        "</div>" +
        field("Decision", "decision", "select", "Approved", true, [
          ["Approved", "Approve access"],
          ["Declined", "Decline"],
        ]) +
        field(
          "Workspace role",
          "access",
          "select",
          "employee",
          true,
          roleOptions(),
        ) +
        personField("Manager", "manager"),
      "Record decision",
      { id },
    );
    return true;
  }
  if (a === "edit-member") {
    const p = S.people.find((x) => x.id === id);
    form(
      "Manage " + p.name,
      "member-access",
      field("Team", "team", "text", p.team) +
        field("Job title", "title", "text", p.title) +
        field(
          "Workspace role",
          "access",
          "select",
          p.access,
          true,
          roleOptions(),
        ) +
        personField("Manager", "manager", p.manager || "", true) +
        field(
          "Account status",
          "active",
          "select",
          p.active ? "1" : "0",
          true,
          [
            ["1", "Active"],
            ["0", "Deactivated"],
          ],
        ),
      "Save access",
      { id },
    );
    return true;
  }
  if (a === "provider-settings") {
    form(
      "Company provider setup",
      "provider-config",
      '<p class="summary-note">Use your company OAuth application credentials. The redirect URI is <strong>' +
        esc(location.origin + "/oauth/account") +
        "</strong>. Saved secrets are hidden.</p>" +
        [
          "GOOGLE_CLIENT_ID",
          "GOOGLE_CLIENT_SECRET",
          "ZOOM_ACCOUNT_ID",
          "ZOOM_CLIENT_ID",
          "ZOOM_CLIENT_SECRET",
          "ZOOM_HOST",
        ]
          .map((k) =>
            field(
              k.replaceAll("_", " ").toLowerCase(),
              k,
              k.includes("SECRET") ? "password" : "text",
              "",
              false,
            ),
          )
          .join(""),
      "Save settings",
    );
    return true;
  }
  if (a.startsWith("cloud-")) {
    if (S.mode === "demo")
      throw Error(
        "Open Start Company.cmd to configure real provider accounts.",
      );
    if (
      a === "cloud-disconnect" &&
      !confirm("Disconnect your Google account and clear its local preview?")
    )
      return true;
    const r = await api(a, {});
    if (r.url) location.assign(r.url);
    else {
      await refresh();
      toast(r.message);
    }
    return true;
  }
  if (a === "sync-task") {
    if (!confirm("Copy this task to your connected Google Tasks account?"))
      return true;
    const r = await api("cloud-task", { id });
    await refresh();
    toast(r.message);
    return true;
  }
  if (a === "email-digest") {
    if (
      !confirm(
        "Email your current work plan to " +
          S.user.email +
          " using your connected Gmail account?",
      )
    )
      return true;
    const r = await api("cloud-digest", {});
    await refresh();
    toast(r.message);
    return true;
  }
  if (a === "sync-meeting") {
    if (!confirm("Copy this meeting to your connected Google Calendar?"))
      return true;
    const r = await api("cloud-meeting", { id });
    await refresh();
    toast(r.message);
    return true;
  }
  if (a === "install-portal") {
    if (deferredInstall) {
      await deferredInstall.prompt();
      deferredInstall = null;
    } else
      showModal(
        "Install your employee portal",
        '<p class="formtext">Open this workspace in Edge or Chrome and use the browser menu to install it as an app. Use the same company URL on each device.</p><div class="source"><b>Employee portal URL</b>' +
          esc(location.origin + "/employee") +
          "</div>",
      );
    return true;
  }
  if (a === "chat-lock") {
    Messenger.lock();
    draw();
    return true;
  }
  if (a === "chat-room") {
    await Messenger.open(id);
    return true;
  }
  if (a === "chat-older") {
    await Messenger.load(true);
    return true;
  }
  if (a === "chat-refresh") {
    await Messenger.fetch();
    draw();
    return true;
  }
  if (a === "chat-new" || a === "contact-chat") {
    if (!Messenger.keys) {
      route("messages");
      toast("Unlock private chat to start a conversation.");
      return true;
    }
    await Messenger.fetch();
    const ready = Messenger.snapshot.keys.map((k) => k.person);
    if (id && id === S.user.id) throw Error("Choose a colleague.");
    if (id && !ready.includes(id))
      throw Error(name(id) + " needs to activate private chat first.");
    if (id) {
      const r = await api("room-create", {
        kind: "direct",
        members: [id],
        title: "Conversation",
      });
      await Messenger.fetch();
      route("messages");
      await Messenger.open(r.id);
      return true;
    }
    form(
      "New conversation",
      "room-create",
      field("Conversation type", "kind", "select", "direct", true, [
        ["direct", "Direct message"],
        ["group", "Project group"],
      ]) +
        field("Group name", "title", "text", "", false) +
        '<fieldset class="field"><legend>People with private chat activated</legend><div class="checkgroup">' +
        S.people
          .filter((p) => p.id !== S.user.id && ready.includes(p.id))
          .map(
            (p) =>
              '<label><input type="checkbox" name="members" value="' +
              esc(p.id) +
              '"> ' +
              esc(p.name) +
              "</label>",
          )
          .join("") +
        "</div></fieldset><small>Group membership is fixed. Create a new group when the project team changes.</small>",
      "Start conversation",
    );
    return true;
  }
  if (a === "chat-verify") {
    const room = Messenger.room;
    let content =
      '<p class="summary-note">Compare these fingerprints with each participant through a trusted separate channel. First contact is trusted until you verify it.</p>';
    for (const [pid, pub] of Object.entries(room.roster)) {
      content +=
        '<div class="source"><b>' +
        esc(name(pid)) +
        '</b><code class="fingerprint">' +
        (await Messenger.hash(pub)).match(/.{1,4}/g).join(" ") +
        "</code></div>";
    }
    showModal("Verify participants", content);
    return true;
  }
  return false;
}
async function afterExtra(m, result, d) {
  if (m.op === "invite") {
    showModal(
      "Invitation ready",
      '<p class="formtext">Share this invitation with ' +
        esc(result.email) +
        ". It expires in seven days and can be used once.</p>" +
        field(
          "Invitation link",
          "invite-link",
          "text",
          location.origin + "/join#invite=" + result.invitation,
        ),
    );
    return true;
  }
  if (m.op === "task-comment") {
    taskDetail(m.context.id);
    return true;
  }
  if (m.op === "assign") {
    route("work");
    taskDetail(result.id);
    return true;
  }
  if (m.op === "room-create") {
    await Messenger.fetch();
    route("messages");
    await Messenger.open(result.id);
    return true;
  }
  if (m.op === "provider-config") {
    route("integrations");
    toast(result.message);
    return true;
  }
  if (m.op === "membership" || m.op === "member-access") {
    route("members");
    return true;
  }
  return false;
}
async function extraSubmit(f) {
  const d = Object.fromEntries(new FormData(f)),
    button = f.querySelector("button[type=submit],button:not([type])");
  const original = button.innerHTML;
  button.disabled = true;
  button.textContent = "Working…";
  try {
    if (f.id === "keyform") {
      await Messenger.unlock(d.passphrase);
      return;
    }
    if (f.id === "composeform") {
      await Messenger.send(d.message.trim());
      return;
    }
    if (f.id === "setupform") {
      await api("workspace-setup", d);
      sessionStorage.removeItem("pd_setup");
      history.replaceState(null, "", "/");
      info = await api("info");
      await refresh();
      return;
    }
    if (f.id === "joinform") {
      const r = await api("register", d);
      f.innerHTML =
        '<p class="notice">' +
        esc(
          r.message ||
            "Your account is ready. Sign in with your work email and password.",
        ) +
        '</p><a class="btn" href="/">Go to sign in</a>';
      return;
    }
  } catch (e) {
    const error = f.querySelector(".error") || $("#chat-error");
    if (error) error.textContent = e.message;
    else toast(e.message);
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.innerHTML = original;
    }
  }
}
const oldEventDetail = eventDetail;
eventDetail = function (id) {
  const e = S.events.find((e) => e.id === id);
  if (!e) return;
  if (e.remote) {
    showModal(
      e.title,
      '<dl class="details">' +
        pair(
          e.all_day ? "Start (all day)" : "Start (UTC)",
          e.starts.replace("T", " "),
        ) +
        pair(
          e.all_day ? "Ends before (all day)" : "End (UTC)",
          e.ends.replace("T", " "),
        ) +
        pair("Calendar", "My Google Calendar") +
        '</dl><p class="summary-note">Private to your account. Updated when you refresh Google in Connections.</p>' +
        (safeURL(e.link)
          ? '<a class="btn" target="_blank" rel="noreferrer" href="' +
            esc(e.link) +
            '">Open in Google</a>'
          : ""),
    );
    return;
  }
  oldEventDetail(id);
  if (e.people.includes(S.user.id))
    $("#modal .form-actions").insertAdjacentHTML(
      "beforeend",
      btn(
        "Sync to my Google Calendar",
        "sync-meeting",
        "quiet",
        "plug",
        da("id", id),
      ),
    );
};
document.addEventListener("change", async (e) => {
  if (e.target.id === "demo-role" && e.target.value) {
    resetSession();
    await api("login", { demo: e.target.value });
    view = "overview";
    await refresh();
  }
});
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstall = e;
});
window.addEventListener("beforeunload", () => Messenger.lock());
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
