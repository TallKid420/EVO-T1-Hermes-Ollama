#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_CONFIG_FILES = [
    "agents.yaml",
    "autonomy.yaml",
    "filesystem.yaml",
    "plugins.yaml",
    "policies.yaml",
    "services.yaml",
]

# Optional: tighten these once you define your schema.
# Example:
# REQUIRED_TOP_LEVEL_KEYS = {
#   "agents.yaml": ["agents"],
#   "plugins.yaml": ["plugins"],
# }
REQUIRED_TOP_LEVEL_KEYS: dict[str, list[str]] = {
    "agents.yaml": ["system_agents", "custom_agents"],
    "autonomy.yaml": ["autonomous_actions", "allowed_commands", "task_risks"],
    "filesystem.yaml": ["safe_paths", "restricted_paths"],
    "plugins.yaml": ["active", "plugins"],
    "policies.yaml": ["cooldowns", "limits", "circuit_breaker"],
    "services.yaml": ["daemon", "managed_services"],
}

@dataclass
class ValidationIssue:
    file: str
    message: str

def prompt_choice(message: str, choices: list[str], default: str | None = None) -> str:
    """
    Tries to use questionary if installed; falls back to basic input().
    """
    try:
        import questionary  # type: ignore
        return questionary.select(
            message,
            choices=choices,
            default=default or (choices[0] if choices else None),
        ).ask()
    except Exception:
        # Basic fallback
        print(message)
        for i, c in enumerate(choices, 1):
            d = " (default)" if default == c else ""
            print(f"  {i}. {c}{d}")
        while True:
            raw = input("> ").strip()
            if not raw and default:
                return default
            if raw.isdigit() and 1 <= int(raw) <= len(choices):
                return choices[int(raw) - 1]
            if raw in choices:
                return raw
            print("Invalid choice. Enter a number or one of the listed options.")

def prompt_confirm(message: str, default: bool = True) -> bool:
    try:
        import questionary  # type: ignore
        return bool(questionary.confirm(message, default=default).ask())
    except Exception:
        suffix = " [Y/n] " if default else " [y/N] "
        raw = input(message + suffix).strip().lower()
        if raw == "":
            return default
        return raw in ("y", "yes", "true", "1")

def load_yaml(path: Path) -> Any:
    """
    Uses ruamel.yaml if available (better for preserving comments), otherwise PyYAML.
    """
    try:
        from ruamel.yaml import YAML  # type: ignore
        yaml = YAML(typ="rt")
        with path.open("r", encoding="utf-8") as f:
            return yaml.load(f)
    except Exception:
        try:
            import yaml  # type: ignore
        except ImportError:
            print("Missing dependency: install either 'ruamel.yaml' or 'pyyaml'.")
            print("Try: pip install ruamel.yaml questionary")
            sys.exit(2)
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

