# Hermes — EVO-T1 Autonomous Server AI

> An always-on, proactive, Jarvis-style AI supervisor running on a GMKtec EVO-T1 (Intel Core Ultra 9 285H · 64GB RAM · 3TB SSD · Ubuntu).  
> Hermes monitors the server, detects problems, plans responses, and acts — autonomously or with your approval — via Telegram.

---

## What It Does (Right Now)

Hermes runs as a background daemon (`hermesd.py`) that:

- **Watches** the server every 10 seconds for problems
  - Ollama API health (`/api/tags`)
  - Disk pressure (configurable warn/crit thresholds)
  - Memory pressure
  - Managed `systemd` service status
- **Deduplicates** repeated alerts (default: 5-minute cooldown)
- **Plans** a response using a local LLM (Gemma via Ollama) when an event fires
  - Rule-based action selection from an allowlist
  - LLM fallback if rules don't resolve
  - Risk scoring (1–10) with `requires_approval` flag for high-risk actions
- **Notifies** you via Telegram
- **Persists** events and actions to SQLite (`hermes.db`)

---

## Project Structure

```
EVO-T1-Hermes-Ollama/
├── hermesd.py                  # Entrypoint — starts the daemon
├── .env.example                # Copy to .env and fill in secrets
├── config/
│   ├── agents.yaml             # Planner LLM config + allowed actions + rules
│   ├── services.yaml           # Managed systemd services list
│   └── plugins.yaml            # Notification channels config (stub)
├── hermes/
│   ├── daemon/                 # HermesDaemon — main event loop
│   ├── watchers/               # OllamaHealth, DiskPressure, MemoryPressure, ServiceStatus
│   ├── planner/                # Planner agent (LLM-backed, rule-constrained)
│   ├── executor/               # Action execution layer
│   ├── db/                     # SQLite schema + migrations
│   ├── notifications/          # Telegram notifier (stubs for email/SMS)
│   ├── plugins/                # Plugin package (interface stub, not yet pluggable)
│   ├── provider/               # ChatProvider → OllamaChatProvider
│   ├── core/                   # SafetyManager
│   ├── cli/                    # CLI helpers
│   └── utils/                  # Logging, terminal handler
└── Hermes_arc/                 # Legacy/archive code (pre-refactor)
```

---

## Requirements

See `requirements.txt`. Key dependencies:

| Package | Purpose |
|---|---|
| `requests` | HTTP calls to Ollama API |
| `pyyaml` | Config file parsing |
| `python-dotenv` | `.env` secret loading |
| `psutil` | System metrics (memory, disk, processes) |
| `python-telegram-bot` | Telegram notifications |

---

## Setup

### 1. Prerequisites

```bash
# Ubuntu 22.04+
sudo apt update && sudo apt install -y python3 python3-pip python3-venv ollama
sudo systemctl enable --now ollama
```

Pull your planner model:

```bash
ollama pull gemma2:2b
```

### 2. Clone & Install

```bash
git clone https://github.com/TallKid420/EVO-T1-Hermes-Ollama.git
cd EVO-T1-Hermes-Ollama
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
nano .env
```

Fill in:

```env
TELEGRAM_TOKEN="your-bot-token"
TELEGRAM_CHAT_ID="your-chat-id"
```

Edit `config/services.yaml` to list the `systemd` services you want Hermes to watch:

```yaml
managed_services:
  - ollama
  - ssh
```

Edit `config/agents.yaml` to tune the planner model, timeout, allowed actions, and rules.

### 4. Run

```bash
python hermesd.py
```

Logs go to `hermes.log` and stdout.

### 5. Run as a systemd Service (Recommended)

```bash
sudo nano /etc/systemd/system/hermes.service
```

```ini
[Unit]
Description=Hermes AI Daemon
After=network.target ollama.service

[Service]
User=YOUR_USER
WorkingDirectory=/path/to/EVO-T1-Hermes-Ollama
ExecStart=/path/to/.venv/bin/python hermesd.py
Restart=always
RestartSec=10
EnvironmentFile=/path/to/EVO-T1-Hermes-Ollama/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes
sudo journalctl -u hermes -f
```

---

## Configuration Reference

### `config/agents.yaml`

```yaml
system_agents:
  planner:
    model: "gemma2:2b"          # Ollama model tag
    provider: "ollama"
    endpoint: "http://localhost:11434"
    timeout_seconds: 15
    allowed_actions:            # Executor will ONLY run these
      - restart_service
      - cleanup_cache
      - send_notification
      - delete_files
      - notify_user
    rules:
      - "If risk is high (e.g. deleting non-cache files), set requires_approval=true"
      - "Always respond in valid JSON only"
```

### `config/services.yaml`

```yaml
managed_services:
  - ollama
  - ssh
  # add any systemd unit name here
```

### `.env`

```env
TELEGRAM_TOKEN=""
TELEGRAM_CHAT_ID=""
```

---

## How the Planner Works

