"""
Données macro pour enrichir les features BTC :
- DXY  (Dollar Index)    → inverse de BTC quand dollar monte
- SP500 (^GSPC)          → risk-on/risk-off
- Gold  (GC=F)           → refuge vs BTC
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import pickle

import pandas as pd
import yfinance as yf
from loguru import logger

_CACHE_DIR = Path(__file__).parent / "_cache"
_CACHE_TTL_H = 12


def _cache_path(name: str) -> Path:
    return _CACHE_DIR / f"macro_{name}.pkl"


def _get_cached(name: str) -> pd.Series | None:
    p = _cache_path(name)
    try:
        if p.exists():
            ts, data = pickle.loads(p.read_bytes())
            if datetime.fromisoformat(ts) > datetime.now() - timedelta(hours=_CACHE_TTL_H):
                return data
    except Exception:
        pass
    return None


def _save(name: str, s: pd.Series) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(name).write_bytes(pickle.dumps((datetime.now().isoformat(), s)))
    except Exception:
        pass


def _download_close(ticker: str, start: str = "2015-01-01") -> pd.Series:
    cached = _get_cached(ticker)
    if cached is not None:
        return cached
    try:
        df = yf.download(ticker, start=start, auto_adjust=True,
                         progress=False, threads=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        s = df["Close"].dropna()
        s.index = pd.to_datetime(s.index).normalize()
        _save(ticker, s)
        logger.info(f"[Macro] {ticker} : {len(s)} barres")
        return s
    except Exception as exc:
        logger.warning(f"[Macro] {ticker} échec : {exc}")
        return pd.Series(dtype=float)


def get_macro_daily() -> pd.DataFrame:
    """Retourne DataFrame journalier avec DXY, SP500, Gold (returns journaliers + niveaux normalisés)."""
    dxy   = _download_close("DX-Y.NYB")
    sp500 = _download_close("^GSPC")
    gold  = _download_close("GC=F")

    macro = pd.DataFrame({
        "dxy":   dxy,
        "sp500": sp500,
        "gold":  gold,
    }).dropna(how="all")

    # Returns journaliers
    for col in ["dxy", "sp500", "gold"]:
        if col in macro.columns:
            macro[f"{col}_ret1d"]   = macro[col].pct_change(1)
            macro[f"{col}_ret5d"]   = macro[col].pct_change(5)
            macro[f"{col}_vs_ma20"] = macro[col] / macro[col].rolling(20).mean() - 1

    # Rolling correlation DXY vs BTC n'est pas possible ici (pas de BTC), on garde les niveaux
    return macro
