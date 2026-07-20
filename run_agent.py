"""
Point d'entrée pour lancer l'agent de trading adaptatif.

Usage :
    python run_agent.py
    python run_agent.py --ticker QQQ --interval 60
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

from agent.trading_agent import TradingAgent
from config.settings import AGENT_ALLOWED_TICKERS, AGENT_RETRAIN_EVERY_HOURS, LIVE_TICKER


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agent de paper trading adaptatif")
    p.add_argument("--ticker",       default=LIVE_TICKER,              help="Ticker à trader")
    p.add_argument("--interval",     default=60,   type=int,           help="Secondes entre chaque tick")
    p.add_argument("--retrain-hours",default=AGENT_RETRAIN_EVERY_HOURS, type=float)
    p.add_argument("--log-file",     default=None,                     help="Fichier de log (optionnel)")
    return p.parse_args()


def _auto_retrain_loop(ticker: str, every_hours: float, stop_event: threading.Event) -> None:
    """Thread de réentraînement automatique."""
    interval_sec = every_hours * 3600
    logger.info(f"[AutoRetrain] Réentraînement automatique toutes les {every_hours}h pour {ticker}")

    # Toujours entraîner au démarrage (modèle peut être incompatible avec nouvelles features)
    _retrain(ticker)

    while not stop_event.wait(timeout=interval_sec):
        _retrain(ticker)


def _retrain(ticker: str) -> None:
    """Lance le réentraînement dans un subprocess séparé — évite le deadlock _ModuleLock sklearn."""
    import os
    script = Path(__file__).resolve().parent / "retrain_agent.py"
    try:
        logger.info(f"[AutoRetrain] Démarrage subprocess réentraînement — {ticker}")
        result = subprocess.run(
            [sys.executable, str(script), "--tickers", ticker],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        output = (result.stdout + result.stderr).strip()[-2000:]
        if result.returncode == 0 or any(k in output.lower() for k in ["termin", "best=", "replaced"]):
            logger.info(f"[AutoRetrain] Réentraînement terminé — {ticker}")
        else:
            logger.error(f"[AutoRetrain] Réentraînement échoué (code {result.returncode}) : {output[-500:]}")
    except subprocess.TimeoutExpired:
        logger.error(f"[AutoRetrain] Timeout (5 min) — réentraînement annulé")
    except Exception as exc:
        logger.error(f"[AutoRetrain] Échec réentraînement : {exc}")


def main() -> None:
    args = _parse_args()
    ticker = args.ticker.upper()

    # Logs vers fichier
    log_path = Path(args.log_file) if args.log_file else Path(__file__).parent / "logs" / "agent_subprocess.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_path), rotation="10 MB", encoding="utf-8", level="DEBUG")

    # Tuer tout doublon/zombie pour ce ticker avant de démarrer
    import os, json
    _my_pid = os.getpid()
    try:
        import psutil
        for _proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                _cmd = " ".join(_proc.info["cmdline"] or [])
                if "run_agent" in _cmd and ticker in _cmd and _proc.info["pid"] != _my_pid:
                    logger.warning(f"[run_agent] Zombie détecté PID {_proc.info['pid']} — kill")
                    _proc.kill()
            except Exception:
                pass
    except ImportError:
        pass

    # Enregistre le PID réel dans le fichier d'état (multi-agents : mise à jour partielle)
    state_file = Path(__file__).parent / "agent" / "memory_store" / "agent_process.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        _st = json.loads(state_file.read_text())
        if "agents" not in _st:
            _st = {"agents": {}}
    except Exception:
        _st = {"agents": {}}
    _st["agents"][ticker] = {"running": True, "pid": _my_pid}
    state_file.write_text(json.dumps(_st))

    if ticker not in AGENT_ALLOWED_TICKERS:
        logger.warning(f"{ticker} n'est pas dans AGENT_ALLOWED_TICKERS ({AGENT_ALLOWED_TICKERS}) — on continue quand même.")

    agent = TradingAgent(ticker=ticker, interval_sec=args.interval)

    # Thread de réentraînement automatique
    stop_retrain = threading.Event()
    if args.retrain_hours > 0:
        retrain_thread = threading.Thread(
            target=_auto_retrain_loop,
            args=(ticker, args.retrain_hours, stop_retrain),
            daemon=True,
            name="auto-retrain",
        )
        retrain_thread.start()

    _state_file = Path(__file__).resolve().parent / "agent" / "memory_store" / "agent_process.json"

    def _stop(sig, frame):
        logger.info("[run_agent] Arrêt demandé — fermeture des positions en cours...")
        stop_retrain.set()
        agent.stop()
        agent.close_all_positions()   # ferme LONG ou SHORT avant de quitter
        try:
            _st2 = json.loads(_state_file.read_text())
            if "agents" in _st2:
                _st2["agents"].pop(ticker, None)
            else:
                _st2 = {"agents": {}}
            _state_file.write_text(json.dumps(_st2))
        except Exception:
            pass
        _retrain(ticker)
        logger.info("[run_agent] Arrêt propre terminé.")

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    # Enregistre le PID réel + started_at dans le fichier d'état dès que l'agent est prêt
    try:
        _st3 = json.loads(_state_file.read_text())
        if "agents" not in _st3:
            _st3 = {"agents": {}}
        _st3["agents"][ticker] = {"running": True, "pid": os.getpid(), "started_at": time.time()}
        _state_file.write_text(json.dumps(_st3))
        logger.info(f"[run_agent] PID {os.getpid()} enregistré pour {ticker}")
    except Exception as _e:
        logger.warning(f"[run_agent] Impossible d'écrire le PID : {_e}")

    logger.info(f"[run_agent] Agent démarré — {ticker} | intervalle={args.interval}s | retrain={args.retrain_hours}h")

    agent.run()
    stop_retrain.set()
    logger.info("[run_agent] Agent arrêté.")


if __name__ == "__main__":
    main()
