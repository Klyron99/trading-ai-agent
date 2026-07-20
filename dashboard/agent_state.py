"""
Gestion de l'état des agents (processus en cours, PID, tickers).
Supporte plusieurs agents en parallèle — un par ticker.
Persiste dans un fichier JSON — source de vérité unique.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
_STATE_FILE = _ROOT / "agent" / "memory_store" / "agent_process.json"


# ── Lecture / écriture du fichier d'état ─────────────────────────────────────

def _read() -> dict:
    try:
        data = json.loads(_STATE_FILE.read_text())
        # Migration ancien format {"running": ..., "pid": ..., "ticker": ...}
        if "agents" not in data:
            ticker = data.get("ticker")
            if ticker and data.get("running"):
                return {"agents": {ticker: {"running": True, "pid": data.get("pid"), "started_at": data.get("started_at")}}}
            return {"agents": {}}
        return data
    except Exception:
        return {"agents": {}}


def _write(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state))


def _update_ticker(ticker: str, info: dict | None) -> None:
    """Met à jour l'entrée d'un seul ticker sans toucher aux autres."""
    state = _read()
    if info is None:
        state["agents"].pop(ticker, None)
    else:
        state["agents"][ticker] = info
    _write(state)


# ── Utilitaires PID ───────────────────────────────────────────────────────────

def _pid_alive(pid) -> bool:
    if not pid or pid == -1:
        return False
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except ImportError:
        pass
    try:
        import ctypes
        SYNCHRONIZE = 0x00100000
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return False


def _kill_pid(pid: int) -> None:
    try:
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def _kill_all_run_agent_processes() -> None:
    """Tue tous les processus run_agent — psutil + taskkill en fallback."""
    killed = set()
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "run_agent" in cmdline and "python" in cmdline.lower():
                    proc.kill()
                    killed.add(proc.info["pid"])
            except Exception:
                pass
    except ImportError:
        pass
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "Name='python.exe' and CommandLine like '%run_agent%'",
             "get", "ProcessId", "/format:value"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("ProcessId="):
                pid_str = line.split("=", 1)[1].strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if pid not in killed:
                        _kill_pid(pid)
                        killed.add(pid)
    except Exception:
        pass
    if killed:
        time.sleep(0.5)


# ── API publique ──────────────────────────────────────────────────────────────

def get_all_agents_status() -> dict[str, dict]:
    """Retourne {ticker: {"running": bool, "pid": int, "started_at": float}} pour tous les agents actifs."""
    state = _read()
    result = {}
    dirty = False
    for ticker, info in list(state["agents"].items()):
        pid = info.get("pid")
        if info.get("running") and pid and pid != -1:
            if _pid_alive(pid):
                result[ticker] = info
            else:
                # PID mort — agent crashé
                state["agents"].pop(ticker)
                dirty = True
        elif info.get("running") and pid == -1:
            result[ticker] = info  # démarrage en cours
    if dirty:
        _write(state)
    return result


def get_agent_status(ticker: str | None = None) -> dict:
    """Compat backward — retourne le statut d'un ticker ou du premier agent actif."""
    all_status = get_all_agents_status()
    if ticker:
        info = all_status.get(ticker)
        if info:
            return {"running": True, "pid": info.get("pid"), "ticker": ticker, "started_at": info.get("started_at")}
        return {"running": False, "pid": None, "ticker": ticker}
    # Sans ticker : retourne le premier actif (compat ancienne API)
    if all_status:
        t, info = next(iter(all_status.items()))
        return {"running": True, "pid": info.get("pid"), "ticker": t, "started_at": info.get("started_at")}
    return {"running": False, "pid": None, "ticker": None}


def get_active_tickers() -> list[str]:
    """Retourne la liste des tickers avec un agent actif."""
    return list(get_all_agents_status().keys())


