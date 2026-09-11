# Personal Health Service System: Architecture and Open-Source Technology Selection

Group: oc2m  
Compilation and research date: 11 September 2026  
Purpose: Group development discussions, course presentations and MVP implementation reference

## 1. Project Direction and Current Boundaries

The system uses a three-layer logical architecture: frontend interaction, backend business logic, and data and file storage. The first version focuses on a working workflow: add a report, grant a doctor access, let the doctor view it, record the access, revoke permission, and deny subsequent access.

The features, table structures, APIs and acceptance criteria in this document are design proposals. They do not mean that the corresponding features have already been implemented or have passed testing. The existing scaffold's dependency list confirms that React, TypeScript, Vinext, Drizzle, shadcn-related components, React Hook Form, Zod and Recharts, among others, have been declared. Declaring a dependency does not mean its functionality has been integrated. Development, deployment and testing progress must be reported according to the actual results of the main development task.

The near-term recommendation is to continue the current MVP rather than immediately replace its framework following this research. Standard Next.js or a React + Hono approach can be assessed later for long-term independent deployment. Open-source components reduce the work required for common functionality. Core business rules, including report ownership, permission expiry, revocation and access logging, remain the project's responsibility.

## 2. Users and Business Scope

| Role | Responsibilities and permissions | MVP boundary |
| --- | --- | --- |
| Patient | Manage personal records; select reports and doctors; grant and revoke access; view revision history and access logs | Core role |
| Doctor | Read reports and attachments covered by valid permissions | Use demo identities to verify the workflow; do not claim that real doctor identity verification is complete |
| Administrator | Maintain institution, service and platform administration information | A later module or a responsibility of another group |
| External hospital system | Supply medical records and examination results | Use simulated data for now; real interfaces remain to be confirmed |

The first version uses sample information only. Switching demo identities is a classroom testing tool, not a production login system. It should not be offered to real patients for handling real information.

### Feature Phases

| Phase | Features | Delivery goal |
| --- | --- | --- |
| MVP | Create, view and edit records; attachments; time-limited report-level permissions; revocation; revision history; access logs | Complete one end-to-end workflow for sharing records before a follow-up visit |
| Phase two | Indicator trends, reminders based on agreed rules, simulated hospital synchronisation, improved search | Demonstrate health changes and the data import process |
| Phase three | Appointment interfaces, production accounts, doctor identity verification, integration with administration functions | Align with real service boundaries |
| Optional extensions | AI-assisted analysis, patient communication, complex permission policies | Decide according to course requirements and available time |

AI models, SMS verification, facial verification and real hospital integration must not currently be listed as completed features.

## 3. Overall Technical Architecture

```text
Patient browser / Doctor browser
         | HTTPS requests
         v
Frontend: React + TypeScript + existing UI components
         | API
         v
Backend: sessions, records, permissions, logs, file access
         +-- D1 / SQLite: structured data
         +-- R2: report files
         +-- External adapters: hospitals, appointments, reminders (later)
```

The current scaffold uses Vinext and targets Cloudflare Workers. D1 and R2 are the proposed platform storage services; they are not GitHub libraries that the team must deploy entirely by itself.

The three layers describe a division of responsibilities. They do not require three independent services or three servers. The first version can be organised in one repository and one application. The backend receives frontend requests, verifies identity and permissions, and then accesses the database or object storage.

### Differences Between Deployment Options

| Option | Suitable circumstances | Recommendation for this project |
| --- | --- | --- |
| Existing Vinext + Workers + D1/R2 | Continue with the current scaffold for the course demonstration | Retain it for now and assess it through actual builds and workflow tests |
| Standard Next.js + Node.js + database/object storage | Long-term independent deployment using the standard Next.js toolchain | Prioritise it for later evaluation; do not copy D1 binding code directly into Node.js |
| React + Vite frontend with a Hono backend | A clearly separate API is needed, with a more explicit frontend/backend division | An alternative; deployment, same-origin policies, sessions and API integration require separate handling |

