import os
from dataclasses import dataclass
from typing import Callable

from groq import Groq
from hermes_operator import _COMPOUND_MODEL


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


SETTINGS_FIELDS = [
    SettingField("GROQ_API_KEY", "API Key", "", secret=True, required=True),
    SettingField("GROQ_MODEL", "Chat Model", "openai/gpt-oss-120b", normalizer=_normalize_non_empty),
    SettingField("GROQ_RPM_LIMIT", "RPM Limit", "20", normalizer=_normalize_rpm),
    SettingField("OPERATOR_COMPOUND_MODEL", "Compound Model", _COMPOUND_MODEL, normalizer=_normalize_non_empty),
    SettingField("OPERATOR_DEBUG", "Debug Mode", "1", normalizer=_normalize_debug),
]


def _get_field(key: str) -> SettingField:
    for field in SETTINGS_FIELDS:
        if field.key == key:
            return field
    raise KeyError(f"Unknown setting key: {key}")


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


def load_settings(env_path):
    raw_settings = _read_env_settings(env_path)
    loaded: dict[str, str] = {}
    for field in SETTINGS_FIELDS:
        try:
            loaded[field.key] = normalize_setting_value(field, raw_settings.get(field.key, field.default), strict_required=False)
        except ValueError:
            loaded[field.key] = field.default
    return loaded


def load_settings_with_validation(env_path: str, strict_required: bool = False) -> tuple[dict[str, str], list[str]]:
    raw_settings = _read_env_settings(env_path)
    validated: dict[str, str] = {}
    errors: list[str] = []

    for field in SETTINGS_FIELDS:
        raw_value = raw_settings.get(field.key, field.default)
        try:
            validated[field.key] = normalize_setting_value(field, raw_value, strict_required=strict_required)
        except ValueError as exc:
            errors.append(str(exc))
            validated[field.key] = field.default

    return validated, errors


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
    if key == "OPERATOR_COMPOUND_MODEL":
        operator_module._COMPOUND_MODEL = value
    if key == "OPERATOR_DEBUG":
        operator_module._debug = value == "1"


def reload_operator(env_path, operator_module, session):
    try:
        state = operator_module.setup(env_path)
        session["status"] = f"Operator reloaded ({state['model']})"
        return f"Operator reloaded. Model: {state['model']}"
    except Exception as exc:
        session["errors"] += 1
        session["status"] = f"Reload failed: {exc}"
        return f"Failed: {exc}"


def test_connection(settings):
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
    render_header("SETTINGS", "Edit values and apply changes instantly")

    from rich import box
    from rich.align import Align
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel

    table = Table(show_header=False, box=box.ROUNDED, border_style="bright_blue", padding=(0, 2))
    table.add_column(width=3)
    table.add_column(width=20)
    table.add_column(width=40)

    rows = [
        (field.label, mask_value(settings.get(field.key, ""), field.secret))
        for field in SETTINGS_FIELDS
    ]
    rows.extend(
        [
            ("Test Connection", "Validate current Groq API key"),
            ("Reload Operator", "Apply settings to running session"),
            ("Reset Defaults", "Reset model/rpm/compound defaults"),
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

    if field.key in {"GROQ_MODEL", "GROQ_RPM_LIMIT", "OPERATOR_COMPOUND_MODEL", "GROQ_API_KEY"}:
        reload_operator(env_path, operator_module, session)
    return f"Saved {field.label}."


def reset_defaults(env_path, default_model, default_rpm, operator_module, session):
    save_setting(env_path, "GROQ_MODEL", default_model, operator_module)
    save_setting(env_path, "GROQ_RPM_LIMIT", default_rpm, operator_module)
    save_setting(env_path, "OPERATOR_COMPOUND_MODEL", "groq/compound", operator_module)
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
    total_rows = len(SETTINGS_FIELDS) + 4

    while True:
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

        if sel < len(SETTINGS_FIELDS):
            status = prompt_setting(console, SETTINGS_FIELDS[sel], settings, env_path, operator_module, session)
            settings = load_settings(env_path)
        elif sel == len(SETTINGS_FIELDS):
            status = test_connection(settings)
        elif sel == len(SETTINGS_FIELDS) + 1:
            status = reload_operator(env_path, operator_module, session)
        elif sel == len(SETTINGS_FIELDS) + 2:
            status = reset_defaults(env_path, default_model, default_rpm, operator_module, session)
            settings = load_settings(env_path)
        else:
            return
