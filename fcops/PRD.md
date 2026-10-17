# KapilFutureTech Internal Engineering Platform

Product requirements document — version 0.1, 17 October 2026

Status: requirements baseline for review. Documentation is authorised; implementation has not been authorised. The agreed product direction below does not imply that every detailed proposal or the pilot delivery scope has been approved.

## 1. Purpose and outcomes

Build and own one internal platform for KapilFutureTech's software, firmware, hardware, assembly, mechanical, rover, pilot, and service teams. Reuse the existing `fcops` application where appropriate.

The platform must shorten the journey from a field report to accountable engineering ownership, preserve unit and configuration evidence, coordinate daily work, and announce approved GCS releases to selected users.

Success means that reports do not disappear between departments, ownership and handoffs are explicit, resolution is independently checked, and employees find relevant history without receiving unrestricted access to unrelated records.

### Reference incident

A customer reported a GCS problem to a service engineer. It took five days to reach Software. Investigation also found a problem with the flashed parameter file.

The new workflow must accept this report before the serial number, exact version, or root cause is known; route it promptly; track human acknowledgement; escalate unattended reports; and preserve separate GCS and configuration investigations within one customer incident.

## 2. Organisation and use context

| Team | Approximate people |
| --- | ---: |
| Core software | 4 |
| Firmware | 2 |
| PCB hardware | 3 |
| Assembly | 4 |
| Mechanical | 3 |
| Rover | 4 |
| Pilots | 6–12 |
| Service engineers | 6 |

Code is maintained on GitHub. Development uses VS Code, Claude Code, and OpenAI Codex. No company-wide work-management platform is established. Hardware serial numbers are currently tracked on paper.

Employees primarily use browsers on Windows and Android, including at customer sites and testing grounds. Windows development does not require Windows hosting. Normal hours are 10:00–18:00; issues can be reported at any time. Workdays, holidays, acknowledgement targets, and after-hours coverage remain to be agreed.

## 3. Decision register

### Confirmed

- One application covers cross-team issues, FC traceability, GCS releases and email announcements, and daily tasks/progress.
- Reuse the existing application as the candidate foundation; keep a centrally hosted modular monolith as the preferred architecture.
- All team heads and the manager can see all engineering issues and progress.
- Team members can see their team's issues, their own reported issues, and records on which they are explicitly included. A receiving team gains issue access during a cross-team handoff.
- Customer contact details and the signup mailing list are limited to authorised people.
- Each release requires approval by both the manager and the Software head.
- Release announcement emails go to selected GCS users. A signup API exists; its contract will be provided or reviewed by the product owner.
- Email announcement and installing an update are separate activities.
- Preserve existing modified and untracked files.
- Four days is an initial focused pilot target, not a production-readiness commitment.

### Proposed defaults requiring operational confirmation

- Route known product reports to the corresponding team head; unknown reports go to a designated coordinator with the manager as backup.
- Maintain one accountable person per issue. A team head is accountable until a named member accepts ownership.
- Keep the current owner accountable until a proposed handoff is accepted.
- Normal acknowledgement clocks use agreed working hours; urgent reports alert the responsible head immediately at any time.
- Software-head technical approval precedes manager approval. Both approvals are mandatory; whether order is required remains open.
- Daily task details are visible to the employee, collaborators, their team head, other team heads, and the manager. Ordinary teammates do not automatically see all personal task details.
- Private customer/contact data is separate from broadly visible engineering summaries.

## 4. Scope and exclusions

### Included in the product

1. Quick issue reporting, triage, accountable ownership, acknowledgement, accepted handoffs, reminders, escalation, investigation, resolution, verification, and knowledge.
2. FC registration, unique serials, lifecycle, assembly/test/rework history, firmware and configuration evidence.
3. GCS release records, dual approval, selected recipient email preview/send/history.
4. Daily tasks, dated updates, blockers, and team-head visibility.
5. Backend access enforcement across all data access paths.
6. Minimal customer/deployment context needed for service and engineering traceability.

