# PeopleDesk 3

Start with ASSISTANT.md for conversation-driven actions and background task routines.

# PeopleDesk — company workspace

Open **PeopleDesk.exe** for the fictional Aster Works demo. Open **Employee portal.cmd** for Karan's personal workspace. Both use the same local service and data; switching demo roles changes the perspective. The existing HR workflows, Qwen assistant and Handoff module remain available. The clean PeopleDesk-3 folder contains the latest executable; earlier releases are preserved separately.

Keep the neighbouring **Handoff-Studio** folder beside **PeopleDesk-3** in the portable release. It contains the shared Qwen model and inference engine. The Windows executable includes the application dependencies; no Python installation or paid model account is needed. The complete portable ZIP includes both folders.

## Explore the upgrade

1. Open the employee portal. **My day** shows today's and tomorrow's assignments, who assigned them, collaborators and scheduled meetings.
2. Select **Engineering manager** in the demo role menu. In **Team workspace**, assign a task to Karan. Switch back to Karan, open tomorrow's plan and update progress or add a note.
3. Open **Messages** and create a separate chat passphrase of at least 16 characters. Activate chat for the other demo participants too. Use **New conversation** to start a direct message or a project group. For simultaneous perspectives, use separate browser profiles or an incognito window; tabs in one browser profile share a login cookie.
4. Open **Files** to share a document privately, with your team or with the whole company. The upload limit is 5 MB.
5. Open **Calendar**, **My requests**, **Handbook** or the assistant. HR can review sensitive requests in **Approvals**, run onboarding/exit/review checklists, review model-generated handoffs and create formal email drafts.

Aster Works contains 32 fictional employees, opening leave ledgers, ten handbook sections, assignments, meetings, workflow checklists and requests. Karan starts with 18 remaining working days. Approving his seeded one-day leave request changes the ledger to 17, once. Demo data persists between launches; relative dates are calculated on first creation. A CSV snapshot is included in **Aster-Works-demo-data.zip**. No company's private employee dataset was used.

## Start a real company workspace

Open **Start company.cmd**. The first browser launch opens a private setup link for the company name and first administrator account. Choose a password of at least 12 characters. This company database is separate from the demo.

In **People & access**, invite colleagues using a one-use link, or review registrations submitted at **/join**. Registration alone grants no access. Approve the person's role and coordinator. Uninvited Google users also enter the approval queue. The administrator can change roles, teams and managers or deactivate an account. Deactivation blocks existing sessions on their next request.

| Workspace role | Access |
| --- | --- |
| Founder / administrator | Company configuration, membership, HR operations and company work |
| People operations | Registrations, employee records, approvals and HR workflows; cannot grant HR/administrator access |
| Manager / VP | Work within their team or direct reports, assignments, announcements and their personal workspace |
| Team lead | The same team coordination scope as a manager |
| Team member | Their own assignments and collaborations, requests, calendar, files and messages |

Job titles and teams are separate from permissions: developer, designer, marketing, finance and other roles can use the same workspace. A task proposed outside a person's management scope requires the responsible colleague's acceptance. HR can record opening leave entitlement and corrections by clicking the leave balance beside a member; every adjustment includes a reason and audit entry. Newly registered members start without a leave entitlement until HR records it.

## Employee app and shared installation

The employee portal is **/employee** on the same company URL. It has an installable web-app manifest: use **Install portal** or the Edge/Chrome app-install menu. **Employee portal.cmd** opens the URL in the environment variable **PEOPLEDESK_COMPANY_URL**, or the local company portal when unset.

For a company to collaborate, all devices must connect to **one shared service and database**. Separate local installations create independent companies. The default service listens only on the local computer. For shared use, operate the company service behind an HTTPS reverse proxy, forwarding the original Host header to **127.0.0.1:8879**. Set **PEOPLEDESK_ORIGIN** to the exact public HTTPS origin, with no path or trailing slash, before starting the service. Keep the demo port **8878** local. Chat requires HTTPS or localhost. This build does not include an automatic server installer, certificate provisioning or multi-tenant SaaS hosting.

The database is stored under **%LOCALAPPDATA%\\PeopleDesk**. Set **PEOPLEDESK_DATA** to change its directory and **PEOPLEDESK_PORT** to change the service port. Back up SQLite through its backup API or with the service stopped. Provider credentials use Windows DPAPI and depend on the Windows account operating the server; a database copy alone will not recover those credentials on a different host.

## Connect Google and Zoom

Use company mode. The administrator opens **Connections → Company provider setup** and saves credentials. Saved secrets are hidden. Environment variables with the prefix **PEOPLEDESK_** and the same field names can override the settings.

