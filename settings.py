import json
import os
from dataclasses import dataclass
from typing import Callable
from urllib import error, request

from groq import Groq


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    default: str
    secret: bool = False
    required: bool = False
    normalizer: Callable[[str], str] | None = None


def _normalize_non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be empty")
    return normalized


def _normalize_rpm(value: str) -> str:
    normalized = value.strip()
    rpm = float(normalized)
    if rpm <= 0:
        raise ValueError("must be a positive number")
    return str(rpm)


def _normalize_debug(value: str) -> str:
    normalized = value.strip().lower()
    truthy = {"1", "true", "on"}
    falsy = {"0", "false", "off"}
    if normalized in truthy:
        return "1"
    if normalized in falsy:
        return "0"
    raise ValueError("must be 0/1, true/false, or on/off")


def _normalize_provider(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"groq", "ollama"}:
        return normalized
    raise ValueError("must be groq or ollama")


DEFAULT_PROVIDER = "groq"
PROVIDER_DEFAULTS = {
    "groq": {
        "model_key": "GROQ_MODEL",
        "rpm_key": "GROQ_RPM_LIMIT",
        "default_model": "openai/gpt-oss-120b",
        "default_rpm": "20",
    },
    "ollama": {
        "model_key": "OLLAMA_MODEL",
        "rpm_key": "OLLAMA_RPM_LIMIT",
        "default_model": "qwen3",
        "default_rpm": "20",
    },
}
PROVIDER_FIELD_KEYS = {
    "groq": ["GROQ_API_KEY", "GROQ_MODEL", "GROQ_RPM_LIMIT"],
    "ollama": ["OLLAMA_HOST", "OLLAMA_MODEL", "OLLAMA_RPM_LIMIT"],
}
COMMON_FIELD_KEYS = ["LLM_PROVIDER", "OPERATOR_DEBUG"]


SETTINGS_FIELDS = [
    SettingField("LLM_PROVIDER", "LLM Provider", DEFAULT_PROVIDER, normalizer=_normalize_provider),
    SettingField("OPERATOR_DEBUG", "Debug Mode", "1", normalizer=_normalize_debug),
    SettingField("GROQ_API_KEY", "API Key", "", secret=True, required=True),
    SettingField("GROQ_MODEL", "Chat Model", "openai/gpt-oss-120b", normalizer=_normalize_non_empty),
    SettingField("GROQ_RPM_LIMIT", "RPM Limit", "20", normalizer=_normalize_rpm),
    SettingField("OLLAMA_HOST", "Ollama Host", "http://localhost:11434", normalizer=_normalize_non_empty),
    SettingField("OLLAMA_MODEL", "Ollama Model", "qwen3", normalizer=_normalize_non_empty),
    SettingField("OLLAMA_RPM_LIMIT", "Ollama RPM Limit", "20", normalizer=_normalize_rpm),
]


def _get_field(key: str) -> SettingField:
    for field in SETTINGS_FIELDS:
        if field.key == key:
            return field
    raise KeyError(f"Unknown setting key: {key}")


def get_provider(settings: dict[str, str] | None = None) -> str:
    field = _get_field("LLM_PROVIDER")
    raw_value = (settings or {}).get(field.key, field.default)
    try:
        return normalize_setting_value(field, raw_value, strict_required=False)
    except ValueError:
        return DEFAULT_PROVIDER


def get_provider_defaults(provider: str) -> dict[str, str]:
    return dict(PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS[DEFAULT_PROVIDER]))


def get_active_fields(settings: dict[str, str] | None = None) -> list[SettingField]:
    provider = get_provider(settings)
    keys = COMMON_FIELD_KEYS + PROVIDER_FIELD_KEYS.get(provider, PROVIDER_FIELD_KEYS[DEFAULT_PROVIDER])
    return [_get_field(key) for key in keys]


