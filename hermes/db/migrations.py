from datetime import datetime
from hermes.db.conn import connect

MIGRATIONS = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          severity TEXT NOT NULL,
          source TEXT NOT NULL,
          type TEXT NOT NULL,
          message TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          acknowledged_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
        CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);

        CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          status TEXT NOT NULL,
          priority INTEGER NOT NULL,
          type TEXT NOT NULL,
          title TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          result_json TEXT,
          event_id INTEGER,
          requires_approval INTEGER NOT NULL DEFAULT 0,
          approved_at TEXT,
          blocked_reason TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);

        CREATE TABLE IF NOT EXISTS actions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          task_id INTEGER,
          tool TEXT NOT NULL,
          action TEXT NOT NULL,
          input_json TEXT NOT NULL,
          output_json TEXT,
          success INTEGER NOT NULL,
          duration_ms INTEGER,
          error TEXT,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_actions_task_id ON actions(task_id);
        CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions(created_at);
        """,
    )
]


def migrate():
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );
            """
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (version, datetime.utcnow().isoformat()),
            )
            conn.commit()
    finally:
        conn.close()