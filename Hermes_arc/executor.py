from datetime import datetime, date
from urllib import request, error, parse
import pytz
import math
import hashlib
import uuid
import random
import base64
import os
import sys
import platform
import shutil
import subprocess
import re
import json
import time


def _expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _is_protected_path(path: str) -> bool:
    """Prevent dangerous operations on critical roots/directories."""
    p = _expand_path(path)
    drive = os.path.splitdrive(p)[0]
    protected_exact = {
        p.lower() for p in {
            os.path.abspath(os.sep),
            os.path.abspath(os.getcwd()),
            os.path.abspath(os.path.expanduser("~")),
            os.path.abspath(os.path.join(os.path.expanduser("~"), "Downloads")),
        }
    }
    if drive:
        protected_exact.add((drive + "\\").lower())

    pl = p.lower()
    if pl in protected_exact:
        return True

    protected_markers = (
        "\\windows",
        "\\program files",
        "\\program files (x86)",
        "\\programdata",
        "\\appdata\\local\\programs",
    )
    if sys.platform == "win32" and any(marker in pl for marker in protected_markers):
        return True

    unix_markers = (
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/usr/local/bin",
        "/etc",
        "/root",
        "/boot",
        "/sys",
        "/proc",
        "/dev",
        "/var/log",
    )
    if sys.platform != "win32" and any(marker in pl for marker in unix_markers):
        return True

    return False


def _normalize_shell_command(command: str) -> str:
    """Strip shell wrappers when running on Windows."""
    cmd = command.strip()
    if sys.platform == "win32":
        cmd = re.sub(r"^powershell(\.exe)?\s+-NoProfile\s+-NonInteractive\s+-Command\s+", "", cmd, flags=re.IGNORECASE)
        cmd = re.sub(r"^powershell(\.exe)?\s+-Command\s+", "", cmd, flags=re.IGNORECASE)
    return cmd


# ── Time ────────────────────────────────────────────────────────────────────

def get_time(timezone=None):
    timezone = timezone or "EDT"
    try:
        time = datetime.now(pytz.timezone(timezone)).isoformat(timespec="seconds")
    except pytz.UnknownTimeZoneError:
        return {"error": f"Unknown timezone: {timezone}"}
    return {"timezone": timezone, "time": time}


def get_current_weather(location: str, unit: str = "f"):
    """Get current weather for a location using wttr.in JSON API."""
    loc = str(location).strip()
    if not loc:
        return {"error": "location is required"}

    unit_l = str(unit or "f").strip().lower()
    if unit_l not in {"c", "f"}:
        return {"error": "unit must be 'c' or 'f'"}

    try:
        encoded = parse.quote(loc)
        url = f"https://wttr.in/{encoded}?format=j1"
        req = request.Request(url=url, method="GET", headers={"User-Agent": "Hermes/2.0"})
        with request.urlopen(req, timeout=20) as resp:  # noqa: S310
            raw = resp.read(250000).decode("utf-8", errors="replace")
            data = json.loads(raw)

        current = (data.get("current_condition") or [{}])[0]
        area = (data.get("nearest_area") or [{}])[0]
        area_name = ((area.get("areaName") or [{"value": loc}])[0]).get("value", loc)
        region_name = ((area.get("region") or [{"value": ""}])[0]).get("value", "")
        country_name = ((area.get("country") or [{"value": ""}])[0]).get("value", "")

        if unit_l == "c":
            temperature = current.get("temp_C")
            feels_like = current.get("FeelsLikeC")
            temp_unit = "C"
        else:
            temperature = current.get("temp_F")
            feels_like = current.get("FeelsLikeF")
            temp_unit = "F"

        return {
            "location": {
                "query": loc,
                "area": area_name,
                "region": region_name,
                "country": country_name,
            },
            "temperature": temperature,
            "feels_like": feels_like,
            "temperature_unit": temp_unit,
            "condition": ((current.get("weatherDesc") or [{"value": ""}])[0]).get("value", ""),
            "humidity": current.get("humidity"),
            "wind_kph": current.get("windspeedKmph"),
            "wind_mph": current.get("windspeedMiles"),
            "observation_time_utc": current.get("observation_time"),
            "source": "wttr.in",
        }
    except error.HTTPError as e:
        return {"error": f"Weather request failed with HTTP {e.code}"}
    except Exception as e:
        return {"error": f"Weather lookup failed: {e}"}


