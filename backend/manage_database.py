"""Backup or restore to a NEW file; never replace a running database.

Examples (stop the app before switching which file it uses):
  python manage_database.py backup --source instance/personal_health.db --destination backups/health.db
  python manage_database.py restore --source backups/health.db --destination instance/restored_health.db
Then configure DATABASE_URL to the restored file and restart the backend.
"""
import argparse

from app.schema import backup_sqlite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        result = backup_sqlite(args.source, args.destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Verified {args.operation}: {result}")
    if args.operation == "restore":
        print("The active database was not changed. Stop the backend, configure DATABASE_URL to this file, then restart.")


if __name__ == "__main__":
    main()