def get_provider_runtime_summary(settings: dict[str, str]) -> dict[str, str]:
    provider = get_provider(settings)
    defaults = get_provider_defaults(provider)
    return {
        "provider": provider,
        "model": settings.get(defaults["model_key"], defaults["default_model"]),
        "rpm": settings.get(defaults["rpm_key"], defaults["default_rpm"]),
    }


def normalize_setting_value(field: SettingField, value: str, strict_required: bool = False) -> str:
    raw = (value or "").strip()

    if not raw:
        if strict_required and field.required:
            raise ValueError(f"{field.label} is required")
        return field.default

    if field.normalizer:
        try:
            return field.normalizer(raw)
        except ValueError as exc:
            raise ValueError(f"{field.label} {exc}") from exc
    return raw


def _read_env_settings(env_path: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip().strip('"').strip("'")
    return settings


def _validate_settings(raw_settings: dict[str, str], strict_required: bool) -> tuple[dict[str, str], list[str]]:
    validated: dict[str, str] = {}
    errors: list[str] = []

    provider_field = _get_field("LLM_PROVIDER")
    try:
        validated[provider_field.key] = normalize_setting_value(
            provider_field,
            raw_settings.get(provider_field.key, provider_field.default),
            strict_required=False,
        )
    except ValueError as exc:
        errors.append(str(exc))
        validated[provider_field.key] = provider_field.default

    active_field_keys = {field.key for field in get_active_fields(validated)}
    for field in SETTINGS_FIELDS:
        if field.key == provider_field.key:
            continue

        raw_value = raw_settings.get(field.key, field.default)
        should_strict = strict_required and field.key in active_field_keys
        try:
            validated[field.key] = normalize_setting_value(field, raw_value, strict_required=should_strict)
        except ValueError as exc:
            if field.key in active_field_keys:
                errors.append(str(exc))
            validated[field.key] = field.default

    return validated, errors


def load_settings(env_path):
    loaded, _ = _validate_settings(_read_env_settings(env_path), strict_required=False)
    return loaded


def load_settings_with_validation(env_path: str, strict_required: bool = False) -> tuple[dict[str, str], list[str]]:
    return _validate_settings(_read_env_settings(env_path), strict_required=strict_required)


def save_setting(env_path, key, value, operator_module):
    field = _get_field(key)
    value = normalize_setting_value(field, value, strict_required=field.required)

    lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as env_file:
            lines = env_file.readlines()

    entry = f"{key}={value}\n"
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[index] = entry
            replaced = True
            break

    if not replaced:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(entry)

    with open(env_path, "w", encoding="utf-8") as env_file:
        env_file.writelines(lines)

    os.environ[key] = value


def reload_operator(env_path, operator_module, session):
    try:
        state = operator_module.setup(env_path)
        provider = state.get("provider", get_provider(load_settings(env_path)))
        model = state.get("model", "")
        session["status"] = f"Operator reloaded ({provider}: {model})"
        return f"Operator reloaded. Provider: {provider}  Model: {model}"
    except Exception as exc:
        session["errors"] += 1
        session["status"] = f"Reload failed: {exc}"
        return f"Failed: {exc}"


def test_connection(settings):
    provider = get_provider(settings)
    if provider == "groq":
        api_key = settings.get("GROQ_API_KEY", "").strip()
        if not api_key:
            return "Failed: GROQ_API_KEY is not set."

        try:
            client = Groq(api_key=api_key)
            models = client.models.list()
            model_count = len(getattr(models, "data", []) or [])
            return f"Connected to Groq successfully. {model_count} model(s) available."
        except Exception as exc:
            return f"Failed: {exc}"

    host = settings.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        with request.urlopen(f"{host}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model_count = len(payload.get("models", []) or [])
        return f"Connected to Ollama successfully. {model_count} model(s) available."
    except error.URLError as exc:
        return f"Failed: {exc.reason}"
    except Exception as exc:
        return f"Failed: {exc}"


def mask_value(value, secret=False):
    if not value:
        return "[dim]Not set[/dim]"
    if not secret:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def render_settings_menu(console, render_header, sel, settings, status=None):
    console.clear()
    provider = get_provider(settings)
    render_header("SETTINGS", f"Edit {provider} and operator values")

    from rich import box
    from rich.align import Align
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel

    table = Table(show_header=False, box=box.ROUNDED, border_style="bright_blue", padding=(0, 2))
    table.add_column(width=3)
    table.add_column(width=20)
    table.add_column(width=40)

    active_fields = get_active_fields(settings)
    rows = [
        (field.label, mask_value(settings.get(field.key, ""), field.secret))
        for field in active_fields
    ]
    rows.extend(
        [
            ("Test Connection", f"Validate current {provider} configuration"),
            ("Reload Operator", "Apply settings to running session"),
            ("Reset Defaults", f"Reset {provider} model/rpm defaults"),
            ("Back", "Return to main menu"),
        ]
    )

    for index, (label, value) in enumerate(rows):
        selected = index == sel
        arrow = Text("▶" if selected else " ", style="bold yellow" if selected else "white")
        label_style = "bold yellow on dark_blue" if selected else "bold white"
        value_style = "white on dark_blue" if selected else "dim white"
        table.add_row(arrow, Text(label, style=label_style), Text(str(value), style=value_style))

    console.print(Align.center(table))
    console.print(Align.center(Text("\n↑ ↓ Navigate   Enter Edit/Run", style="dim")))
    if status:
        color = "magenta" if status.startswith("Failed") else "green"
        console.print(Panel(status, border_style=color))


def prompt_setting(console, field: SettingField, settings, env_path, operator_module, session):
    from rich.panel import Panel

    current = settings.get(field.key, "")
    console.clear()
    console.print(Panel(f"[bold cyan]{field.label}[/bold cyan]", style="cyan"))
    console.print(f"Current value: {mask_value(current, field.secret)}")
    console.print("[dim]Leave blank to keep the current value.[/dim]")

    new_value = console.input("[bold yellow]New value > [/bold yellow]").strip()
    if not new_value:
        return "No changes saved."

    try:
        save_setting(env_path, field.key, new_value, operator_module)
    except ValueError as exc:
        return f"Failed: {exc}"

    reload_status = reload_operator(env_path, operator_module, session)
    if reload_status.startswith("Failed"):
        return reload_status
    return f"Saved {field.label}. {reload_status}"


def reset_defaults(env_path, settings, operator_module, session):
    provider = get_provider(settings)
    defaults = get_provider_defaults(provider)
    save_setting(env_path, defaults["model_key"], defaults["default_model"], operator_module)
    save_setting(env_path, defaults["rpm_key"], defaults["default_rpm"], operator_module)
    return reload_operator(env_path, operator_module, session)


def run_settings(
    console,
    read_key,
    render_header,
    env_path,
    operator_module,
    session,
    default_model,
    default_rpm,
):
    settings = load_settings(env_path)
    sel = 0
    status = "Edit values here. Changes are saved to .env immediately."

    while True:
        active_fields = get_active_fields(settings)
        total_rows = len(active_fields) + 4
        sel = min(sel, total_rows - 1)
        render_settings_menu(console, render_header, sel, settings, status)
        try:
            key = read_key()
        except KeyboardInterrupt:
            return

        if key == "UP":
            sel = (sel - 1) % total_rows
            continue
        if key == "DOWN":
            sel = (sel + 1) % total_rows
            continue
        if key != "ENTER":
            continue

        if sel < len(active_fields):
            status = prompt_setting(console, active_fields[sel], settings, env_path, operator_module, session)
            settings = load_settings(env_path)
        elif sel == len(active_fields):
            status = test_connection(settings)
        elif sel == len(active_fields) + 1:
            status = reload_operator(env_path, operator_module, session)
        elif sel == len(active_fields) + 2:
            status = reset_defaults(env_path, settings, operator_module, session)
            settings = load_settings(env_path)
        else:
            return
