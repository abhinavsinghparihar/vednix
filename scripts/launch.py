#!/usr/bin/env python3
"""VEDNIX one-click launcher — the whole machine, one command.

Made for people who have never heard of Ollama, pip, venv or npm:
  1. checks Python                   5. installs the Vednix Engine (Ollama) if needed
  2. builds the backend venv         6. starts the engine, pulls the default model
  3. checks Node.js                  7. starts backend + frontend
  4. builds the frontend             8. opens the browser at the app

Step by step it says WHAT it is doing and WHY — Ctrl+C stops everything.
Zero third-party dependencies: stdlib only, so it runs anywhere Python 3.11+ runs.
"""

from __future__ import annotations

import os
import platform
import shutil
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
ENGINE_URL = "http://localhost:11434"
APP_URL = "http://localhost:3000"
HEALTH_URL = "http://localhost:8000/api/health"
DEFAULT_MODEL = "qwen2.5:3b"
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def step(n: int, total: int, what: str) -> None:
    print(f"\n\033[1mStep {n}/{total} — {what}\033[0m", flush=True)


def info(msg: str) -> None:
    print(f"   · {msg}", flush=True)


def fail(msg: str, hint: str = "") -> None:
    print(f"\n\033[91m✖ {msg}\033[0m", flush=True)
    if hint:
        print(f"   → {hint}", flush=True)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"   \033[92m✓\033[0m {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, quiet: bool = False, env: dict | None = None) -> int:
    return subprocess.call(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )


def npm_cmd(*args: str) -> list[str]:
    """npm is a `.cmd` shim on Windows — CreateProcess can't exec it directly."""
    exe = shutil.which("npm") or "npm"
    if IS_WIN:
        return ["cmd.exe", "/c", exe, *args]
    return [exe, *args]


