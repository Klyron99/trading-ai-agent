"""
Agent de trading sur annonces économiques — XAUUSD via MT5 DEMO.

Cycle :
  1. Rafraîchit le calendrier économique toutes les heures (ou toutes les 30s
     si un event USD important est prévu dans les 15 prochaines minutes)
  2. Surveille les annonces imminentes (fenêtre -10min / +5min)
  3. Dès qu'une annonce paraît avec actual vs forecast connu :
     → Détermine la direction (gold BUY ou SELL)
     → Entre en position via MT5 DEMO le plus vite possible
     → Stop-loss 0.8%, Take-profit 2.0%
     → Sort automatiquement ou laisse le TP/SL gérer
  4. Logue tout dans la DB (table decisions + economic_events)

Garde-fous :
  - MT5 DEMO uniquement (vérification compte)
  - 1 seule position ouverte à la fois sur XAUUSD
  - Pause 30 min après chaque trade (évite sur-trading post-annonce)
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger

from agent import memory as mem
from data.economic_calendar import (
    fetch_upcoming_events,
    get_imminent_events,
    mark_trade_taken,
    _get_gold_reaction,
    _DB_PATH,
)
from execution.mt5_broker import MT5DemoBroker

TICKER = "XAUUSD"
LOTS   = 0.01           # 1 micro-lot
SL_PCT = 0.008          # Stop-loss 0.8% (élargi pour éviter stop-hunt post-annonce)
TP_PCT = 0.020          # Take-profit 2.0% (les annonces font ±0.5-1.5%)
COOLDOWN_MIN    = 30    # Pas de nouveau trade pendant 30 min
CALENDAR_REFRESH_NORMAL = 3600   # Refresh calendrier : toutes les heures
CALENDAR_REFRESH_FAST   = 30     # Refresh calendrier : toutes les 30s si event imminent
FAST_MODE_WINDOW_MIN    = 15     # Activer fast mode si event dans les 15 min
TICK_NORMAL_SEC  = 30            # Tick normal : 30 secondes
TICK_FAST_SEC    = 10            # Tick rapide : 10 secondes (mode event imminent)


class NewsTradingAgent:
    """Agent qui trade XAUUSD sur les annonces économiques via MT5 DEMO."""

    def __init__(self, mt5_login: int | None = None, mt5_password: str | None = None,
                 mt5_server: str | None = None) -> None:
        mem.init_db()
        self._broker = MT5DemoBroker(
            login=mt5_login,
            password=mt5_password,
            server=mt5_server,
        )
        self._running = True
        self._last_trade_ts: float = 0.0
        self._last_calendar_refresh: float = 0.0
        self._fast_mode: bool = False

        logger.info(f"[NewsAgent] Démarré — XAUUSD | lots={LOTS} | SL={SL_PCT:.1%} TP={TP_PCT:.1%}")

    def run(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"[NewsAgent] Erreur : {exc}")

            # Tick rapide si event imminent, sinon tick normal
            sleep_sec = TICK_FAST_SEC if self._fast_mode else TICK_NORMAL_SEC
            time.sleep(sleep_sec)

    def stop(self) -> None:
        self._running = False
        self._broker.shutdown()
        logger.info("[NewsAgent] Arrêté.")

    def _has_imminent_events_ahead(self, within_min: int = 15) -> bool:
        """Vérifie si un event USD important arrive dans les X prochaines minutes (sans actual encore)."""
        now = datetime.now(timezone.utc)
        window_end = (now + timedelta(minutes=within_min)).strftime("%Y-%m-%dT%H:%M")
        window_start = now.strftime("%Y-%m-%dT%H:%M")
        con = sqlite3.connect(str(_DB_PATH))
        rows = con.execute(
            "SELECT COUNT(*) FROM economic_events WHERE ts BETWEEN ? AND ? AND importance >= 2",
            (window_start, window_end)
        ).fetchone()
        con.close()
        return (rows[0] or 0) > 0

    def _tick(self) -> None:
        now = time.time()

        # --- Mode fast : rafraîchit le calendrier très fréquemment ---
        # Active fast mode si un event important arrive dans les 15 prochaines minutes
        self._fast_mode = self._has_imminent_events_ahead(FAST_MODE_WINDOW_MIN)
        refresh_interval = CALENDAR_REFRESH_FAST if self._fast_mode else CALENDAR_REFRESH_NORMAL

        if now - self._last_calendar_refresh > refresh_interval:
            fetch_upcoming_events(days_ahead=1)
            self._last_calendar_refresh = now
            if self._fast_mode:
                logger.info("[NewsAgent] MODE RAPIDE — rafraîchissement calendrier (event imminent)")

        # Cooldown post-trade
        if now - self._last_trade_ts < COOLDOWN_MIN * 60:
            remaining = int((COOLDOWN_MIN * 60 - (now - self._last_trade_ts)) / 60)
            logger.debug(f"[NewsAgent] Cooldown actif — {remaining} min restantes")
            return

        # Vérifie si une position est déjà ouverte
        positions = self._broker.get_positions(TICKER)
        if positions:
            logger.debug(f"[NewsAgent] Position ouverte sur {TICKER} — attente sortie")
            return

        # --- Cherche annonce avec actual connu (fenêtre -10min / +5min) ---
        # La fenêtre large en arrière (10min) permet de capter un actual
        # publié juste après l'heure si le précédent tick n'avait pas encore les données
        events = get_imminent_events(window_minutes=5, lookback_minutes=10)
        if not events:
            return

        for event in events:
            reaction = event.get("gold_reaction")

            # Recalcule si gold_reaction pas encore en DB (actual vient d'arriver)
            if reaction not in ("buy", "sell"):
                if event.get("actual") is not None and event.get("forecast") is not None:
                    reaction = _get_gold_reaction(
                        event["name"], event["actual"], event["forecast"]
                    )
                if reaction not in ("buy", "sell"):
                    continue

            self._trade(event, reaction)
            break  # 1 seul trade par tick

    def _trade(self, event: dict, direction: str) -> None:
        price = self._broker.get_price(TICKER)
        if price is None:
            logger.error("[NewsAgent] Prix XAUUSD indisponible")
            return

        actual   = event.get("actual")
        forecast = event.get("forecast")
        surprise_pct = ((actual - forecast) / abs(forecast) * 100) if forecast else 0
        importance = event.get("importance", 1)

        # Taille proportionnelle à l'importance (3★ = LOTS, 2★ = 2/3 LOTS, 1★ = 1/3 LOTS)
        lots = round(LOTS * importance / 3, 2) or 0.01

        try:
            result = self._broker.submit_market_order(
                TICKER, direction, lots,
                sl_pct=SL_PCT, tp_pct=TP_PCT,
                comment=f"News:{event['name'][:20]}"
            )
        except Exception as exc:
            logger.error(f"[NewsAgent] Ordre refusé : {exc}")
            return

        self._last_trade_ts = time.time()
        mark_trade_taken(event["event_id"])

        direction_emoji = "BUY" if direction == "buy" else "SELL"
        sl_price = price * (1 - SL_PCT) if direction == "buy" else price * (1 + SL_PCT)
        tp_price = price * (1 + TP_PCT) if direction == "buy" else price * (1 - TP_PCT)

        reason = (
            f"NEWS TRADE — {event['name']} | "
            f"Actual={actual} Forecast={forecast} Surprise={surprise_pct:+.2f}% | "
            f"Direction: {direction_emoji} | Importance: {'★' * importance} | "
            f"SL=${sl_price:.2f} TP=${tp_price:.2f}"
        )

        mem.log_decision(
            ticker=TICKER,
            action=direction_emoji,
            confidence=0.70 + importance * 0.05,
            strategy="NewsTrading",
            price=price,
            ml_prob=None,
            reason=reason,
        )

        logger.success(
            f"[NewsAgent] {direction_emoji} {lots} XAUUSD @ ${price:.2f} | "
            f"{event['name']} | Surprise {surprise_pct:+.2f}% | "
            f"SL=${sl_price:.2f} TP=${tp_price:.2f}"
        )

    def get_status(self) -> dict:
        acct = self._broker.get_account()
        positions = self._broker.get_positions(TICKER)
        cooldown_left = max(0, int((COOLDOWN_MIN * 60 - (time.time() - self._last_trade_ts)) / 60))
        return {
            "running": self._running,
            "balance": acct.get("balance", 0),
            "demo": acct.get("demo", True),
            "positions": positions,
            "cooldown_min": cooldown_left,
            "fast_mode": self._fast_mode,
            "connected": self._broker.is_connected(),
        }
