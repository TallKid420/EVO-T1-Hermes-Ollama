CREATE TABLE IF NOT EXISTS agent_nodes (
    agent_id TEXT PRIMARY KEY,
    parent_id TEXT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    spawn_depth INTEGER NOT NULL,
    mailbox_id TEXT,
    created_at TEXT NOT NULL
);