def open_browser(url: str) -> None:
    """Open the app; never crash if no console/browser is available."""
    try:
        if IS_WIN:
            os.startfile(url)  # type: ignore[attr-defined]  # Windows shell — no console needed
            ok("Browser khol diya")
        elif webbrowser.open(url):
            ok("Browser khol diya")
        else:
            info(f"Browser khud nahi khula — khol lo: {url}")
    except Exception:
        info(f"Browser khud nahi khula — khol lo: {url}")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def http_get(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, resp.read().decode("utf-8", "replace")
    except Exception as exc:  # engine/backend down is an expected branch
        return False, str(exc)


def find_ollama() -> str | None:
    """Locate the ollama binary (winget installs don't refresh PATH mid-session)."""
    exe = shutil.which("ollama")
    if exe:
        return exe
    if IS_WIN:
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
        if local.exists():
            return str(local)
    return None


def install_engine() -> None:
    if IS_WIN:
        winget = shutil.which("winget")
        if not winget:
            fail("Ollama not found AND winget unavailable.",
                 "Download the engine once from https://ollama.com/download/windows — then double-click start.bat again.")
        info("Downloading & installing the Vednix Engine via winget (one-time)…")
        if run([winget, "install", "-e", "--id", "Ollama.Ollama",
                "--accept-source-agreements", "--accept-package-agreements"]) != 0:
            fail("winget couldn't install Ollama.",
                 "Install it by hand from https://ollama.com/download — then run start.bat again.")
    elif IS_MAC:
        brew = shutil.which("brew")
        if brew:
            if run([brew, "install", "ollama"]) != 0:
                fail("brew couldn't install Ollama.", "Install from https://ollama.com/download/mac")
        else:
            fail("Ollama not found.", "Install from https://ollama.com/download/mac — then run this again.")
    else:  # Linux — official one-liner, exactly what the docs prescribe
        if run(["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]) != 0:
            fail("Automatic install failed.", "Install from https://ollama.com/download — then run this again.")


def ensure_engine_serving() -> None:
    up, _ = http_get(f"{ENGINE_URL}/api/tags")
    if up:
        ok("Engine is already serving on localhost:11434")
        return
    exe = find_ollama()
    if not exe:
        fail("Engine binary vanished after install.",
             "Restart the computer once (fresh PATH), then run start.bat again.")
    info("Waking the Vednix Engine (ollama serve)…")
    kwargs = {"stdout": (LOGS / "engine.log").open("ab"), "stderr": subprocess.STDOUT}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, "serve"], **kwargs)  # type: ignore[arg-type]
    for _ in range(30):
        time.sleep(1)
        up, _ = http_get(f"{ENGINE_URL}/api/tags")
        if up:
            ok("Engine is live")
            return
    fail("The engine didn't answer in 30s.", "See logs/engine.log")


def ensure_model(exe: str) -> None:
    try:
        result = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30)
        out = result.stdout if result.returncode == 0 else ""
    except Exception:
        out = ""
    if DEFAULT_MODEL in out:
        ok(f"Model {DEFAULT_MODEL} already on this machine")
        return
    info(f"Pulling {DEFAULT_MODEL} (~2GB, one-time — progress below)…")
    if run([exe, "pull", DEFAULT_MODEL]) != 0:
        fail(f"Couldn't pull {DEFAULT_MODEL}.", f"Run manually: ollama pull {DEFAULT_MODEL}")
    ok(f"Model {DEFAULT_MODEL} ready")


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    print("\033[1;33m", r"""
        __     ________  ____  _   _ _____  __
        \ \   / / ____||  _ \| \ | |_ _\ \/ /
         \ \ / /|  _|  | | | |  \| || | \  /
          \ V / | |___ | |_| | |\  || | /  \
           \_/  |_____||____/|_| \_|___/_/\_\
    """ + "\033[0m", flush=True)
    print("  One-click launcher — sit back; everything below happens by itself.\n")

    # ---- 1/8: python ----------------------------------------------------------
    step(1, 8, "Checking Python")
    if sys.version_info < (3, 11):
        fail(f"Python {sys.version.split()[0]} is too old.", "Install Python 3.11+ from https://python.org")
    ok(f"Python {sys.version.split()[0]}")

    # ---- 2/8: backend env -----------------------------------------------------
    step(2, 8, "Preparing the backend (brain of the app)")
    if not venv_python().exists():
        info("Creating the virtualenv (one-time)…")
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            fail("Couldn't create .venv.", "Delete the .venv folder and retry.")
    info("Installing backend dependencies (quiet unless something breaks)…")
    if run([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.txt")]) != 0:
        fail("pip install failed.", "Check your internet ONCE for the install; then it's all local.")
    ok("Backend ready")

    # ---- 3/8: node ------------------------------------------------------------
    step(3, 8, "Checking Node.js (for the interface)")
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        fail("Node.js not found.", "Install Node 20+ from https://nodejs.org — then run this again.")
    ok(f"Node {subprocess.check_output([node, '--version'], text=True).strip()}")

    # ---- 4/8: frontend --------------------------------------------------------
    step(4, 8, "Preparing the frontend (the face)")
    if not (FRONTEND / "node_modules").exists():
        info("npm install (one-time, a few minutes)…")
        if run(npm_cmd("install"), cwd=FRONTEND) != 0:
            fail("npm install failed.", "Delete frontend/node_modules and retry.")
    if not (FRONTEND / ".next/BUILD_ID").exists():
        info("Building the production interface (one-time)…")
        if run(npm_cmd("run", "build"), cwd=FRONTEND) != 0:
            fail("npm run build failed.", "Run it once manually inside frontend/ to see the full error.")
    ok("Frontend ready")

    # ---- 5/8: engine present ---------------------------------------------------
    step(5, 8, "Vednix Engine check (the AI that runs on YOUR machine)")
    if find_ollama():
        ok("Engine found")
    else:
        info("Not found — installing it for you right now…")
        install_engine()
        if not find_ollama():
            fail("Engine installed but not on PATH yet.",
                 "Restart the computer once, then double-click start.bat again.")
        ok("Engine installed")

    # ---- 6/8: engine live + model ----------------------------------------------
    step(6, 8, "Starting the engine + ensuring a brain (model)")
    ensure_engine_serving()
    ensure_model(find_ollama() or "ollama")

    # ---- 7/8: start the two servers --------------------------------------------
    step(7, 8, "Starting Vednix — backend on :8000, frontend on :3000")
    backend_log = (LOGS / "backend.log").open("ab")
    frontend_log = (LOGS / "frontend.log").open("ab")
    children: list[subprocess.Popen] = []
    popen_kwargs: dict = {}
    if IS_WIN:
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        popen_kwargs["start_new_session"] = True
    children.append(subprocess.Popen(
        [str(venv_python()), str(BACKEND / "main.py")],
        cwd=BACKEND, stdout=backend_log, stderr=subprocess.STDOUT, **popen_kwargs))
    time.sleep(2)
    children.append(subprocess.Popen(
        npm_cmd("start"), cwd=FRONTEND, stdout=frontend_log, stderr=subprocess.STDOUT, **popen_kwargs))

    # ---- 8/8: health + browser --------------------------------------------------
    step(8, 8, "Waiting for the heartbeat, then opening your browser")
    ready = False
    for _ in range(90):
        time.sleep(1)
        up, body = http_get(HEALTH_URL)
        if up and '"status":"ok"' in body.replace(" ", ""):
            ready = True
            break
        if children[0].poll() is not None:
            fail("Backend exited early — full story in logs/backend.log")
    if not ready:
        fail("Backend never came up.", "See logs/backend.log — then tell support what it says.")
    ok("Backend live " + body.strip()[:120])
    time.sleep(2)
    open_browser(APP_URL)

    print(f"""
\033[92m\033[1m✔ VEDNIX IS RUNNING\033[0m  →  {APP_URL}

  Agla step aapka hai — browser me:
    1. Setup ceremony:  "Free · Private · Unlimited" choose karo
    2. Apna owner account banao (NO SIGNUP, NO ENTRY — pehla account = owner)
    3. Chat shuru. Engine aapke machine pe, data aapke machine pe — hamesha.

  Logs: logs/backend.log · logs/frontend.log · logs/engine.log
  Rokna ho to is window me \033[1mCtrl+C\033[0m dabao — sab band ho jayega.
""", flush=True)

    try:
        while True:
            time.sleep(1)
            if any(c.poll() is not None for c in children):
                info("A server stopped — shutting the rest down. See logs/.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        for c in children:
            try:
                c.terminate()
            except Exception:
                pass
        print("\nVednix stopped. Phir milte hain. 👋\n")


if __name__ == "__main__":
    main()
