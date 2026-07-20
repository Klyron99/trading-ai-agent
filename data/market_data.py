"""
Téléchargement et mise en cache des données de marché via yfinance.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf
from loguru import logger
from pathlib import Path

from config.settings import DATA_CACHE_DIR, DATA_START_DATE, DATA_END_DATE


def download_ohlcv(
    ticker: str,
    start: str = DATA_START_DATE,
    end: str = DATA_END_DATE,
    use_cache: bool = True,
    interval: str = "1h",
) -> pd.DataFrame:
    """Télécharge les données OHLCV d'un ticker et les met en cache CSV.

    Args:
        ticker: Symbole boursier (ex. "AAPL").
        start: Date de début au format YYYY-MM-DD.
        end: Date de fin au format YYYY-MM-DD.
        use_cache: Si True, recharge depuis le cache si disponible.

    Returns:
        DataFrame avec colonnes Open, High, Low, Close, Volume, index DatetimeIndex.
    """
    cache_path: Path = DATA_CACHE_DIR / f"{ticker}_{start}_{end}_{interval}.csv"

    # Cache valide 1h pour données horaires, 4h pour données journalières
    import time as _time
    cache_ttl = 3600 if interval == "1h" else 4 * 3600
    cache_stale = (
        not cache_path.exists()
        or (_time.time() - cache_path.stat().st_mtime) > cache_ttl
    )

    if use_cache and not cache_stale:
        logger.info(f"[{ticker}] Chargement depuis le cache : {cache_path}")
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        return df

    logger.info(f"[{ticker}] Téléchargement via yfinance ({start} → {end}, interval={interval})")
    # yfinance limite les données horaires à 730 jours max
    if interval == "1h":
        import datetime as _dt
        _start = max(
            _dt.datetime.strptime(start, "%Y-%m-%d"),
            _dt.datetime.now() - _dt.timedelta(days=720)
        ).strftime("%Y-%m-%d")
    else:
        _start = start
    raw = yf.download(ticker, start=_start, end=end, interval=interval,
                      auto_adjust=True, progress=False)

    if raw.empty:
        raise ValueError(f"Aucune donnée reçue pour {ticker} sur la période {start}/{end}.")

    # Normalise les colonnes (yfinance peut retourner un MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Date"
    df.to_csv(cache_path)
    logger.success(f"[{ticker}] {len(df)} barres sauvegardées dans {cache_path}")
    return df


def load_multiple(
    tickers: list[str],
    start: str = DATA_START_DATE,
    end: str = DATA_END_DATE,
) -> dict[str, pd.DataFrame]:
    """Télécharge et retourne les données pour plusieurs tickers.

    Args:
        tickers: Liste de symboles boursiers.
        start: Date de début.
        end: Date de fin.

    Returns:
        Dictionnaire {ticker: DataFrame}.
    """
    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            data[ticker] = download_ohlcv(ticker, start=start, end=end)
        except Exception as exc:
            logger.error(f"[{ticker}] Échec du téléchargement : {exc}")
    return data