def days_between(date1: str, date2: str):
    """Return the number of days between two ISO dates (YYYY-MM-DD)."""
    try:
        d1 = date.fromisoformat(date1)
        d2 = date.fromisoformat(date2)
        delta = abs((d2 - d1).days)
        return {"date1": date1, "date2": date2, "days": delta}
    except ValueError as e:
        return {"error": str(e)}


# ── Math ─────────────────────────────────────────────────────────────────────

def calculate(expression: str):
    """Safely evaluate a mathematical expression."""
    safe_globals = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    safe_globals["abs"] = abs
    safe_globals["round"] = round
    safe_globals["min"] = min
    safe_globals["max"] = max
    try:
        result = eval(expression, {"__builtins__": {}}, safe_globals)  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


def convert_units(value: float, from_unit: str, to_unit: str):
    """Convert between common units of temperature, length, weight, and speed."""
    f, t = from_unit.lower(), to_unit.lower()

    conversions = {
        # length → meters
        "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
        # weight → kilograms
        "mg": 1e-6, "g": 0.001, "kg": 1.0, "lb": 0.453592, "oz": 0.028350, "t": 1000.0,
        # speed → m/s
        "mph": 0.44704, "kph": 0.27778, "m/s": 1.0, "knot": 0.51444,
    }

    # Temperature handled separately
    temp_units = {"c", "f", "k"}
    if f in temp_units or t in temp_units:
        try:
            if f == "c" and t == "f":
                result = value * 9 / 5 + 32
            elif f == "f" and t == "c":
                result = (value - 32) * 5 / 9
            elif f == "c" and t == "k":
                result = value + 273.15
            elif f == "k" and t == "c":
                result = value - 273.15
            elif f == "f" and t == "k":
                result = (value - 32) * 5 / 9 + 273.15
            elif f == "k" and t == "f":
                result = (value - 273.15) * 9 / 5 + 32
            elif f == t:
                result = value
            else:
                return {"error": f"Unsupported temperature conversion: {f} → {t}"}
            return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 6)}
        except Exception as e:
            return {"error": str(e)}

    if f not in conversions or t not in conversions:
        return {"error": f"Unknown unit(s): '{from_unit}', '{to_unit}'"}

    base = value * conversions[f]
    result = base / conversions[t]
    return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 6)}


def roll_dice(sides: int = 6, count: int = 1):
    """Roll one or more dice with a given number of sides."""
    sides = max(2, int(sides))
    count = min(max(1, int(count)), 100)
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"sides": sides, "count": count, "rolls": rolls, "total": sum(rolls)}


# ── Text ─────────────────────────────────────────────────────────────────────

def count_words(text: str):
    """Count words, characters, and sentences in a block of text."""
    words = len(text.split())
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", ""))
    sentences = len(re.findall(r'[.!?]+', text))
    return {"words": words, "characters": chars, "characters_no_spaces": chars_no_spaces, "sentences": sentences}


def hash_text(text: str, algorithm: str = "sha256"):
    """Hash a string using md5, sha1, or sha256."""
    algo = algorithm.lower().replace("-", "")
    supported = {"md5", "sha1", "sha256"}
    if algo not in supported:
        return {"error": f"Unsupported algorithm '{algorithm}'. Choose from: {', '.join(supported)}"}
    h = hashlib.new(algo, text.encode()).hexdigest()
    return {"algorithm": algo, "hash": h}


def encode_base64(text: str):
    """Encode a UTF-8 string to Base64."""
    encoded = base64.b64encode(text.encode()).decode()
    return {"original": text, "encoded": encoded}


def decode_base64(encoded: str):
    """Decode a Base64 string back to UTF-8 text."""
    try:
        decoded = base64.b64decode(encoded.encode()).decode()
        return {"encoded": encoded, "decoded": decoded}
    except Exception as e:
        return {"error": str(e)}


