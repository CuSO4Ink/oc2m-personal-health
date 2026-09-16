# Personal Health Service System

Full-stack implementation of the personal-facing subsystem for the Smart Medical and Elderly Care Big Data Public Service Platform.

## Technology stack

- Frontend: React 19, Vite 8, Ant Design 6, React Router and Axios
- Backend: Python 3.11+, Flask 3.1, Flask-Login and Flask-SQLAlchemy
- Database: SQLite for local development and the first demonstrable release
- Quality and deployment: Vitest, pytest, Docker, Nginx and GitHub Actions

The Figma prototype is the source of truth for screen layout and interaction. The legacy `tmp/sketch` directory is retained as a functional reference and is not the production application.

## Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The API runs at `http://127.0.0.1:5001`. Port 5001 avoids the macOS AirPlay Receiver conflict on port 5000.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The website runs at `http://127.0.0.1:5173` and proxies `/api` requests to Flask.

## Local test account

Run `python seed_demo.py` from `backend/` once, then sign in with:

- Email: `alex.morgan@example.com`
- Password: `HealthDemo2026!`

The account contains sample data only. The password-reset page displays its generated code in development until an email or SMS delivery service is connected.

## Implemented modules

- Account registration, session login, logout and development password reset
- Account-scoped health overview with refresh, pending alerts, overdue tasks, upcoming appointments and active sharing counts
- Latest measurements with collection time, source, missing-data and stale-data notices
- Recently updated records, expiring permissions, historical unusual access and working module shortcuts
- Health record search and filtering by keyword, type, source and date
- Self-reported record creation, editing and version history
- Read-only provider-synced records with source and sync provenance
- Ownership checks and optimistic version conflict protection in the API
- Blood pressure, blood glucose and heart-rate trend charts with time filters
- Validated manual reading entry with fixed units, source and collection time
- Versioned reference-threshold alerts with review status
- Data-sufficiency notices and traceable rule-based trend summaries
- Verified healthcare-recipient directory and fixed-record sharing permissions
- Permission preview, view/download controls, expiry and immediate revocation
- Account-isolated access activity with action, result, time, location and review flags
- Verified medical-service catalogue with live local appointment capacity
- Appointment review, confirmation, duplicate/full-slot checks and cancellation
- Personal health reminders with due-state tracking and completion
- Searchable elder-care information directory with source and update provenance
- Care appointment and task summaries on the health overview
- Optional Community profile with explicit on/off control
- Peer-circle membership, anonymous experience posts, likes and comments
- Community reporting workflow with health-record isolation and safety guidance
- Unified in-app notifications for health, care, sharing, security and community events
- Persistent unread state, category/status filters, search, mark-all-read and clear actions
- Global unread badge in the application header
- Account profile management with protected sign-in email changes
- Current-password-verified password changes that revoke other sessions
- Active-session management and account security activity history

Provider system integration, recipient identity-directory integration, correction requests, attachments, OCR, visit folders, clinically approved personalised risk reports, cross-system access enforcement, payments, online consultations, appointment rescheduling, live elder-care booking, private community messages, the moderator workbench, SMS/face authentication and external email/SMS/push delivery are planned for a later phase.