The official Vinext documentation states that it remains under active development, has gaps in Next.js compatibility, and is not a drop-in replacement for every application or production workload. Therefore, the presence of `next` in the dependency list does not make the current runtime a standard Next.js setup. [Official Vinext repository](https://github.com/cloudflare/vinext)

Standard Next.js is a framework for full-stack React applications. Hono is a backend framework based on Web standards, supporting environments including Workers and Node.js. The table above represents a project-specific technology assessment, not a completed migration decision. [Next.js](https://github.com/vercel/next.js), [Hono](https://github.com/honojs/hono)

## 4. Pages and Interaction Design

| Page or area | Main content | Actions and feedback |
| --- | --- | --- |
| Identity selector | Current demo patient or doctor | Clear the previous identity's report details and cached data when switching |
| Health records | Title, type, date, source and attachment status | Create records and open details; add filtering later |
| Report details | Content, attachment and current version | Edit personal records, retrieve attachments and view history |
| Permission settings | Report selection, doctor and validity period | Preview the scope before submission and display the outcome after success |
| Permission management | Active, revoked and expired permissions | Revoke access; let doctors verify that subsequent access is denied |
| Access history | Who acted, when, on which report, what action was taken and its result | Patients view activity relating to their own information |

Use a navy and teal theme, with usable layouts on both mobile and desktop. Every submission should provide in-progress, success and failure feedback. Preserve entered content on failure wherever possible. Empty lists should explain why they are empty, for example: “You have not been granted access to any reports.”

## 5. Database and File Design

### Five Core Data Categories

| Table | Key fields | Relationships and purpose |
| --- | --- | --- |
| records | id, tenant, owner, title, kind, date, source, summary, version, created, updated, attachment metadata | Current content of a health record |
| versions | id, record_id, tenant, version, title, summary, actor, created | Multiple content snapshots for each record |
| grants | id, tenant, owner, doctor, record_id, expires, created, revoked | Permission linking one report to one doctor |
| logs | id, tenant, owner, actor, record_id, title, action, result, created | Successful or denied access and other actions |
| sessions | id, tenant, actor, expires | Server-side demo sessions |

`tenant` identifies an isolated demo space, not the patient. Ownership and doctor permissions still need to be checked within that space. Users must not be able to choose their own tenant arbitrarily through request parameters.

Add `users`, identity verification and the necessary role information when implementing production accounts. If attachments are managed independently later, an `attachments` table can be added. A single-attachment MVP can initially store the metadata in `records`.

### Data Consistency

1. Save the first historical version when creating a record.
2. When editing, compare the submitted version number, then increment the version and save a snapshot. This prevents a stale page from overwriting newer content.
3. Where possible, perform related writes to records, versions and activity logs within a database transaction.
4. Use primary keys, foreign keys, necessary unique constraints and indexes based on actual query conditions. Do not add unnecessary freeze files or validation controls.
5. Define how repeated grants for the same doctor and report behave. Updating or replacing the existing grant is recommended. After revocation, check whether another valid grant remains, so the interface and actual permissions do not contradict each other.

### Attachment Handling

The database stores the filename, object key, type, size and associated record. Object storage holds the file contents. Restrict file types and sizes during upload; do not trust the extension alone. Attachment retrieval must pass through backend authorisation before returning the content. Avoid long-lived public URLs that could bypass revocation.

The database and object storage cannot simply be treated as one transaction. If the file is written successfully but the record cannot be saved, clean up the orphaned file created by that operation and return a clear error to the user.

## 6. Identity, Permissions and Privacy

For every report or attachment read, check the following in order: valid identity, demo space, record ownership or doctor permission, permission scope, revocation status and validity period. Hiding buttons in the frontend is insufficient for enforcing authorisation.

The MVP may allow a doctor to read report content and attachments during the permission period while prohibiting edits. Configuring viewing, editing and downloading separately is an extension of the full design and must not be described as an already implemented capability.

Distinguish between two time-related concepts:

- Record date range: which period's reports may be shared, for example reports from the last three months.
- Permission validity period: when the doctor may access them, for example for two days from now.

The MVP should prioritise explicit record ID selection to prevent permissions from automatically expanding to reports added in the future. Revocation blocks subsequent access through the system, but cannot recall copies the doctor has already downloaded. Clear old cached data when switching identities in the frontend. Cached data must never be the basis for an authorisation decision.

A hosted environment can use identity information supplied by a trusted platform. An independently deployed application must not directly trust identity headers supplied by the client. Establish the user context through a production session mechanism or verified identity credentials.

## 7. Proposed API Design

| Method | Path | Function |
| --- | --- | --- |
| GET / POST | /api/session | Query or establish a demo session |
| GET / POST | /api/records | List records visible to the current identity; create a personal record |
| GET / PATCH | /api/records/{id} | Read details; update a personal record |
| GET / POST | /api/records/{id}/file | Retrieve an attachment with access checks; upload an attachment to a personal report |
| GET / POST / DELETE | /api/grants | Query, create and revoke permissions |
| GET | /api/logs | Query activity the current identity is permitted to view |

Validate inputs again on the server. Return consistent, understandable errors: 400 for invalid input, 401 for missing valid identity, 403 for insufficient permission, 404 for a missing resource, 409 for version or business conflicts, 413 for an oversized file, and 503 for temporary service unavailability.

At this stage, maintaining API documentation is sufficient. Add an OpenAPI description when multiple groups need to collaborate or a generated client is needed, rather than allowing documentation work to replace actual API integration testing.

## 8. Research into GitHub Frameworks and Libraries

The following tables draw on official repository READMEs, documentation entry points and public project descriptions. Priorities and integration costs are assessments for this project. Star counts alone are not used to judge maturity, and compatibility between arbitrary version combinations is not guaranteed. This is a candidate list, not a list of packages that must all be installed.

### 8.1 Frameworks and General Foundations

| Project | Official GitHub repository | Purpose | Suitability and cost |
| --- | --- | --- | --- |
| Next.js | https://github.com/vercel/next.js | Full-stack React framework, routing and server-side capabilities | Established framework candidate; evaluate for independent deployment. Medium to high migration cost |
| Hono | https://github.com/honojs/hono | Backend routing, middleware and APIs across runtimes | Candidate for a separate backend; no need to add another routing layer to the current setup. Medium cost |
| Vinext | https://github.com/cloudflare/vinext | Implements Next.js APIs on Vite, targeting environments including Workers | Current scaffold approach; has compatibility limitations and should not be classified as an unconditionally mature replacement |
| Drizzle ORM / Kit | https://github.com/drizzle-team/drizzle-orm | TypeScript schemas, database access and SQL migrations | Already declared; prioritise reuse. Current D1 business queries can continue using parameterised SQL. Low to medium cost |
| shadcn/ui | https://github.com/shadcn-ui/ui | Editable, customisable UI component source code | Reuse existing buttons, dialogs, tabs and form components with a consistent theme. Low cost |

Drizzle officially supports databases and environments including SQLite and D1. It is suitable for maintaining a typed schema and generating migrations. shadcn/ui supplies component code that developers can modify; installing it does not provide a complete health service application. [Drizzle](https://github.com/drizzle-team/drizzle-orm), [shadcn/ui](https://github.com/shadcn-ui/ui)

### 8.2 Libraries Supporting Product Features

| Project | Official GitHub repository | Use in this project | Adoption order and considerations |
| --- | --- | --- | --- |
| React Hook Form | https://github.com/react-hook-form/react-hook-form | Form state and error messages for creating and editing reports and configuring permissions | Prioritise the existing dependency; low cost. Form validation cannot replace backend validation |
| Zod | https://github.com/colinhacks/zod | Validate request data such as titles, dates, types and permission durations | High priority; the declared dependency is in the 3.x series. Use the matching API rather than copying examples from another major version |
| TanStack Query | https://github.com/TanStack/query | Asynchronous loading and refreshing of reports, permissions and activity lists | Add when requests across multiple pages become complex. Clear caches on identity changes and refresh relevant queries after permission changes |
| Recharts | https://github.com/recharts/recharts | Time-series charts for indicators such as blood pressure and blood glucose | Already declared; use in phase two. Establish structured indicator data before building charts |
| PDF.js | https://github.com/mozilla/pdf.js | View report PDFs in the browser | Optional later; controlled downloading is enough for the first version. It is not OCR and does not enforce access permissions |

React Hook Form supports integration with validation libraries such as Zod. Zod parses and validates data at runtime. TanStack Query handles fetching, caching and updating server state; it is not a database. [React Hook Form](https://github.com/react-hook-form/react-hook-form), [Zod](https://github.com/colinhacks/zod), [TanStack Query](https://github.com/TanStack/query)

Recharts is a React charting library, while PDF.js is a JavaScript PDF reader. Both address presentation needs. Neither automatically generates trustworthy health assessments or replaces backend report authorisation. [Recharts](https://github.com/recharts/recharts), [PDF.js](https://github.com/mozilla/pdf.js)

### 8.3 Integration and Testing

| Project | Official GitHub repository | Use in this project | Adoption approach |
| --- | --- | --- | --- |
| MSW | https://github.com/mswjs/msw | Simulate hospital responses, error states, delays and appointment results | Use during development and testing. The main classroom workflow should still call the real backend and database |
| Vitest | https://github.com/vitest-dev/vitest | Test pure logic, date rules and permission decisions | Introduce as needed for specific rules. D1/R2 behaviour also requires testing in the appropriate runtime |
| Playwright | https://github.com/microsoft/playwright | Complete patient and doctor workflows in the browser | Once the core APIs work, a small number of key end-to-end tests is sufficient |

MSW provides network request mocking, Vitest is a Vite-based test framework, and Playwright supports browser testing with Chromium, Firefox and WebKit. Each has a different role. Mocking every API to return success does not prove that real authorisation and persistence work. [MSW](https://github.com/mswjs/msw), [Vitest](https://github.com/vitest-dev/vitest), [Playwright](https://github.com/microsoft/playwright)

### 8.4 Production Identity and Healthcare Standards

| Project | Official GitHub repository | Purpose | Recommendation for this project |
| --- | --- | --- | --- |
| Better Auth | https://github.com/better-auth/better-auth | TypeScript authentication framework | Evaluate after deciding on independent deployment and production account requirements. Do not add a second authentication system alongside the current hosted identity approach. Medium to high cost |
| Medplum | https://github.com/medplum/medplum | Healthcare application platform, APIs, React components and related capabilities | A reference for later healthcare data modelling and interoperability work. It is not a lightweight library that can be integrated by changing a few lines. High cost |

Better Auth provides authentication foundations, but the project must still implement per-report authorisation rules. Medplum is a complete healthcare application platform. Adopting its components or services does not automatically complete hospital integration, clinical validation or compliance work. [Better Auth](https://github.com/better-auth/better-auth), [Medplum](https://github.com/medplum/medplum)

## 9. Recommended Stack and Adoption Order

### Near-Term Classroom MVP

Retain the current React + TypeScript + Vinext scaffold and the D1/R2 storage direction. Reuse shadcn-related components for the interface, the existing React Hook Form + Zod dependencies for forms, and Drizzle for schemas and migrations. First implement real APIs for reports, permissions, attachments and logs, then connect the pages.

Reuse the locked versions of existing dependencies instead of upgrading packages in bulk for this demonstration. Before adding a library, check its runtime requirements, the documentation for the relevant major version, and its LICENSE. Use official repositories and package names.

### As Features Expand

1. Introduce TanStack Query when request and cache handling becomes noticeably repetitive across pages.
2. Use Recharts for trends once concrete, structured simulated indicator data is available.
3. Introduce MSW to simulate external dependencies when hospital or appointment integration is needed.
4. Use Playwright to verify complete browser interactions once the core workflow runs.
5. Assess PDF.js when users have a demonstrated need to read attachments online.

### Long-Term Direction

Compare standard Next.js with React + Hono when independent deployment, production accounts or broader compatibility is required. Before migrating, separate business functions, database access and file storage interfaces. Do not introduce microservices, message queues, complex rule engines or a complete healthcare platform prematurely.

## 10. Minimum Acceptance Checklist

| Scenario | Expected result |
| --- | --- |
| Refresh or return after adding a report | The record still exists |
| Edit a report | The current version is updated and historical content is retained |
| Two pages submit the same old version | The later submission receives a conflict message and does not overwrite newer data |
| Patient A requests patient B's report | The backend denies access without disclosing the report content or attachment |
| An unauthorised doctor requests a report | The backend denies access and records the denial according to the defined rules |
| Selected reports are shared with a designated doctor | That doctor can read the selected reports but not other reports |
| A new request is made after revocation or expiry | Further access to both content and attachments is denied |
| Repeated permission grants are followed by revocation | Defined rules are applied; the system must not appear to revoke access while another grant remains effective |
| File upload fails | An error is shown; an attachment that was not saved successfully is not presented as successful |
| The user switches identity | Cached details from the previous identity are not displayed |

These are acceptance tests to be performed, not statements that testing has passed. At delivery, record the actual test dates, results and any scenarios that have not passed.

## 11. Suggested Group Work Allocation

The six members can divide responsibilities by deliverable. The group should confirm the assignment of named individuals:

1. Pages and interactions: record lists, details, forms and status feedback.
2. Records and versions: database structure, record reads and writes, historical snapshots.
3. Permissions and sessions: patient/doctor boundaries, validity periods and revocation.
4. Attachments and external data: uploads, retrieval and simulated hospital interfaces.
5. Integration and testing: core workflows, cross-user access, expiry and revocation.
6. Project integration and reporting: API documentation, running instructions, demonstration scripts and progress records.

At each integration step, prioritise demonstrating a working business workflow. Record code completion, successful API calls, completed page interactions and passed tests as separate milestones.

## 12. Example Classroom Explanation

We divide the system into three layers: frontend interaction, backend business logic and data storage. The first version focuses on health reports, doctor permissions and access logs. We have designed five data categories: records, revision history, permissions, logs and sessions. Our technical approach prioritises existing components and database tools, while the backend enforces permission checks. The next acceptance priority is to upload a report, grant a doctor access, and deny further access after permission is revoked or expires. We have carried out targeted research into frameworks and feature libraries, and will report development progress based on actual running software and test results.