### Excluded for now

Sales, marketing campaigns, social monitoring, call tracking, a full CRM, procurement/ERP, payroll, native mobile applications, automatic GCS installation, direct USB flashing, and comprehensive lifecycle tooling for every non-FC hardware family.

Offline submission, GitHub synchronisation, automated device read-back, and GCS integration are future options, not assumed pilot commitments. Existing Configurator records may remain; expanding its release workflow is secondary to the GCS requirement.

## 5. Roles and access

Separate role capabilities (what a person may do) from record scope (what they may see). Job titles alone must not grant unrestricted writes.

| Role or relationship | Read scope | Write/decision authority |
| --- | --- | --- |
| Employee | Own team's issues, own reports, explicitly shared issues; own/collaborative tasks | Report, comment, upload evidence, update permitted tasks; issue actions depend on responsibility |
| Team head | All engineering issues and progress | Triage, allocate and coordinate their team; access alone does not permit changing another team's work |
| Manager | All engineering issues and progress | Escalation oversight and release approval; sensitive data requires an explicit grant |
| Software head | Team-head scope | Technical release approval; release drafting/sending permissions are separate |
| Assigned verifier | Explicitly shared issue and necessary evidence | Verify or reject a resolution; cannot verify their own resolution |
| Administrator | Account/configuration management | No automatic product approval by virtue of being administrator; privileged data access must be controlled and audited |
| External GCS recipient | Email and approved release material only | No internal platform account or issue access implied by signup |

FC history is available to authorised production, engineering, testing, and service users within assigned scope. The exact FC access matrix must be agreed before exposing it to the pilot group. Knowledge articles have an explicit published audience; an article may be broadly visible without exposing restricted source occurrences.

Acceptance requirements:

- Filter backend list/detail queries and validate object relationships on create/update.
- Apply the same policy to search, similar results, dashboards/counts, nested data, exports, timelines, audit entries, parameter comparison, and attachments.
- Never grant access to every linked record merely because a user can read one parent record.
- Keep files private; check permissions before download or before issuing short-lived access links.
- Notifications must not disclose details to unauthorised recipients. Recheck current access when displaying stored notifications and opening their links.
- Cache entries must respect user scope and permission changes.
- Removing team membership or explicit access must remove future access consistently.
- Cross-team sharing must not expose the signup mailing list or restricted customer contact fields.

## 6. Issue management

### 6.1 Rapid reporting

Require a short title, observed symptom, and impact/urgency selection with an explicit Unknown option. Capture reporter and submission time automatically. Permit unknown product, customer, deployment, serial number, stage, and version.

Optional initial evidence includes photos, logs, screenshots, parameter files, approximate occurrence time, location/context, and reproduction notes. Technical completeness must not block submission. Show the report ID and current responsible queue after successful submission.

### 6.2 Routing, acknowledgement, and ownership

Route known products to a configured team queue. Unknown reports need a named fallback coordinator; this person is not yet selected. A queue requires a responsible head and backup.

Record separate events for submission, routing, assignment, notification, and explicit human acknowledgement. Opening a page or sending a notification is not acknowledgement. Distinguish the responsible department, accountable person, collaborators, and root-cause department.

A handoff records proposed recipient/team, reason, time, accepting/rejecting actor, and response. The old owner retains accountability until acceptance. Rejecting requires a reason. The receiving team gains the necessary engineering context; the reporter retains issue visibility. Exact historical access for previous teams remains an access-policy decision.

### 6.3 Status, urgency, and follow-up

Proposed work states: Open → Investigating → Resolved → Verified → Closed. Acknowledgement and pending handoff are separate workflow attributes. Waiting is a flag with reason, dependency owner, and next follow-up date; it must not silently disable reminders indefinitely.

Separate customer/flight impact and urgency from whether a specific FC production stage is blocked. Linking a severe service issue must not automatically block an FC without the applicable production decision.

