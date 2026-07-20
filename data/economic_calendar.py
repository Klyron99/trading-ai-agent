"""
Calendrier économique — événements macro qui impactent XAUUSD.

Sources :
- Finnhub API (gratuit, clé dans .env FINNHUB_API_KEY)
- Fallback : calendrier statique des prochains événements connus

Impact gold par événement :
  actual > forecast → POSITIF pour USD → NÉGATIF pour gold (SELL)
  actual < forecast → NÉGATIF pour USD → POSITIF pour gold (BUY)
  Exceptions : CPI élevé = mauvais USD mais bon pour gold (hedge inflation)
"""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

import requests
from loguru import logger

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "trading_memory.db"
_FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")

# Impact sur XAUUSD selon la direction de la surprise
# "positive_surprise" = actual > forecast
# gold_reaction: "buy" = gold monte, "sell" = gold baisse, "none" = neutre
GOLD_IMPACT_MAP: dict[str, dict] = {
    # Inflation → surprise basse = Fed dovish = dollar faible = gold monte
    "CPI":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Core CPI":               {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "PCE":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Core PCE":               {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "PPI":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    # Emploi → surprise haute = USD fort = gold baisse
    "NFP":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Non-Farm Payrolls":      {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Unemployment Rate":      {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 2},
    "ADP":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Jobless Claims":         {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 2},
    "Initial Jobless":        {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 2},
    "Continued Jobless":      {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 2},
    "JOLTs":                  {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    # Fed / taux
    "Fed Interest Rate":      {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "FOMC":                   {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Fed Chair":              {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    # Croissance → surprise haute = risk-on = gold baisse
    "GDP":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 3},
    "Retail Sales":           {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Core Retail Sales":      {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "ISM Manufacturing":      {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "ISM Services":           {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "PMI":                    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Philly Fed":             {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Empire State":           {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Business Inventories":   {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Durable Goods":          {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Trade Balance":          {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    # Immobilier
    "Housing":                {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Home Sales":             {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "NAHB":                   {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Building Permits":       {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Pending Home":           {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    # Sentiment
    "Consumer Confidence":    {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    "Consumer Sentiment":     {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 1},
    "Michigan":               {"positive_surprise": "sell", "negative_surprise": "buy",  "importance": 2},
    # Pétrole (corrélé gold)
    "Crude Oil":              {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 2},
    "EIA":                    {"positive_surprise": "buy",  "negative_surprise": "sell", "importance": 1},
}


def _init_calendar_table() -> None:
    con = sqlite3.connect(str(_DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS economic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            ts TEXT,
            name TEXT,
            country TEXT,
            actual REAL,
            forecast REAL,
            previous REAL,
            importance INTEGER,
            gold_reaction TEXT,
            trade_taken INTEGER DEFAULT 0,
            trade_result REAL
        )
    """)
    con.commit()
    con.close()


def _get_gold_reaction(event_name: str, actual: float | None,
                       forecast: float | None) -> str | None:
    """Retourne 'buy', 'sell' ou None selon la surprise."""
    if actual is None or forecast is None:
        return None

    impact = None
    for key, val in GOLD_IMPACT_MAP.items():
        if key.lower() in event_name.lower():
            impact = val
            break

    if impact is None:
        return None

    surprise = actual - forecast
    if abs(surprise) < 1e-6:
        return None  # pas de surprise

    return impact["positive_surprise"] if surprise > 0 else impact["negative_surprise"]


def fetch_upcoming_events(days_ahead: int = 7) -> list[dict]:
    """Récupère les événements économiques via Forex Factory (gratuit)."""
    _init_calendar_table()
    events = _fetch_forex_factory()
    if events:
        _upsert_events(events)
        logger.info(f"[Calendar] {len(events)} événements gold-relevant récupérés (Forex Factory)")
        return events
    logger.warning("[Calendar] Forex Factory indisponible — données simulées")
    return _get_simulated_events()


def _fetch_forex_factory() -> list[dict]:
    """Scrape le calendrier Forex Factory pour la semaine en cours."""
    try:
        from bs4 import BeautifulSoup
        import re

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        now = datetime.now(timezone.utc)
        url = f"https://www.forexfactory.com/calendar?week=this.week"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("tr.calendar__row")

        events = []
        current_date = now.strftime("%Y-%m-%d")

        for row in rows:
            # Date (peut être vide si même jour que la ligne précédente)
            date_cell = row.select_one(".calendar__date")
            if date_cell and date_cell.get_text(strip=True):
                raw_date = date_cell.get_text(strip=True)
                try:
                    # Format FF : "Tue Jul 15"
                    parsed = datetime.strptime(f"{raw_date} {now.year}", "%a %b %d %Y")
                    current_date = parsed.strftime("%Y-%m-%d")
                except Exception:
                    pass

            # Heure
            time_cell = row.select_one(".calendar__time")
            raw_time = time_cell.get_text(strip=True) if time_cell else ""
            if not raw_time or raw_time.lower() in ("all day", "tentative", ""):
                raw_time = "12:00am"
            try:
                t = datetime.strptime(raw_time, "%I:%M%p")
                ts = f"{current_date}T{t.strftime('%H:%M')}:00"
            except Exception:
                ts = f"{current_date}T12:00:00"

            # Pays
            country_cell = row.select_one(".calendar__currency")
            country = country_cell.get_text(strip=True) if country_cell else ""
            if country.upper() != "USD":
                continue

            # Nom
            name_cell = row.select_one(".calendar__event-title")
            name = name_cell.get_text(strip=True) if name_cell else ""
            if not name:
                continue

            # Importance (icônes)
            impact_cell = row.select_one(".calendar__impact")
            impact_icons = impact_cell.select("span") if impact_cell else []
            importance = len([i for i in impact_icons if "high" in str(i).lower()]) or \
                         len([i for i in impact_icons if "medium" in str(i).lower()]) or 1
            importance = min(importance, 3)

            # Cherche infos gold dans la map (peut être None pour événements moins connus)
            impact_info = next(
                (v for k, v in GOLD_IMPACT_MAP.items() if k.lower() in name.lower()),
                None
            )
            # Garde tous les événements importance >= 1 (on affiche tout, réaction gold si connue)
            # importance depuis Forex Factory déjà calculée ci-dessus

            # Actual / Forecast / Previous
            def _parse_num(cell_cls: str) -> float | None:
                cell = row.select_one(f".calendar__{cell_cls}")
                if not cell:
                    return None
                txt = cell.get_text(strip=True).replace("%", "").replace("K", "000").replace("M", "000000").replace("B", "000000000")
                try:
                    return float(txt)
                except Exception:
                    return None

            actual   = _parse_num("actual")
            forecast = _parse_num("forecast")
            previous = _parse_num("previous")
            reaction = _get_gold_reaction(name, actual, forecast)

            # Importance : utilise la map si disponible, sinon celle de ForexFactory
            final_importance = impact_info["importance"] if impact_info else importance

            event_id = f"FF_{current_date}_{name[:30].replace(' ','_')}"
            events.append({
                "event_id": event_id,
                "ts": ts,
                "name": name,
                "country": "USD",
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "importance": final_importance,
                "gold_reaction": reaction,
            })

        return events

    except Exception as exc:
        logger.error(f"[Calendar] Forex Factory erreur : {exc}")
        return []


def get_imminent_events(window_minutes: int = 5, lookback_minutes: int = 10) -> list[dict]:
    """
    Retourne les événements dans la fenêtre [-lookback_minutes, +window_minutes]
    dont l'actual est connu et le trade pas encore pris.

    lookback_minutes=10 permet de capter un actual publié quelques secondes après
    l'heure officielle, si le tick précédent n'avait pas encore les données.
    """
    _init_calendar_table()
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=lookback_minutes)).strftime("%Y-%m-%dT%H:%M")
    window_end   = (now + timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M")

    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT * FROM economic_events
        WHERE ts BETWEEN ? AND ?
        AND trade_taken = 0
        AND gold_reaction IS NOT NULL
        ORDER BY importance DESC, ts ASC
    """, (window_start, window_end)).fetchall()
    con.close()

    return [dict(r) for r in rows]


def mark_trade_taken(event_id: str, result: float | None = None) -> None:
    con = sqlite3.connect(str(_DB_PATH))
    con.execute(
        "UPDATE economic_events SET trade_taken=1, trade_result=? WHERE event_id=?",
        (result, event_id)
    )
    con.commit()
    con.close()


def _upsert_events(events: list[dict]) -> None:
    con = sqlite3.connect(str(_DB_PATH))
    for e in events:
        con.execute("""
            INSERT INTO economic_events
                (event_id, ts, name, country, actual, forecast, previous, importance, gold_reaction)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET
                actual=excluded.actual,
                forecast=excluded.forecast,
                gold_reaction=excluded.gold_reaction
        """, (e["event_id"], e["ts"], e["name"], e["country"],
              e["actual"], e["forecast"], e["previous"],
              e["importance"], e["gold_reaction"]))
    con.commit()
    con.close()


def _get_simulated_events() -> list[dict]:
    """Événements simulés pour tester sans clé API."""
    now = datetime.now(timezone.utc)
    return [
        {
            "event_id": "SIM_NFP_001",
            "ts": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:00"),
            "name": "Non-Farm Payrolls",
            "country": "US",
            "actual": None,
            "forecast": 180000,
            "previous": 175000,
            "importance": 3,
            "gold_reaction": None,
        },
        {
            "event_id": "SIM_CPI_001",
            "ts": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:00"),
            "name": "CPI m/m",
            "country": "US",
            "actual": None,
            "forecast": 0.3,
            "previous": 0.2,
            "importance": 3,
            "gold_reaction": None,
        },
    ]
