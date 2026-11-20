# PeopleDesk 3 — actions and routines

This release adds an assistant workspace to the existing employee/HR application. Open PeopleDesk.exe from the new PeopleDesk-3 folder. It opens your browser on the Assistant page; no editor, Python installation or terminal is needed.

## Try these requests

- “Assign Karan to review the launch checklist tomorrow.” Review the action, edit fields if needed, then Run plan. The receipt opens the created task.
- “Make it Friday.” Revises a pending plan's date. “Move it to 4 pm” revises a meeting time. “Do it” executes the latest ready plan; “Cancel it” cancels it.
- “Draft an email to Karan asking for a launch update.” Local Qwen generates the subject and body. Running creates an HR approval request, not an external send.
- “Schedule a Zoom meeting with Karan tomorrow at 3 pm.” Running submits a meeting request. HR approval and connected provider execution remain separate.
- “Give me a workload brief.” Shows visible overdue, blocked and due work with supporting records. Counts are not performance ratings.
- “Message Karan: Can we review the launch tomorrow?” Creates a browser-only private draft. Activate Messages for both participants first. Send private message encrypts it using the existing chat keys. This explicit message command is not sent to the assistant endpoint or stored in assistant history.

Use Routines → Create routine for a weekday task. Review and run its plan to activate it. You can pause/resume it and open the task created by each run. Only automate work for yourself or employees you manage.

Find anything, or Ctrl+K, searches the people, tasks, meetings, handbook and workspace file records visible to the signed-in user.

## Execution and history

Assistant conversations and pending plans persist per account. Each plan contains up to four supported actions. You can edit fields before execution. New versions invalidate older execution requests. Local steps execute in one SQLite transaction: a failure rolls the plan back. A completed plan returns its original receipts when retried, rather than creating duplicates.

The assistant cannot bypass employee access, collaboration acceptance, HR approval or external-send requirements. A local request is not a confirmed Google/Zoom booking. The UI distinguishes a saved task, pending approval, private message and provider operation.

Common assignment, meeting, email and date/time revisions have bounded parsing paths. Qwen drafts email and handles other supported planning and conversation. The included small local model can still misunderstand requests. Missing or invalid fields stop execution and can be edited. There is no claim of universal autonomous understanding.

Regular assistant requests and history are stored on the company server; they are not end-to-end encrypted. The explicit private-message command is handled in the browser. Do not paste confidential private-chat text into unrelated assistant requests.

## Background routines

The company service checks routines every 30 seconds. Rules create one task on each weekday at the configured UTC time. The server must remain running; closing the browser is fine, stopping the service stops processing. Missed dates collapse to one catch-up task on the next working day. A unique run record prevents duplicate tasks even with simultaneous checks.

Each run checks the creator's active account and management scope and the recipient's active account. Lost access pauses the rule. Routine scheduling is for tasks; it does not automatically send external emails or make employment decisions.

## Scope of this release

The app includes role portals, approval workflows, connected provider adapters, private group/direct messaging, task collaboration, files, search, an action assistant and weekday routines. It is not at Microsoft Teams feature parity. Native audio/video calls, screen sharing, rich channels/threads, enterprise SSO/provisioning, high availability and enterprise compliance controls remain future work.

Google/Zoom live operation still requires company credentials and consent. Sync is on demand. The free local model avoids an AI API subscription; third-party providers, hosting and infrastructure may have their own limits or charges. No independent security audit or large-workforce benchmark has been completed.