Reminders and escalations must use configurable acknowledgement and follow-up deadlines, record their history, and avoid duplicate alerts. Escalate unattended reports and unaccepted handoffs. Coverage gaps and delivery failures must be visible to the responsible head/manager.

Allow submission at all hours. Urgent notifications can be immediate, but guaranteed after-hours acknowledgement requires a named duty contact and agreed coverage. The platform must not imply coverage that has not been staffed.

### 6.4 Investigation, resolution, and verification

Keep append-only investigation notes and a timestamped action history. Preserve the difference between observed symptoms, suspected cause, confirmed cause, workaround, and permanent correction.

Support a parent service incident with linked team work when Software and Firmware/configuration need separate owners. Avoid forcing all technical work under one department or creating disconnected customer reports.

Resolution records the change/workaround, evidence, affected versions/units, unresolved risks, and root-cause status. Do not force staff to invent a confirmed root cause for an unconfirmed or mitigated problem; exceptional closure rules need agreement.

Independent verification records who tested, what they tested, evidence, result, and time. The resolver cannot verify the same resolution. Failed verification returns work to investigation. Reopening preserves prior resolution/verification events; reopening authority remains to be confirmed.

### 6.5 Knowledge

Promote reviewed findings into searchable knowledge with symptoms, scope, diagnosis, resolution, and affected versions. Publish a customer-redacted article where broader sharing is useful. Counts, occurrence links, snippets, and similarity results must respect the reader's permissions.

## 7. FC lifecycle and configuration evidence

Retain specialised FC stages, attempts, test results, rework routes, serial uniqueness, and history. General service/software issues may have no FC or lifecycle stage. An issue may later link to one or more affected units without rewriting its original discovery facts.

Register new units digitally during the pilot. Existing paper records can be entered gradually, marked as historical/manual with source and uncertainty; do not invent dates or require bulk transcription before the pilot.

Keep these evidence types distinct:

| Type | Meaning | Required provenance |
| --- | --- | --- |
| Approved baseline | Authorised parameter set for a defined configuration | Revision, approver, approval time, compatibility and scope |
| Recorded flashed configuration | What an operator or tool records as applied | Unit if known, operator/tool, time, firmware, exact file/hash and source |
| Actual read-back | Values retrieved from the device at a particular time | Unit/device identity confidence, capture time, collector/tool, raw evidence/hash |

The presence of a flashed record is not proof of actual device state. An unknown unit is allowed on initial evidence, with explicit association added later.

Preserve raw parameter files and parsed values. Record parser warnings, comparison inputs, baseline revision, and any tolerance used. Treat differences as evidence for interpretation, not an automatic declaration that flight is safe or unsafe. New evidence supersedes earlier evidence through history rather than overwriting it.

Link the relevant GCS version, firmware version/build, hardware revision, deployment, and capture time. An FC's latest recorded version must not be silently presented as the version present during an earlier incident.

## 8. GCS releases and email announcements

### 8.1 Release record and approval

A release includes version, immutable source reference, artifact reference/checksum where available, internal notes, recipient-facing notes, compatibility, and known limitations.

Both the designated Software head and designated manager must approve the same release revision through authenticated actions. Selecting an approver's name is not approval. Store each actor, decision, revision, comment, and timestamp. The pilot must use two distinct people in these roles; delegation/absence rules remain open.

Changing approval-relevant content invalidates prior approvals. Rejection requires a reason and returns the release for revision. Existing legacy release rows must not be retroactively labelled as having completed this dual-approval process.

### 8.2 Signup API dependency

The product owner will obtain the API contract. Required review covers authentication, pagination, stable user IDs, email addresses, active/eligible status, product/version fields if available, preferences/opt-outs if supplied, rate limits, and refresh behaviour.

Keep API credentials on the backend. Treat external response fields as untrusted input. Define recipient eligibility before enabling real sending; signup alone does not determine every announcement audience.

An API outage must produce a visible failure or clearly identified approved snapshot; never silently fall back to mailing every known address. Do not scrape or invent API endpoints.

### 8.3 Preview, authorised sending, and history