def validate_yaml_file(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    name = path.name

    if not path.exists():
        return [ValidationIssue(name, "missing file")]

    try:
        data = load_yaml(path)
    except Exception as e:
        return [ValidationIssue(name, f"invalid YAML: {e}")]

    if not isinstance(data, dict):
        issues.append(ValidationIssue(name, "top-level YAML must be a mapping/object (dict)"))

    required_keys = REQUIRED_TOP_LEVEL_KEYS.get(name, [])
    if isinstance(data, dict) and required_keys:
        for k in required_keys:
            if k not in data:
                issues.append(ValidationIssue(name, f"missing required top-level key: '{k}'"))

    return issues

def backup_dir(dir_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = dir_path.parent / f"{dir_path.name}.backup_{ts}"
    shutil.copytree(dir_path, backup_path)
    return backup_path


def download_config_from_github(filename: str, dest_path: Path) -> bool:
    """
    Download a config file from the GitHub repository defaults.
    """
    github_url = f"https://raw.githubusercontent.com/TallKid420/EVO-T1-Hermes-Ollama/main/config/{filename}"
    
    try:
        print(f"Downloading {filename} from GitHub...")
        with urllib.request.urlopen(github_url) as response:
            content = response.read().decode('utf-8')
            
        dest_path.write_text(content, encoding='utf-8')
        print(f"Successfully downloaded {filename}")
        return True
        
    except urllib.error.HTTPError as e:
        print(f"Failed to download {filename}: HTTP {e.code}")
        return False
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        return False


def generate_default_configs(config_dir: Path) -> None:
    """
    Generate default config files by downloading them from GitHub.
    """
    print("Generating default configuration files...")
    
    for filename in REQUIRED_CONFIG_FILES:
        config_path = config_dir / filename
        if download_config_from_github(filename, config_path):
            print(f"Created {filename}")
        else:
            print(f"Failed to create {filename} - using minimal defaults")

def main() -> int:
    home = Path.home()
    config_dir = home / "config"

    print(f"Installer running as: {os.getlogin() if hasattr(os, 'getlogin') else 'user'}")
    print(f"Expected config directory: {config_dir}")

    if not config_dir.exists():
        print("No ~/config directory found.")
        if prompt_confirm("Create ~/config and generate fresh config files?", default=True):
            config_dir.mkdir(parents=True, exist_ok=True)
            generate_default_configs(config_dir)
            print("Created ~/config with default configuration files.")
            return 0
        return 1

    if not config_dir.is_dir():
        print("Error: ~/config exists but is not a directory.")
        return 1

    existing_files = {p.name for p in config_dir.iterdir() if p.is_file()}
    missing = [f for f in REQUIRED_CONFIG_FILES if f not in existing_files]

    issues: list[ValidationIssue] = []
    for fname in REQUIRED_CONFIG_FILES:
        issues.extend(validate_yaml_file(config_dir / fname))

    if missing:
        print("Missing required config files:")
        for f in missing:
            print(f"  - {f}")

    if issues:
        print("\nConfig validation issues found:")
        for iss in issues:
            print(f"  - {iss.file}: {iss.message}")

    if missing or issues:
        choice = prompt_choice(
            "Your ~/config is incomplete or invalid. What do you want to do?",
            choices=[
                "Backup ~/config then regenerate missing/invalid files",
                "Exit (do nothing)",
            ],
            default="Backup ~/config then regenerate missing/invalid files",
        )
        if choice.startswith("Backup"):
            backup_path = backup_dir(config_dir)
            print(f"Backed up existing config to: {backup_path}")
            # Regenerate missing/invalid files
            for fname in REQUIRED_CONFIG_FILES:
                config_path = config_dir / fname
                if not config_path.exists() or fname in [iss.file for iss in issues]:
                    download_config_from_github(fname, config_path)
            print("Regenerated missing/invalid config files.")
            return 0
        return 1

    # If we reach here, the required files exist and passed baseline validation.
    choice = prompt_choice(
        "Existing ~/config looks valid. Keep existing config?",
        choices=[
            "Keep as-is (recommended)",
            "Backup then modify/merge (interactive)",
            "Backup then overwrite with fresh defaults",
            "Exit",
        ],
        default="Keep as-is (recommended)",
    )

    if choice.startswith("Keep"):
        print("Keeping existing config.")
        # Create any NEW config files the project now needs (without touching existing ones)
        existing_files = {p.name for p in config_dir.iterdir() if p.is_file()}
        for fname in REQUIRED_CONFIG_FILES:
            if fname not in existing_files:
                config_path = config_dir / fname
                download_config_from_github(fname, config_path)
                print(f"Added new config file: {fname}")
        return 0

    if choice.startswith("Backup then modify/merge"):
        backup_path = backup_dir(config_dir)
        print(f"Backup created: {backup_path}")
        # For now, download fresh defaults (interactive merge not implemented)
        generate_default_configs(config_dir)
        print("Downloaded fresh defaults. (Interactive merge not implemented - manual merge required.)")
        return 0

    if choice.startswith("Backup then overwrite"):
        backup_path = backup_dir(config_dir)
        print(f"Backup created: {backup_path}")
        # Danger: wiping user config
        if prompt_confirm("Really overwrite ALL files in ~/config?", default=False):
            # Write fresh defaults for all REQUIRED_CONFIG_FILES
            generate_default_configs(config_dir)
            print("Overwrote config with fresh defaults.")
            return 0
        print("Cancelled overwrite.")
        return 1

    print("Exiting.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())