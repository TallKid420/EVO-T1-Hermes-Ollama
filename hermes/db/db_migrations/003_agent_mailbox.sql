-- agent-to-agent messaging system

CREATE TABLE IF NOT EXISTS agent_mailbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sender_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  priority INTEGER DEFAULT 5,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL
);