An approved release does not automatically trigger email. A separately authorised sender selects eligible recipients or a defined segment, previews the exact subject/body and recipient list/count, and presses Send.

Save a snapshot of release revision, message, selected recipients, eligibility source/time, sender, and send time. Recheck authorisation and approval revision when queueing. Use individual delivery so recipients do not see one another's addresses.

Track per-recipient queued, provider-accepted, failed, and unknown outcomes. Record delivery/bounce events only where supported by the provider. Provider acceptance does not prove reading, delivery, or installation.

Repeated clicks must not create duplicate campaigns. Retry known failures deliberately; uncertain outcomes require reconciliation before retrying. Keep campaign and attempt history. A deliberate resend requires a visible action and reason.

Internal notes, customer incident details, and internal credentials must never enter recipient-facing emails. Installation/download adoption is a separate future capability.

## 9. Daily tasks and progress

A task has title, accountable person, team, priority, due date if relevant, status, optional issue/release/unit links, and collaborators. Proposed statuses: Planned, In progress, Blocked, Done, Cancelled.

Daily updates capture date, progress, next step, and blockers. Keep dated history rather than replacing yesterday's text. Avoid duplicate entry by linking issue activity and tasks while preserving a short human progress summary.

Heads need a view of assigned work, missing updates, overdue tasks, blockers, and next actions. All heads and the manager can see engineering progress. Whether updates are mandatory and whether teammates see all team tasks remain to be confirmed. Do not infer employee performance from activity counts.

## 10. Architecture and operational requirements

Use a centrally hosted modular monolith: React/Vite browser interface, Django/DRF backend, PostgreSQL, private file storage, and a durable background worker/scheduler. Suggested module boundaries are Accounts/access, Issues/knowledge, FC lifecycle/configuration, Customers/deployments, Releases/announcements, Tasks/progress, and shared audit/jobs/files.

Prefer one application origin, HTTPS, and secure browser authentication. Review the prototype's local-storage JWT approach before shared deployment; authentication design is not yet final.

A database-backed job queue is a pilot candidate to avoid another service. Claim jobs safely, persist retries/outcomes, and monitor worker/scheduler health. External email sends must follow committed database changes. Use transactions and concurrency controls for assignments, approvals, serial/key generation, and send requests.

Mobile priorities are quick reporting, acknowledgement, photo/log upload, and progress updates. Show clear network/upload failures and confirm successful submission. Offline queuing is excluded unless explicitly added to scope.

Maintain timestamped audit history for access changes, ownership, handoffs, configuration evidence, approval, verification, and email sending. Audit visibility follows record policy. Describe append-only guarantees within their actual threat model; database owners remain privileged.

Before shared use: production configuration, restricted administrative access, private downloads, appropriate upload limits, account deactivation, dependency review, backups of database and attachments, a restore exercise, error/job monitoring, and a migration/rollback plan. Do not use seeded default credentials for real employees.

Recurring costs must be justified by app hosting, PostgreSQL/backups, private storage, domain, and transactional email needs. No provider or price is approved by this document. Prefer few infrastructure services; managed versus self-hosted database choice depends on backup responsibility and operating effort.

## 11. Existing foundation and required changes

Source inspection confirms reusable lifecycle, issue, knowledge, release-record, parameter comparison, audit, and notification components. This planning session did not run the application or establish production readiness. Older README/implementation-note claims of successful runs are historical claims, not current verification.

Required changes include removing mandatory FC assumptions from general issues and services; adding accepted ownership/handoffs and deadlines; replacing universal-read policy and its tests; scoping dashboards/caches/search/files; introducing typed parameter provenance; replacing named-approver recording with dual authenticated approval; and adding tasks, customer/deployment links, and durable email jobs.

Do not replace existing lifecycle rules wholesale. Inventory and preserve local changes before implementation; parameter features are among the existing untracked work.

## 12. First release and four-day pilot

The product scope above is broader than a dependable four-day commitment. Proposed pilot group: representatives from Software, Firmware, Service, and Assembly, with named heads and a manager. Final pilot participants and feature cut remain to be approved.

