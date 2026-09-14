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

The API runs at `http://127.0.0.1:5000`.

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
- Health overview with recent records loaded from the API
- Health record search and filtering by keyword, type, source and date
- Self-reported record creation, editing and version history
- Read-only provider-synced records with source and sync provenance
- Ownership checks and optimistic version conflict protection in the API

Provider system integration, correction requests, attachments, OCR and visit folders are represented in the interface and planned for a later phase.
