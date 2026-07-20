"""
Système de logs des signaux et des trades.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from config.settings import LOGS_DIR


def setup_logger(log_file: str = "trading.log") -> None:
    """Configure Loguru pour écrire dans un fichier rotatif.

    Args:
        log_file: Nom du fichier de log dans le répertoire logs/.
    """
    log_path = LOGS_DIR / log_file
    logger.add(
        str(log_path),
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        encoding="utf-8",
    )
    logger.info(f"Logger initialisé → {log_path}")


def export_trades_csv(orders: list[dict], filename: str = "trades_export.csv") -> Path:
    """Exporte la liste des ordres en CSV.

    Args:
        orders: Liste de dictionnaires avec les champs de l'ordre.
        filename: Nom du fichier CSV de sortie.

    Returns:
        Chemin vers le fichier créé.
    """
    output_path = LOGS_DIR / filename
    if not orders:
        logger.warning("Aucun ordre à exporter.")
        return output_path

    df = pd.DataFrame(orders)
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.success(f"Trades exportés : {output_path} ({len(df)} lignes)")
    return output_path


def log_signal(ticker: str, date: datetime, signal: int, price: float) -> None:
    """Enregistre un signal en log.

    Args:
        ticker: Symbole boursier.
        date: Date du signal.
        signal: Valeur du signal (1, -1, 0).
        price: Prix à la date du signal.
    """
    action = {1: "ACHAT", -1: "VENTE", 0: "NEUTRE"}.get(signal, "?")
    logger.debug(f"[SIGNAL] {ticker} | {date.date()} | {action} | @ {price:.2f}")
