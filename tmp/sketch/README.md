# Personal Health Service System — MVP Sketch

An English-language classroom MVP for group **oc2m**. This directory contains a working implementation reference for the main project, including the frontend, backend APIs, database schema, migrations and workflow tests.

## Implemented scope

- Create, search and view health records.
- Edit your own records and retain earlier versions, with conflict detection for stale edits.
- Upload one PDF, PNG or JPG attachment per record (up to 5 MB).
- Preview and grant a selected doctor time-limited access to specific records.
- Revoke access and deny subsequent report and attachment requests.
- Record successful and denied access, edits and permission changes.
- Switch between demo patient and doctor identities.

The interface, sample records and server error messages are in English. Application dates use the `en-GB` locale.

## Quick start on Windows

1. Install **Node.js 22.13 or later**, including npm.
2. Open this directory and double-click **Start-MVP.cmd**.
3. The script installs dependencies if needed, builds the application and initialises the local database if it is absent.
4. When the server is ready, open **http://127.0.0.1:8787**.
5. Keep the terminal window open while demonstrating. Stop the running server before starting another copy on the same port.

The first dependency installation requires internet access. Local records and files persist under `.wrangler/state`; this directory is ignored by Git. A new clone has its own local data and does not receive the existing hosted site's records.

## Manual setup

Run these commands **inside `tmp/sketch`**, not at the repository root:

```sh
npm run install:ci
npm run build
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_massive_runaways.sql
npm run start -- --port 8787
```

Apply the initial SQL migration only once to a fresh local database. On subsequent launches, build and start without replaying it. `Start-MVP.cmd` performs the initial-table check automatically.

For frontend development after initial setup, use `npm run dev` and open the address printed by the development server. To test the complete built Worker with local storage, use the build/start flow above.

## Architecture

| Layer | Implementation |
| --- | --- |
| Frontend | React, TypeScript, Vinext and existing shadcn UI components |
| Backend | Cloudflare Worker API routes; session and authorisation checks |
| Structured storage | D1 / SQLite: records, versions, grants, logs and sessions |
| File storage | R2; attachments are retrieved through permission-checked API requests |

Vinext provides a Next.js-compatible development approach. This project is not a standard Next.js server deployment. The Cloudflare bindings require the supplied runtime or appropriate adapters for another hosting environment.

`.openai/hosting.json` declares only the logical `DB` and `BUCKET` bindings. The original private deployment identifier has deliberately been omitted from this shared copy. Running locally does not register or publish a site.

## Key files

| Path | Purpose |
| --- | --- |
| `app/health-app.tsx` | Records, sharing, history and demo-role interface |
| `app/globals.css` | Navy and teal theme and responsive layout |
| `app/api/[...path]/route.ts` | Record, attachment, permission, session and log endpoints |
| `lib/health-server.ts` | Server context, access checks, input validation and sample data |
| `db/schema.ts` | Drizzle schema for five core tables |
| `drizzle/` | Generated SQL migration and migration metadata |
| `tests/api-flow.mjs` | API workflow checks, including actual one-minute expiry |
| `DEMO.md` | English classroom demonstration sequence |

## APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET / POST | `/api/session` | Read or switch the demo session |
| GET / POST | `/api/records` | List visible records or create an owned record |
| GET / PATCH | `/api/records/:id` | Read a record or edit an owned record |
| GET / POST | `/api/records/:id/file` | Retrieve or upload an attachment |
| GET / POST / DELETE | `/api/grants` | List, grant or revoke permissions |
| GET | `/api/logs` | List activity visible to the current identity |

## Checks

With the local server running on port 8787:

```sh
node tests/api-flow.mjs
```

The script creates an isolated local test space and checks record creation, revisions, stale-edit rejection, uploads, ownership, doctor permissions, revocation, session persistence and real-time expiry. It waits for a one-minute permission to expire. It must not be run against a live site.

For TypeScript checking:

```sh
npx tsc --noEmit
```

Browser end-to-end tests are not included. Passing API checks does not by itself verify the browser layout or all interactions.

## Demo boundaries

- Role switching is a demonstration tool, not production patient or doctor authentication. Use sample information only.
- Hosted use relies on trusted platform identity. Independent deployment needs a verified identity/session mechanism; do not trust arbitrary client identity headers.
- A doctor may view authorised reports and retrieve their attachments, but may not edit records. Separate download permissions are not implemented.
- Revocation blocks future requests; it cannot recall copies already downloaded or captured.
- Permissions point to the current report version. An authorised doctor can see subsequent edits until permission ends.
- Regranting the same report to the same doctor replaces the previous unrevoked grant.
- The interface displays the latest 150 activity entries; older entries remain in the database.
- Source names are entered by users and are not proof of hospital verification.
- Real hospital integration, production accounts, SMS/facial verification, AI analysis, trends, appointments, patient communication and verified backup/restore procedures remain outside this MVP.

## Working together

Create a feature branch for your change and submit a pull request. Keep dependency changes aligned with `package-lock.json`. Do not commit `.env` files, credentials, `node_modules`, build output or local patient/demo data. Preserve schema migrations and add new migrations for future schema changes rather than replaying the initial migration against an existing database.