# ── Random / Generation ───────────────────────────────────────────────────────

def generate_uuid():
    """Generate a random UUID v4."""
    return {"uuid": str(uuid.uuid4())}


def random_choice(items: list):
    """Pick a random element from a list."""
    if not items:
        return {"error": "List is empty"}
    choice = random.choice(items)
    return {"items": items, "choice": choice}


def random_number(min_value: float = 0, max_value: float = 100):
    """Generate a random float between min_value and max_value."""
    if min_value > max_value:
        return {"error": "min_value must be ≤ max_value"}
    result = random.uniform(min_value, max_value)
    return {"min": min_value, "max": max_value, "result": round(result, 6)}


# ── Data ─────────────────────────────────────────────────────────────────────

def sort_list(items: list, order: str = "asc"):
    """Sort a list of numbers or strings. order: 'asc' or 'desc'."""
    try:
        sorted_items = sorted(items, reverse=(order.lower() == "desc"))
        return {"original": items, "sorted": sorted_items, "order": order}
    except TypeError as e:
        return {"error": str(e)}


# ── System / Computer Control ────────────────────────────────────────────────

def list_directory(path: str):
    """List files and subdirectories inside a folder."""
    try:
        entries = []
        with os.scandir(os.path.expanduser(path)) as it:
            for e in sorted(it, key=lambda x: (not x.is_dir(), x.name.lower())):
                stat = e.stat(follow_symlinks=False)
                entries.append({
                    "name": e.name,
                    "type": "dir" if e.is_dir() else "file",
                    "size_bytes": stat.st_size if e.is_file() else None,
                })
        return {"path": path, "count": len(entries), "entries": entries}
    except Exception as e:
        return {"error": str(e)}


def find_files(pattern: str, directory: str = "~", recursive: bool = True, max_results: int = 20):
    """Find files by glob pattern in a directory and return full paths."""
    try:
        base_dir = _expand_path(directory)
        if not os.path.isdir(base_dir):
            return {"error": f"Directory not found: {base_dir}"}
        max_results = min(max(1, int(max_results)), 200)
        matcher = "**/*" if recursive else "*"
        # Use Python's fnmatch semantics via glob-style pattern filtering.
        import fnmatch

        results: list[str] = []
        for root, _, files in os.walk(base_dir):
            for name in files:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    results.append(os.path.join(root, name))
                    if len(results) >= max_results:
                        return {"directory": base_dir, "pattern": pattern, "count": len(results), "paths": results}
            if not recursive:
                break
        return {"directory": base_dir, "pattern": pattern, "count": len(results), "paths": results}
    except Exception as e:
        return {"error": str(e)}


