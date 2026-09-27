#!/usr/bin/env python3
"""One-click local Vednix launcher for the API and web workspace.

Provider credentials are configured in the browser after launch and are stored
encrypted by the backend. This script never installs model runtimes or handles
provider keys. Python and Node dependencies are installed locally in the repo.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
LOGS = ROOT / "logs"
APP_PORT = 3000
APP_URL = f"http://localhost:{APP_PORT}"
HEALTH_URL = "http://localhost:8000/api/health"
IS_WIN = platform.system() == "Windows"


def fail(message: str, hint: str = "") -> None:
    print(f"\n✖ {message}", flush=True)
    if hint:
        print(f"  → {hint}", flush=True)
    raise SystemExit(1)


def step(index: int, total: int, message: str) -> None:
    print(f"\nStep {index}/{total} — {message}", flush=True)


def ok(message: str) -> None:
    print(f"  ✓ {message}", flush=True)


def run(command: list[str], cwd: Path | None = None) -> int:
    return subprocess.call(command, cwd=cwd)


def npm_cmd(*args: str) -> list[str]:
    executable = shutil.which("npm") or "npm"
    return ["cmd.exe", "/c", executable, *args] if IS_WIN else [executable, *args]


def python_in_venv() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def choose_frontend_port() -> int:
    for port in (3000, 3001):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    fail("Ports 3000 and 3001 are already in use.", "Close the existing Vednix frontend and retry.")
    return 3000


def http_get(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, response.read().decode("utf-8", "replace")
    except Exception as exc:
        return False, str(exc)


def open_browser(url: str) -> None:
    try:
        if not webbrowser.open(url):
            print(f"Open the workspace in your browser: {url}", flush=True)
    except Exception:
        print(f"Open the workspace in your browser: {url}", flush=True)


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    if sys.version_info < (3, 11):
        fail("Python 3.11 or newer is required.", "Install it from https://python.org and retry.")

    step(1, 5, "Preparing Python dependencies")
    if not python_in_venv().exists():
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            fail("Could not create the project virtual environment.")
    if run([str(python_in_venv()), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.txt")]) != 0:
        fail("Backend dependency installation failed.", "Check your internet connection and retry.")
    ok("Backend dependencies ready")

    step(2, 5, "Checking Node.js")
    node = shutil.which("node")
    if not node or not shutil.which("npm"):
        fail("Node.js 20 or newer is required.", "Install from https://nodejs.org and retry.")
    ok(f"Node {subprocess.check_output([node, '--version'], text=True).strip()}")

    step(3, 5, "Preparing the frontend")
    if not (FRONTEND / "node_modules").exists():
        if run(npm_cmd("ci"), cwd=FRONTEND) != 0:
            fail("Frontend dependency installation failed.")
    ok("Frontend dependencies ready")

    step(4, 5, "Starting the API and workspace")
    global APP_PORT, APP_URL
    APP_PORT = choose_frontend_port()
    APP_URL = f"http://localhost:{APP_PORT}"
    logs = {name: (LOGS / f"{name}.log").open("ab") for name in ("backend", "frontend")}
    popen_kwargs: dict = {}
    if IS_WIN:
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        popen_kwargs["start_new_session"] = True
    children: list[subprocess.Popen] = []
    children.append(subprocess.Popen(
        [str(python_in_venv()), str(BACKEND / "main.py")],
        cwd=BACKEND, stdout=logs["backend"], stderr=subprocess.STDOUT, **popen_kwargs,
    ))
    children.append(subprocess.Popen(
        npm_cmd("run", "dev", "--", "-p", str(APP_PORT)),
        cwd=FRONTEND, stdout=logs["frontend"], stderr=subprocess.STDOUT, **popen_kwargs,
    ))

    step(5, 5, "Waiting for Vednix and opening the browser")
    ready = False
    for _ in range(90):
        time.sleep(1)
        up, body = http_get(HEALTH_URL)
        if up and '"status":"ok"' in body.replace(" ", ""):
            ready = True
            break
        if any(child.poll() is not None for child in children):
            fail("A Vednix service exited early.", "Check logs/backend.log and logs/frontend.log.")
    if not ready:
        fail("The API did not become ready.", "Check logs/backend.log.")
    open_browser(APP_URL)
    print(f"\nVednix is running at {APP_URL}\nConfigure a Gemini or Groq key in the provider setup.\nPress Ctrl+C to stop.\n", flush=True)

    try:
        while all(child.poll() is None for child in children):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
        for log in logs.values():
            log.close()
        print("\nVednix stopped.\n", flush=True)


if __name__ == "__main__":
    main()
