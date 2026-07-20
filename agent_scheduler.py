"""
Scheduler d'agents — gère le démarrage/arrêt automatique selon les horaires.

Règles :
  BTC-USD  : 24h/24, 7j/7 (toujours actif)
  SPY      : 15h30 → 22h00 Paris (13h30 → 20h00 UTC), jours de semaine uniquement

Lancement :
  python agent_scheduler.py
  python agent_scheduler.py --dry-run   (affiche les décisions sans agir)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger
from dashboard.agent_state import start_agent, stop_agent, get_all_agents_status

# ── Configuration ─────────────────────────────────────────────────────────────
PARIS_OFFSET = timedelta(hours=2)          # UTC+2 en été (CEST)

SCHEDULE: list[dict] = [
    {
        "ticker":    "BTC-USD",
        "interval":  60,
        "always_on": True,                 # tourne 24/7, ne s'arrête jamais
        "weekdays":  list(range(7)),
        "start_h":   0,  "start_m": 0,
        "stop_h":    23, "stop_m":  59,
    },
    {
        "ticker":    "SPY",
        "interval":  60,
        "always_on": False,
        "weekdays":  [0, 1, 2, 3, 4],     # lundi–vendredi
        "start_h":   15, "start_m": 30,   # 15h30 Paris
        "stop_h":    22, "stop_m":  0,    # 22h00 Paris
    },
]

CHECK_INTERVAL_S = 30   # vérification toutes les 30 secondes
# ──────────────────────────────────────────────────────────────────────────────


def _paris_now() -> datetime:
    return datetime.now(timezone.utc) + PARIS_OFFSET


def _should_run(cfg: dict, now: datetime) -> bool:
    if cfg["always_on"]:
        return True
    if now.weekday() not in cfg["weekdays"]:
        return False
    start = now.replace(hour=cfg["start_h"], minute=cfg["start_m"], second=0, microsecond=0)
    stop  = now.replace(hour=cfg["stop_h"],  minute=cfg["stop_m"],  second=0, microsecond=0)
    return start <= now < stop


def _is_running(ticker: str) -> bool:
    return ticker in get_all_agents_status()


def run(dry_run: bool = False) -> None:
    logger.info(f"[Scheduler] Démarré — dry_run={dry_run}")

    # État précédent pour ne logger que les changements
    prev_state: dict[str, bool] = {}

    while True:
        now = _paris_now()
        active = get_all_agents_status()

        for cfg in SCHEDULE:
            ticker  = cfg["ticker"]
            wanted  = _should_run(cfg, now)
            running = ticker in active

            if wanted and not running:
                if prev_state.get(ticker) is not False:   # évite le log répété
                    logger.info(f"[Scheduler] {ticker} → DÉMARRAGE  ({now.strftime('%H:%M')} Paris)")
                prev_state[ticker] = False
                if not dry_run:
                    ok, msg = start_agent(ticker, cfg["interval"])
                    logger.info(f"[Scheduler] {msg}")
                else:
                    logger.info(f"[Scheduler] [DRY-RUN] start_agent({ticker})")
                prev_state[ticker] = True

            elif not wanted and running:
                if prev_state.get(ticker) is not True:
                    logger.info(f"[Scheduler] {ticker} → ARRÊT     ({now.strftime('%H:%M')} Paris)")
                prev_state[ticker] = True
                if not dry_run:
                    ok, msg = stop_agent(ticker)
                    logger.info(f"[Scheduler] {msg}")
                else:
                    logger.info(f"[Scheduler] [DRY-RUN] stop_agent({ticker})")
                prev_state[ticker] = False

            else:
                # Aucun changement — juste mettre à jour l'état connu
                prev_state[ticker] = running

        time.sleep(CHECK_INTERVAL_S)


def main() -> None:
    p = argparse.ArgumentParser(description="Scheduler d'agents de trading")
    p.add_argument("--dry-run", action="store_true", help="Simulation sans action réelle")
    args = p.parse_args()

    log_path = Path(__file__).parent / "logs" / "scheduler.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_path), rotation="5 MB", encoding="utf-8", level="INFO")

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