def read_file_text(path: str, max_chars: int = 8000):
    """Read the text content of a file, capped at max_chars characters."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        truncated = os.path.getsize(os.path.expanduser(path)) > max_chars
        return {"path": path, "content": content, "truncated": truncated}
    except Exception as e:
        return {"error": str(e)}



def _is_safe_parent_path(path: str) -> bool:
    p = _expand_path(path)
    parent = os.path.dirname(p)
    if not parent:
        return False
    workspace = os.path.abspath(os.getcwd())
    if _is_protected_path(parent) and os.path.abspath(parent) != workspace:
        return False
    try:
        common = os.path.commonpath([workspace, p])
    except ValueError:
        return False
    return common == workspace


def write_file_text(path: str, content: str, append: bool = False):
    """Write (or append) text to a file. Creates parent directories if needed."""
    try:
        p = _expand_path(path)
        if _is_protected_path(p):
            return {"error": f"Refusing to write to protected path: {p}"}
        if not _is_safe_parent_path(p):
            return {"error": f"Refusing to write outside workspace-safe parent path: {p}"}
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        return {"path": path, "bytes_written": len(content.encode()), "mode": "append" if append else "overwrite"}
    except Exception as e:
        return {"error": str(e)}


def run_shell_command(command: str, timeout: int = 30):
    """Run a shell command and return stdout/stderr."""
    try:
        normalized = _normalize_shell_command(command)
        timeout = min(max(1, int(timeout)), 120)
        if sys.platform == "win32":
            args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", normalized]
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        else:
            result = subprocess.run(normalized, capture_output=True, text=True, timeout=timeout, shell=True)
        return {
            "command": normalized,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def get_system_info():
    """Return basic OS, CPU architecture, hostname, and Python version info."""
    uname = platform.uname()
    return {
        "os": uname.system,
        "os_version": uname.version,
        "release": uname.release,
        "machine": uname.machine,
        "hostname": uname.node,
        "python_version": platform.python_version(),
        "processor": uname.processor,
    }


def get_disk_usage(path: str = "C:\\"):
    """Return total, used, and free disk space for a drive or path."""
    try:
        usage = shutil.disk_usage(os.path.expanduser(path))
        gb = 1024 ** 3
        return {
            "path": path,
            "total_gb": round(usage.total / gb, 2),
            "used_gb": round(usage.used / gb, 2),
            "free_gb": round(usage.free / gb, 2),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception as e:
        return {"error": str(e)}

def get_running_processes():
    """List running processes with PID and memory usage."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15
            )
            processes = []
            for line in result.stdout.strip().splitlines()[:60]:
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 5:
                    processes.append({"name": parts[0], "pid": parts[1], "memory": parts[4]})
            return {"count": len(processes), "processes": processes}

        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,%mem=", "--sort=-%mem"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        processes = []
        for line in result.stdout.strip().splitlines()[:60]:
            parts = line.split(None, 2)
            if len(parts) >= 3:
                pid, name, mem = parts
                processes.append({"name": name, "pid": pid, "memory": f"{mem}%"})
        return {"count": len(processes), "processes": processes}
    except Exception as e:
        return {"error": str(e)}



def kill_process(identifier: str):
    """Kill a process by name (e.g. 'notepad.exe') or PID."""
    try:
        if sys.platform == "win32":
            if identifier.isdigit():
                args = ["taskkill", "/PID", identifier, "/F"]
            else:
                args = ["taskkill", "/IM", identifier, "/F"]
        else:
            if identifier.isdigit():
                args = ["kill", "-9", identifier]
            else:
                args = ["pkill", "-f", identifier]
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return {
            "identifier": identifier,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"error": str(e)}



def open_file(path: str):
    """Open a file or URL with its default application."""
    try:
        target = os.path.expanduser(path)
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", target], capture_output=True, text=True, timeout=10)
        else:
            subprocess.run(["xdg-open", target], capture_output=True, text=True, timeout=10)
        return {"opened": path}
    except Exception as e:
        return {"error": str(e)}



def create_directory(path: str):
    """Create a directory (and any missing parents)."""
    try:
        p = _expand_path(path)
        if _is_protected_path(p):
            return {"error": f"Refusing to create protected path directly: {p}"}
        os.makedirs(p, exist_ok=True)
        return {"path": path, "created": True}
    except Exception as e:
        return {"error": str(e)}


def delete_path(path: str):
    """Delete a file or directory tree."""
    try:
        p = _expand_path(path)
        if not os.path.exists(p):
            return {"error": f"Path does not exist: {p}"}
        if _is_protected_path(p):
            return {"error": f"Refusing to delete protected path: {p}"}
        if os.path.isdir(p):
            shutil.rmtree(p)
            kind = "directory"
        else:
            os.remove(p)
            kind = "file"
        return {"deleted": path, "type": kind}
    except Exception as e:
        return {"error": str(e)}


def move_path(source: str, destination: str):
    """Move or rename a file or directory."""
    try:
        src = _expand_path(source)
        dst = _expand_path(destination)
        if not os.path.exists(src):
            return {"error": f"Source does not exist: {src}"}
        if _is_protected_path(src):
            return {"error": f"Refusing to move protected source path: {src}"}
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.move(src, dst)
        return {"source": source, "destination": destination}
    except Exception as e:
        return {"error": str(e)}


def copy_file(source: str, destination: str):
    """Copy a file to a destination path."""
    try:
        src = _expand_path(source)
        dst = _expand_path(destination)
        if not os.path.isfile(src):
            return {"error": f"Source file does not exist: {src}"}
        if _is_protected_path(src):
            return {"error": f"Refusing to copy protected source path: {src}"}
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
        return {"source": source, "destination": destination}
    except Exception as e:
        return {"error": str(e)}


def get_environment_variable(name: str):
    """Read the value of an environment variable."""
    value = os.environ.get(name)
    if value is None:
        return {"error": f"Environment variable '{name}' not found"}
    return {"name": name, "value": value}


def ping_host(host: str, count: int = 4):
    """Ping a hostname or IP address and return latency stats."""
    try:
        count = min(max(1, int(count)), 10)
        ping_flag = "-n" if sys.platform == "win32" else "-c"
        result = subprocess.run(
            ["ping", ping_flag, str(count), host],
            capture_output=True, text=True, timeout=30
        )
        return {"host": host, "output": result.stdout.strip(), "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Ping timed out"}
    except Exception as e:
        return {"error": str(e)}



def _call_compound(prompt: str) -> dict:
    """Send a prompt to groq/compound and return structured output."""
    try:
        from groq import Groq  # noqa: PLC0415

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            return {"error": "GROQ_API_KEY not set"}

        compound_model = os.getenv("OPERATOR_COMPOUND_MODEL", "groq/compound")
        timeout_seconds = float(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        max_retries = max(0, int(os.getenv("GROQ_MAX_RETRIES", "2")))
        client = Groq(api_key=api_key)

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=compound_model,
                    messages=[{"role": "user", "content": str(prompt).strip()}],
                    temperature=0,
                    timeout=timeout_seconds,
                )
                break
            except Exception as e:
                last_error = e
                if attempt >= max_retries:
                    return {"error": str(e)}
                time.sleep(min(2 ** attempt, 4))

        if 'resp' not in locals():
            return {"error": str(last_error) if last_error else "compound request failed"}

        msg = resp.choices[0].message
        content = (msg.content or "").strip()

        executed_tools = []
        for t in getattr(msg, "executed_tools", None) or []:
            tool_type = str(getattr(t, "type", "") or "").strip()
            if tool_type:
                executed_tools.append(tool_type)

        return {
            "result": content,
            "model": compound_model,
            "executed_tools": executed_tools,
        }
    except Exception as e:
        return {"error": str(e)}


def compound_search(query: str, context: str = "") -> dict:
    """General-purpose route to groq/compound for live web or code tasks."""
    prompt = str(query).strip()
    if context:
        prompt = f"{context.strip()}\n\n{prompt}"
    return _call_compound(prompt)


def compound_web_search(query: str, max_results: int = 5) -> dict:
    """Force a web search style request through groq/compound."""
    q = str(query).strip()
    if not q:
        return {"error": "query is required"}
    max_results = min(max(1, int(max_results)), 10)
    prompt = (
        "Use web search to answer this query with current information. "
        f"Return up to {max_results} concise results with source links when possible.\n\n"
        f"Query: {q}"
    )
    return _call_compound(prompt)


def compound_visit_website(url: str, instruction: str = "Summarize the key points.") -> dict:
    """Ask groq/compound to visit a website and return extracted information."""
    u = str(url).strip()
    if not u:
        return {"error": "url is required"}
    prompt = (
        "Visit this website and follow the instruction below. "
        "Include important factual details and cite the page URL in your response.\n\n"
        f"URL: {u}\n"
        f"Instruction: {instruction}"
    )
    return _call_compound(prompt)


def compound_run_code(task: str, language: str = "python") -> dict:
    """Ask groq/compound to use code interpreter for a computation task."""
    t = str(task).strip()
    if not t:
        return {"error": "task is required"}
    lang = str(language or "python").strip().lower()
    prompt = (
        "Use the code interpreter tool to complete this task. "
        "Show the final answer and a brief note of what code was executed.\n\n"
        f"Language: {lang}\n"
        f"Task: {t}"
    )
    return _call_compound(prompt)


def compound_browser_automation(task: str) -> dict:
    """Ask groq/compound to use browser automation for a multi-step browser task."""
    t = str(task).strip()
    if not t:
        return {"error": "task is required"}
    prompt = (
        "Use browser automation to complete this browser task. "
        "Return the final outcome and key steps performed.\n\n"
        f"Task: {t}"
    )
    return _call_compound(prompt)