```
Event fires (e.g. "Ollama API returned 503")
        │
        ▼
Rule Layer: Is there a deterministic fix?
  YES → Execute from allowlist → Verify → Done
  NO  → LLM Planner gets: event, severity, system_status
              │
              ▼
        Returns: { action, reasoning, risk_score }
              │
        risk_score >= 8 → requires_approval=true → Telegram approval queue
        risk_score < 8  → Execute → Verify → Done
```

---

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the token into `.env` as `TELEGRAM_TOKEN`
3. Start your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`
4. Copy that into `.env` as `TELEGRAM_CHAT_ID`

---

## Known Limitations / In Progress

- Plugin system exists as a package but is not yet dynamically loadable (stub only)
- Email and SMS notifiers are stubs (`send()` raises `NotImplementedError`)
- Verifier agent (post-action health check) is planned but not yet implemented
- No approval queue UI yet — high-risk actions are flagged but not gated
- `Hermes_arc/` is legacy code from the pre-refactor version, kept for reference

---

---

# Roadmap & Phases

> ✅ = Done · 🔄 = In Progress · ⬜ = Not Started

---

## Phase 0 — Foundation & Safety Constraints ✅

| Item | Status |
|---|---|
| Daemon entrypoint (`hermesd.py`) | ✅ |
| SQLite DB + migrations (`hermes/db/`) | ✅ |
| Watcher framework (base class + 4 watchers) | ✅ |
| Ollama health watcher | ✅ |
| Disk pressure watcher | ✅ |
| Memory pressure watcher | ✅ |
| Service status watcher | ✅ |
| Event deduplication (cooldown window) | ✅ |
| Telegram notifier | ✅ |
| `.env` secret loading | ✅ |
| `config/agents.yaml` + `config/services.yaml` | ✅ |
| Allowed-actions allowlist in planner config | ✅ |
| SafetyManager (`hermes/core/`) | ✅ |
| Logging to file + stdout | ✅ |

---

## Phase 1 — Planner Agent (Rule-Based + LLM Fallback) 🔄

| Item | Status |
|---|---|
| Planner agent class (`hermes/planner/`) | ✅ |
| ChatProvider → OllamaChatProvider | ✅ |
| Structured JSON output from LLM | ✅ |
| Rule-based action selection (deterministic first) | ⬜ |
| LLM fallback when rules don't resolve | 🔄 |
| Risk scoring (1–10) | ✅ |
| `requires_approval` flag for high-risk actions | ✅ (flag exists, not gated yet) |
| Approval queue / gate | ⬜ |
| Planner unit tests | ⬜ |

---

## Phase 2 — Executor & Verifier 🔄

| Item | Status |
|---|---|
| Executor layer (`hermes/executor/`) | ✅ (basic) |
| `restart_service` action | ✅ |
| `cleanup_cache` action | ✅ |
| `send_notification` action | ✅ |
| `delete_files` action | ✅ |
| Verifier agent (rule-based health check post-action) | ⬜ |
| Ollama API health check in verifier | ⬜ |
| LLM fallback in verifier | ⬜ |
| Executor allowlist enforcement (hard block) | ⬜ |
| Action result persistence to DB | ⬜ |

---

## Phase 3 — Multi-Agent Architecture ⬜

| Item | Status |
|---|---|
| Agent registry / base class | ⬜ |
| SRE/Ops agent (service restarts, disk cleanup) | ⬜ |
| Research agent (web fetch, summarize) | ⬜ |
| Memory/Reporter agent (daily digest) | ⬜ |
| Verifier/Critic agent | ⬜ |
| Agent delegation protocol (Planner → sub-agent) | ⬜ |
| Per-agent permission profiles | ⬜ |
| Shared task object / job queue | ⬜ |

---

## Phase 4 — Plugin System ⬜

| Item | Status |
|---|---|
| `hermes/plugins/base.py` — `HermesPlugin` abstract class | ⬜ |
| `hermes/plugins/loader.py` — `PluginManager` with `importlib` | ⬜ |
| `config/plugins.yaml` as true plugin registry | ⬜ |
| Per-plugin permission boundary via `SafetyManager` | ⬜ |
| Example plugin (`echo_plugin.py`) | ⬜ |

---

## Phase 5 — Notifications & Channels ⬜

| Item | Status |
|---|---|
| Telegram (alerts + approval requests) | ✅ |
| Email notifier (stub → real) | ⬜ |
| SMS notifier (stub → real) | ⬜ |
| Approval queue via Telegram reply | ⬜ |
| Daily digest / summary report | ⬜ |

---

## Phase 6 — NeMo Guardrails Integration ⬜

| Item | Status |
|---|---|
| NeMo Guardrails installed + configured | ⬜ |
| Rails applied to Planner LLM output | ⬜ |
| Rails applied to sub-agent outputs | ⬜ |
| Custom colang rules for Hermes safety policies | ⬜ |

---

## Phase 7 — Hardening & Production ⬜

| Item | Status |
|---|---|
| `systemd` unit file | ⬜ |
| `requirements.txt` pinned versions | 🔄 |
| SSH hardening docs (key-only, firewall) | ⬜ |
| Ollama bound to localhost only | ⬜ |
| Hermes runs as dedicated low-privilege user | ⬜ |
| Log rotation | ⬜ |
| Health endpoint (HTTP) for external monitoring | ⬜ |