| Sequence | Target |
| --- | --- |
| Day 1 | Establish isolated working/test baseline, confirm access matrix and operating owners, prove backend visibility filtering |
| Day 2 | Quick reporting without FC, acknowledgement, accountable ownership, handoff acceptance, basic reminders/escalation |
| Day 3 | Preserve FC workflow, add minimal deployment/configuration evidence links, minimal tasks/progress |
| Day 4 | Dual release approval and email preview/history, focused end-to-end/access verification, pilot review |

Real email integration depends on receiving and validating the signup API and sending infrastructure. If unavailable, use clearly labelled synthetic recipients and a non-sending preview for review; report actual sending as incomplete. Do not substitute an unapproved source of customer addresses.

If effort exceeds the time box, prioritise secure incident ownership and preservation of the FC workflow. Defer secondary screens and advanced automation; explicitly report deferred product requirements. Do not bypass access controls, dual approval, independent verification, or send-history correctness to meet the date.

## 13. Acceptance scenarios

1. A service engineer submits the reference incident without serial/version/parameters and receives an ID and responsible queue.
2. Software receives the report promptly; explicit acknowledgement records actor/time. A simulated unattended report triggers the configured reminder/escalation without duplicate alerts.
3. A proposed Firmware handoff exposes required context, retains the old accountable owner until acceptance, and records rejection/acceptance.
4. Approved baseline, flashed record, and actual read-back remain distinguishable, retain originals, and can be compared without claiming unverified device state.
5. A Software member can read Software issues, an unrelated Assembly member cannot retrieve them unless involved, and all designated heads can read the engineering issue/progress view.
6. Hidden records do not leak through direct IDs, nested APIs, file links, search/similarity, counts, notifications, cached dashboards, audit, or exports.
7. Resolving an issue does not verify it; the same person cannot independently verify. Failed verification returns it to investigation.
8. Existing FC lifecycle/rework history remains usable; general issue reporting does not require a dummy FC or stage.
9. A release cannot be announced until two distinct designated actors approve the current revision. Editing relevant content invalidates approvals.
10. An authorised sender previews selected recipients/message and sends once; repeat submission does not duplicate the campaign. Failed/unknown deliveries remain visible.
11. A task blocker and dated progress update appear to the relevant heads without overwriting earlier updates.
12. Core reporting/acknowledgement/update flows work at an Android-sized viewport and handle lost network/upload failure clearly.

## 14. Measurement

Capture submission-to-routing time, submission-to-human-acknowledgement time, overdue/unowned report count, handoff acceptance time, resolution/verification time, and repeated-issue links. Measure announcement attempts/failures separately from installations. Review pilot feedback on reporting friction and missing context.

Targets will be set after acknowledgement policy and pilot baseline are agreed. The five-day incident is the motivating example, not a measured company-wide baseline.

## 15. Decisions still needed

| Decision | Proposed owner |
| --- | --- |
| Named unknown-report coordinator, team heads, backups | Manager |
| Working days/holidays, severity definitions, acknowledgement/follow-up targets | Manager and team heads |
| After-hours duty contact and escalation channel | Manager |
| Exact FC, customer-sensitive-data, historical handoff, and daily-task visibility | Manager and team heads |
| Release approval order, absence/delegation, sender permission | Manager and Software head |
| Signup API contract and recipient eligibility | Product owner and Software head |
| Sending domain/provider and permitted download material | Software head and manager |
| Verification eligibility, exceptional closure and reopening authority | Team heads and manager |
| Hosting budget, backup owner, retention and restore objectives | Manager and technical owner |
| Final pilot feature cut and implementation authorisation | Product owner |

## 16. Development handoff

Claude Code and OpenAI Codex should use this PRD and repository `AGENTS.md` as shared context. Each work session should distinguish confirmed requirements from proposals, preserve unrelated work, and record changes and validation honestly. Approval to write this document is not approval to begin application implementation.
