import os
import sqlite3


def get_db_path() -> str:
    return os.environ.get("HERMES_DB_PATH", "hermes.sqlite3")


def connect():
    path = get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn