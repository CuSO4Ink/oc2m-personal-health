"""Run a dedicated demo. --fresh creates a new database; previous files are retained."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets

from app import create_app
from app.demo_data import seed_usability_demo, DEMO_ACCOUNTS, DEMO_PASSWORD

DEMO_ROOT = Path(__file__).resolve().parent / "instance" / "usability-demo"


def prepare_demo(fresh=False, demo_root=DEMO_ROOT):
    demo_root = Path(demo_root).resolve()
    demo_root.mkdir(parents=True, exist_ok=True)
    pointer = demo_root / "current.json"
    saved = json.loads(pointer.read_text(encoding="utf-8")) if pointer.exists() and not fresh else None
    if saved:
        database = (demo_root / saved["filename"]).resolve()
        if database.parent != demo_root or not database.is_file():
            raise ValueError("The saved demo is unavailable. Run with --fresh to create a new one.")
        secret = saved["session_secret"]
    else:
        name = datetime.now(timezone.utc).strftime("demo-%Y%m%d-%H%M%S-%f.db")
        database, secret = demo_root / name, secrets.token_hex(32)
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}", "SECRET_KEY":secret,
        "APP_ENV":"development","DEMO_FEATURES_ENABLED":True,"RESET_CODE_DELIVERY":"demo","DEMO_DATASET":database.stem})
    if not saved:
        with app.app_context(): seed_usability_demo()
        pointer.write_text(json.dumps({"filename":database.name,"session_secret":secret}),encoding="utf-8")
    else:
        # Enrich only the explicitly selected synthetic demo; retain personal data.
        with app.app_context():
            from app.demo_community_catalog import ensure_demo_community_catalog
            from app.demo_care_catalog import ensure_demo_care_catalog
            ensure_demo_community_catalog()
            ensure_demo_care_catalog()
    return app, database


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh",action="store_true",help="Start with clean demo data in a NEW database; retain every old database.")
    parser.add_argument("--prepare-only",action="store_true",help="Create/reuse the demo without starting a server.")
    parser.add_argument("--port",type=int,default=5001)
    args=parser.parse_args()
    app,path=prepare_demo(args.fresh)
    print(f"Demo database: {path}")
    for account in DEMO_ACCOUNTS: print(f"{account['title']}: {account['email']}")
    print(f"Demo password: {DEMO_PASSWORD}")
    if not args.prepare_only: app.run(host="127.0.0.1",port=args.port,debug=False)
