"""
Point d'entrée pour réentraîner manuellement les modèles ML de l'agent.

Usage :
    python retrain_agent.py
    python retrain_agent.py --tickers AAPL MSFT SPY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

from agent.learning_loop import run_learning_loop
from config.settings import AGENT_ALLOWED_TICKERS


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Réentraînement des modèles de l'agent")
    p.add_argument(
        "--tickers", nargs="*", default=None,
        help="Tickers à réentraîner (défaut : AGENT_ALLOWED_TICKERS)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    tickers = [t.upper() for t in args.tickers] if args.tickers else AGENT_ALLOWED_TICKERS

    logger.info(f"[retrain_agent] Réentraînement pour : {tickers}")
    run_learning_loop(tickers)
    logger.info("[retrain_agent] Terminé.")


if __name__ == "__main__":
    main()
