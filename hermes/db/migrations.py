from datetime import datetime
from pathlib import Path

from hermes.db.conn import connect

# UPDATED PATH
MIGRATIONS_DIR = Path(__file__).resolve().parent / "db_migrations"


def load_migrations():
    migrations = []

    if not MIGRATIONS_DIR.exists():
        raise FileNotFoundError(f"Migrations dir not found: {MIGRATIONS_DIR}")

    for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        # expects format: 001_name.sql
        try:
            version = int(file.stem.split("_")[0])
        except ValueError:
            raise ValueError(f"Invalid migration filename: {file.name}")

        sql = file.read_text(encoding="utf-8")
        migrations.append((version, sql))

    return migrations


def migrate():
    conn = connect()
    try:
        # ensure migration tracking table exists
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );
        """)

        applied = {
            row["version"]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

        migrations = load_migrations()

        for version, sql in migrations:
            if version in applied:
                continue

            print(f"[migrate] applying v{version}")

            conn.executescript(sql)

            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (version, datetime.utcnow().isoformat()),
            )

            conn.commit()

        print("[migrate] complete")

    finally:
        conn.close()