def compound_wolfram(query: str) -> dict:
    """Ask groq/compound to use Wolfram Alpha for math/science knowledge queries."""
    q = str(query).strip()
    if not q:
        return {"error": "query is required"}
    prompt = (
        "Use Wolfram Alpha to answer this precisely. "
        "Return key result values and units when relevant.\n\n"
        f"Query: {q}"
    )
    return _call_compound(prompt)


def get_tools():
    """Return the currently available tool names and descriptions."""
    tools = []
    for item in TOOLS:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        name = fn.get("name")
        if not name:
            continue
        tools.append({
            "name": name,
            "description": fn.get("description", ""),
        })
    return {"count": len(tools), "tools": tools}


def ask_question(question: str):
    """Prompt the local user for follow-up input and return their answer."""
    try:
        answer = input(f"Hermes follow-up: {question}\n> ").strip()
        return {"question": question, "answer": answer}
    except Exception as e:
        return {"error": str(e)}


# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "compound_web_search",
            "description": "Run a live web search via groq/compound and return concise sourced results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "max_results": {"type": "integer", "description": "Maximum number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compound_visit_website",
            "description": "Visit a webpage through groq/compound and return extracted information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to visit"},
                    "instruction": {"type": "string", "description": "What to extract or do on the page"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compound_run_code",
            "description": "Use groq/compound code interpreter to run code for analysis or computation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Computation or coding task to execute"},
                    "language": {"type": "string", "description": "Preferred language, default python"},
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compound_browser_automation",
            "description": "Use groq/compound browser automation for multi-step web interaction tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Browser automation objective and steps"}
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compound_wolfram",
            "description": "Use groq/compound with Wolfram Alpha for precise math/science/units queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Math or science query for Wolfram"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compound_search",
            "description": "Search the web, run code, or answer questions requiring live data by routing the request to groq/compound (a server-side AI that has built-in web search and code execution). Use this whenever the task needs up-to-date information from the internet or requires executing code you cannot run locally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query, question, or code task to send to the server-side AI"},
                    "context": {"type": "string", "description": "Optional extra instructions or context to prepend to the query (e.g. 'summarize in 3 bullets')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_question",
            "description": "Ask the local user a follow-up question and capture their response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The follow-up question to ask the user"}
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tools",
            "description": "List all currently available local tools and their descriptions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time in a specified IANA timezone (e.g. 'America/New_York', 'UTC').",
            "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get current weather for a city or location (e.g. 'Boston', 'London', 'Tokyo').",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location to query weather for"},
                    "unit": {"type": "string", "enum": ["c", "f"], "description": "Temperature unit, c or f (default f)"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "days_between",
            "description": "Calculate the number of days between two dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date1": {"type": "string", "description": "First date in YYYY-MM-DD format"},
                    "date2": {"type": "string", "description": "Second date in YYYY-MM-DD format"},
                },
                "required": ["date1", "date2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression. Supports standard math operators and functions (sin, cos, sqrt, log, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Math expression to evaluate, e.g. '2 ** 10' or 'sqrt(144)'"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_units",
            "description": "Convert a value between units of temperature (c/f/k), length (mm/cm/m/km/in/ft/yd/mi), weight (mg/g/kg/lb/oz/t), or speed (mph/kph/m/s/knot).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "from_unit": {"type": "string"},
                    "to_unit": {"type": "string"},
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "Roll one or more dice. Default is one standard 6-sided die.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "description": "Number of sides on each die (default 6)"},
                    "count": {"type": "integer", "description": "Number of dice to roll (default 1, max 100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_words",
            "description": "Count the words, characters, and sentences in a text.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hash_text",
            "description": "Hash a string using md5, sha1, or sha256.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "algorithm": {"type": "string", "enum": ["md5", "sha1", "sha256"], "description": "Hashing algorithm (default sha256)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "encode_base64",
            "description": "Encode a UTF-8 string to Base64.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decode_base64",
            "description": "Decode a Base64-encoded string back to plain text.",
            "parameters": {
                "type": "object",
                "properties": {"encoded": {"type": "string"}},
                "required": ["encoded"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_uuid",
            "description": "Generate a random UUID v4.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "random_choice",
            "description": "Pick a random element from a list of items.",
            "parameters": {
                "type": "object",
                "properties": {"items": {"type": "array", "items": {}}},
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "random_number",
            "description": "Generate a random number between min_value and max_value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_value": {"type": "number", "description": "Lower bound (default 0)"},
                    "max_value": {"type": "number", "description": "Upper bound (default 100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sort_list",
            "description": "Sort a list of numbers or strings in ascending or descending order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {}},
                    "order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort order (default 'asc')"},
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories inside a folder. Returns name, type (file/dir), and size.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute or ~ path to the directory"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find files by filename pattern within a directory. Supports wildcard patterns like '*obs*installer*.exe'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Filename pattern with wildcards, e.g. '*setup*.exe'"},
                    "directory": {"type": "string", "description": "Base directory to search (default '~')"},
                    "recursive": {"type": "boolean", "description": "Search subdirectories (default true)"},
                    "max_results": {"type": "integer", "description": "Maximum result count (default 20)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_text",
            "description": "Read the text content of a file on disk (up to 8000 characters by default).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "max_chars": {"type": "integer", "description": "Max characters to read (default 8000)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file_text",
            "description": "Write or append text content to a file. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "description": "If true, append instead of overwrite (default false)"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Run a PowerShell command on the local machine and return stdout/stderr output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to execute"},
                    "timeout": {"type": "integer", "description": "Seconds before timeout (default 30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get OS name, version, hostname, CPU architecture, and Python version.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_usage",
            "description": "Get total, used, and free disk space for a drive or path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Drive or path to check (default 'C:\\\\')"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_running_processes",
            "description": "List currently running processes with their PID and memory usage.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a running process by its name (e.g. 'notepad.exe') or numeric PID.",
            "parameters": {
                "type": "object",
                "properties": {"identifier": {"type": "string", "description": "Process name or PID"}},
                "required": ["identifier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "Open a file or URL with its default application (as if double-clicked).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path or URL to open"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Create a directory and any missing parent directories.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_path",
            "description": "Permanently delete a file or directory tree from disk.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_path",
            "description": "Move or rename a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file to a new destination path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_environment_variable",
            "description": "Read the value of a system or user environment variable.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Variable name, e.g. 'PATH' or 'USERPROFILE'"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ping_host",
            "description": "Ping a hostname or IP address and return the latency output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Hostname or IP, e.g. '8.8.8.8' or 'google.com'"},
                    "count": {"type": "integer", "description": "Number of ping packets (default 4, max 10)"},
                },
                "required": ["host"],
            },
        },
    },
]

EXECUTOR = {
    "ask_question": ask_question,
    "compound_web_search": compound_web_search,
    "compound_visit_website": compound_visit_website,
    "compound_run_code": compound_run_code,
    "compound_browser_automation": compound_browser_automation,
    "compound_wolfram": compound_wolfram,
    "compound_search": compound_search,
    "get_tools": get_tools,
    "get_time": get_time,
    "get_current_weather": get_current_weather,
    "days_between": days_between,
    "calculate": calculate,
    "convert_units": convert_units,
    "roll_dice": roll_dice,
    "count_words": count_words,
    "hash_text": hash_text,
    "encode_base64": encode_base64,
    "decode_base64": decode_base64,
    "generate_uuid": generate_uuid,
    "random_choice": random_choice,
    "random_number": random_number,
    "sort_list": sort_list,
    # system
    "list_directory": list_directory,
    "find_files": find_files,
    "read_file_text": read_file_text,
    "write_file_text": write_file_text,
    "run_shell_command": run_shell_command,
    "get_system_info": get_system_info,
    "get_disk_usage": get_disk_usage,
    "get_running_processes": get_running_processes,
    "kill_process": kill_process,
    "open_file": open_file,
    "create_directory": create_directory,
    "delete_path": delete_path,
    "move_path": move_path,
    "copy_file": copy_file,
    "get_environment_variable": get_environment_variable,
    "ping_host": ping_host,
}