def _kill_all_for_ticker(ticker: str) -> None:
    """Tue TOUS les processus run_agent pour ce ticker, enregistrés ou zombies."""
    # 1. PID enregistré dans le JSON
    all_status = get_all_agents_status()
    if ticker in all_status:
        old_pid = all_status[ticker].get("pid")
        if old_pid and old_pid != -1:
            _kill_pid(old_pid)

    # 2. Scan psutil — attrape les zombies non enregistrés
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "run_agent" in cmdline and ticker in cmdline:
                    proc.kill()
            except Exception:
                pass
    except ImportError:
        pass

    if all_status.get(ticker):
        time.sleep(0.4)


def start_agent(ticker: str, interval: int = 60) -> tuple[bool, str]:
    """Démarre un agent pour ce ticker — tue tout doublon/zombie avant."""
    ticker = ticker.upper()
    _kill_all_for_ticker(ticker)

    script = _ROOT / "run_agent.py"
    log_dir = _ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_out = log_dir / f"agent_{ticker}.log"

    _update_ticker(ticker, {"running": True, "pid": -1, "started_at": time.time()})

    try:
        with open(log_out, "a") as fout:
            proc = subprocess.Popen(
                [sys.executable, str(script), "--ticker", ticker, "--interval", str(interval)],
                cwd=str(_ROOT),
                stdout=fout,
                stderr=fout,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        _update_ticker(ticker, {"running": True, "pid": proc.pid, "started_at": time.time()})
        return True, f"Agent démarré — {ticker} (PID {proc.pid})"
    except Exception as e:
        _update_ticker(ticker, None)
        return False, f"Erreur : {e}"


def stop_agent(ticker: str | None = None) -> tuple[bool, str]:
    """Arrête l'agent d'un ticker précis, ou tous les agents si ticker=None."""
    all_status = get_all_agents_status()

    if ticker:
        ticker = ticker.upper()
        info = all_status.get(ticker)
        if info:
            pid = info.get("pid")
            if pid and pid != -1:
                _kill_pid(pid)
            _update_ticker(ticker, None)
            _launch_retrain(ticker)
            return True, f"Agent {ticker} arrêté."
        return False, f"Aucun agent actif pour {ticker}."
    else:
        # Arrête tous les agents
        stopped = []
        for t, info in all_status.items():
            pid = info.get("pid")
            if pid and pid != -1:
                _kill_pid(pid)
            stopped.append(t)
        _kill_all_run_agent_processes()
        _write({"agents": {}})
        for t in stopped:
            _launch_retrain(t)
        msg = f"Tous les agents arrêtés ({', '.join(stopped)})." if stopped else "Aucun agent actif."
        return True, msg


def _launch_retrain(ticker: str) -> None:
    try:
        script = _ROOT / "retrain_agent.py"
        subprocess.Popen(
            [sys.executable, str(script), "--tickers", ticker],
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except Exception:
        pass


def run_retrain(tickers: list[str]) -> tuple[bool, str]:
    script = _ROOT / "retrain_agent.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--tickers"] + tickers,
            cwd=str(_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        output = (result.stdout + result.stderr).strip()[-3000:]
        success_keywords = ["termin", "cycle", "learning loop", "replaced", "best="]
        is_success = result.returncode == 0 or any(k in output.lower() for k in success_keywords)
        if is_success:
            return True, output or "Réentraînement terminé."
        else:
            return False, output or f"Erreur (code {result.returncode})"
    except subprocess.TimeoutExpired:
        return False, "Timeout (5 min) — réentraînement trop long."
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_previous_close(ticker: str) -> float | None:
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        v = getattr(fi, "previous_close", None)
        return float(v) if v else None
    except Exception:
        return None


def get_price_info(ticker: str) -> dict:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=True)
        live = float(hist["Close"].iloc[-1]) if not hist.empty else None
    except Exception:
        live = None
    return {"live": live, "close": _get_previous_close(ticker)}


def get_live_price(ticker: str) -> float | None:
    info = get_price_info(ticker)
    return info["live"] or info["close"]