**Google setup:** enable Calendar, Gmail, Drive and Tasks APIs in your company's Google Cloud project, configure the OAuth consent screen and create an OAuth web application. Register the exact callback displayed in the form: **http://127.0.0.1:8879/oauth/account** locally, or **https://your-company-host/oauth/account** for the shared HTTPS service. Save **GOOGLE_CLIENT_ID** and **GOOGLE_CLIENT_SECRET**. In testing mode, add the intended users to the provider's test-user list. Google may require app verification for broader distribution and the requested scopes. [Google web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server) · [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)

**Continue with Google** verifies the identity token, audience, issuer, expiry and nonce. A verified email matching an existing company account can sign in; a new email requires company approval. A shared email domain never grants membership or elevated access. Signed-in members use **Connect Google** separately to consent to resource access with their own matching work account.

| Connection | Implemented behaviour |
| --- | --- |
| Calendar | Refresh pulls the next 31 days into the member's personal calendar. A member can explicitly copy or update a PeopleDesk meeting in their primary Google calendar. |
| Gmail | Shows the latest ten inbox subjects/senders. A member can explicitly email their own work plan once a day. HR can create a Gmail draft from an approved formal email and explicitly send it. |
| Drive | Lists the latest 50 accessible files and opens them in Drive. Local workspace uploads use their chosen access scope. |
| Tasks | Shows up to 100 tasks from the default list. A member can copy assigned work, then update its due date/status using the same remote task. |
| Zoom | HR can create a meeting for an approved request and use its join URL in the calendar invitation. |

Refresh and write actions are on demand. This is not continuous, fully bidirectional sync: editing a Google Task does not overwrite a PeopleDesk assignment; Drive previews do not upload local files to Drive. Failed refreshes retain previous results with a visible message. Provider writes with uncertain completion are blocked from automatic replay and marked **Verify with provider**. Check the provider account before reconciling those records.

**Zoom setup:** create and activate a company Server-to-Server OAuth app with the meeting-create scope appropriate for the host. Set **ZOOM_ACCOUNT_ID**, **ZOOM_CLIENT_ID**, **ZOOM_CLIENT_SECRET** and **ZOOM_HOST** (the host's email or user ID), then use **Test Zoom connection**. On an approved Zoom request, create the Zoom meeting before publishing its Google Calendar invitation. Provider account permissions and limits still apply. [Zoom Server-to-Server OAuth](https://developers.zoom.us/docs/internal-apps/s2s-oauth/) · [Create meetings](https://developers.zoom.us/docs/isv/workflows/create-meeting/)

## Private conversations

Messages are encrypted and signed in participants' browsers before upload. The API stores ciphertext and encrypted key backups. Conversation membership controls access, with no administrator override in the app. Each member unlocks their private identity using a separate chat passphrase, including on another device. The service cannot reset or recover a forgotten chat passphrase.

Compare participant fingerprints through another trusted channel using **Verify people**. Group membership is fixed; create a new group when the project team changes. The server can see participant identities, group titles, message sizes and timing. Files outside chat have access controls but are not end-to-end encrypted.

This is a prototype cryptographic protocol, without an independent audit or forward secrecy. A compromised browser or a server operator who changes the JavaScript delivered to users can defeat browser-side secrecy. Do not claim that a malicious app developer or administrator can never access plaintext. See [SECURITY.md](../SECURITY.md) for the precise limits.

## Assistant and human approvals

The included local Qwen model interprets supported requests, drafts formal emails and extracts handoffs from meeting notes. Leave figures come from ledger sums. Policy responses quote company handbook records. The app does not invent leave balances or send a model's draft automatically. HR approves sensitive actions, and an external send requires a separate explicit action.

Employee relations, hiring decisions, pay changes, performance judgments and statutory payroll calculations remain human responsibilities. Calendar times are UTC. Leave uses Monday–Friday working days, without holiday calendars or shift-based accrual. Reminders update when the workspace refreshes; weekday task routines run while the service is open; there is no background email scheduler.

## Validation and source

The upgrade was checked with independent browser sessions for manager assignments, employee progress, encrypted group messages, key recovery and administrator access denial, plus mobile layout. API tests cover setup, invitations, approvals, leave, file isolation, role escalation, OAuth state/nonce/replay protection and actual JWT signature validation. Provider reads and writes were exercised with test doubles; live Google/Zoom account operation still needs the company's credentials and consent.

Source entry point: **PeopleDesk/app.py** in the repository. Use Python 3.12 on Windows and install **requirements.txt**. Run **python app.py**, **python app.py --employee**, or **python app.py --company**. The local model can be overridden with **PEOPLEDESK_ENGINE**. The existing Handoff source is needed alongside the app for source execution and is bundled into the executable.

This is a working local/pilot application. A broad company rollout still needs load testing, deployment operations, backup/recovery validation, security review and organisation-specific configuration. It is not yet a horizontally scalable replacement for every company system.
