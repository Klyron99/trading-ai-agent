"""
Fear & Greed Index — Alternative.me API (gratuit, pas de clé requise).
Retourne un DataFrame journalier avec la valeur 0-100.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from loguru import logger

_CACHE_PATH = Path(__file__).parent / "_cache" / "fear_greed.json"
_CACHE_TTL_H = 6  # recharge toutes les 6h


def _load_cache() -> dict | None:
    try:
        if _CACHE_PATH.exists():
            data = json.loads(_CACHE_PATH.read_text())
            if datetime.fromisoformat(data["ts"]) > datetime.now() - timedelta(hours=_CACHE_TTL_H):
                return data["records"]
    except Exception:
        pass
    return None


def _save_cache(records: list) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({"ts": datetime.now().isoformat(), "records": records}))
    except Exception:
        pass


def get_fear_greed(limit: int = 1000) -> pd.DataFrame:
    """Retourne un DataFrame journalier indexé par date avec colonne 'fear_greed' (0-100)."""
    cached = _load_cache()
    if cached and len(cached) >= limit * 0.9:
        records = cached
    else:
        try:
            url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            records = resp.json()["data"]
            _save_cache(records)
            logger.info(f"[FearGreed] {len(records)} jours téléchargés")
        except Exception as exc:
            logger.warning(f"[FearGreed] Échec téléchargement : {exc}")
            if cached:
                records = cached
            else:
                return pd.DataFrame(columns=["fear_greed"])

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    df["fear_greed"] = df["value"].astype(float)
    df = df.set_index("date")[["fear_greed"]].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def get_fear_greed_today() -> float | None:
    """Retourne la valeur F&G d'aujourd'hui (ou None si indisponible)."""
    df = get_fear_greed(limit=2)
    if df.empty:
        return None
    return float(df["fear_greed"].iloc[-1])
