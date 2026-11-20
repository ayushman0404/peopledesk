# Validation scope

Run **python scripts/check.py** after installing development requirements.

| Suite | Coverage |
| --- | --- |
| verify.py | HTTP workflows, leave ledger, approvals, exports and uncertain provider outcomes |
| verify_company.py | Registration, invitations, file/task isolation, OAuth state/nonce and JWT signatures |
| verify_copilot.py | Plan revisions, cross-account denial, concurrent replay, rollback and approval boundaries |
| verify_routines.py | Weekday scheduling, concurrency, catch-up and deactivation |

Synthetic records and provider doubles are used; no live Google/Zoom account is exercised. JWT signature checks use freshly generated test keys.

Local-model tests are explicitly skipped by default. With **PEOPLEDESK_TEST_MODEL=1**, they require the separately installed engine and model. Missing files then fail instead of silently skipping.

Optional browser checks from the repository root: install Playwright with **npm install --no-save playwright**, install Chromium with **npx playwright install chromium**, then run **node tests/copilot_ui.cjs**. This exercise needs the local model and **python** on PATH. Screenshots under tests/ are ignored.

The Windows CI workflow runs the default Python suites. CI results refer to that commit. These checks are not held-out model accuracy, an independent security audit, production-load measurements or customer-impact evidence.
