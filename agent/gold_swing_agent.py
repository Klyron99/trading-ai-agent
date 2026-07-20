"""
Agent Swing Gold — XAUUSD via MT5 DEMO.

Fréquence : vérifie le signal toutes les 4H (à chaque clôture de bougie 4H).
Stratégie : GoldSwingStrategy (tendance daily + pullback 4H + RSI + ATR).
Exécution : MT5DemoBroker (ou simulation si MT5 non connecté).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from loguru import logger

from agent import memory as mem
from execution.mt5_broker import MT5DemoBroker
from strategies.gold_swing_strategy import GoldSwingStrategy

TICKER     = "XAUUSD"
LOTS       = 0.01          # 1 micro-lot par défaut
CHECK_EVERY_SEC = 4 * 3600  # toutes les 4H
MIN_CONFIDENCE  = 0.65


class GoldSwingAgent:
    """Agent swing sur XAUUSD — entre sur pullbacks en direction de la tendance."""

    def __init__(self, mt5_login=None, mt5_password=None, mt5_server=None) -> None:
        mem.init_db()
        self._broker   = MT5DemoBroker(login=mt5_login, password=mt5_password, server=mt5_server)
        self._strategy = GoldSwingStrategy()
        self._running  = True
        logger.info("[SwingAgent] Démarré — XAUUSD swing multi-timeframe")

    def run(self) -> None:
        import signal as _signal
        _signal.signal(_signal.SIGINT,  lambda s, f: self._graceful_stop())
        _signal.signal(_signal.SIGTERM, lambda s, f: self._graceful_stop())
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"[SwingAgent] Erreur : {exc}")
            time.sleep(CHECK_EVERY_SEC)

    def _graceful_stop(self) -> None:
        logger.info("[SwingAgent] Arrêt demandé — fermeture des positions...")
        self._running = False
        self._close_all_positions()
        self._broker.shutdown()
        logger.info("[SwingAgent] Arrêt propre terminé.")

    def stop(self) -> None:
        self._graceful_stop()

    def _close_all_positions(self) -> None:
        positions = self._broker.get_positions(TICKER)
        if not positions:
            logger.info("[SwingAgent] Aucune position ouverte à fermer.")
            return
        price = self._broker.get_price(TICKER)
        for pos in positions:
            side = pos.get("side", "buy")
            qty  = pos.get("qty", 0.01)
            close_side = "sell" if side == "buy" else "buy"
            try:
                self._broker.submit_market_order(TICKER, close_side, qty, comment="ShutdownClose")
                mem.log_decision(
                    ticker=TICKER, action="COVER" if side == "sell" else "SELL",
                    confidence=1.0, strategy="SHUTDOWN_CLOSE",
                    price=price or 0, ml_prob=None,
                    reason="Fermeture automatique à l'arrêt de l'agent swing",
                )
                logger.success(f"[SwingAgent] Position fermée @ ${price:.2f}" if price else "[SwingAgent] Position fermée")
            except Exception as exc:
                logger.error(f"[SwingAgent] Erreur fermeture : {exc}")

    def _tick(self) -> None:
        logger.info("[SwingAgent] Analyse en cours...")
        signal = self._strategy.analyze()

        if signal.action == "HOLD" or signal.confidence < MIN_CONFIDENCE:
            logger.info(
                f"[SwingAgent] HOLD — {signal.reason} | "
                f"Tendance={signal.daily_trend} | RSI={signal.rsi_4h} | Conf={signal.confidence:.0%}"
            )
            mem.log_decision(
                ticker=TICKER, action="HOLD",
                confidence=signal.confidence,
                strategy="GoldSwing",
                price=signal.price,
                ml_prob=None,
                reason=signal.reason,
            )
            return

        # Vérifie si une position est déjà ouverte
        positions = self._broker.get_positions(TICKER)
        if positions:
            logger.info(f"[SwingAgent] Position déjà ouverte — pas de nouvel ordre")
            return

        # Soumet l'ordre
        sl_pct = abs(signal.price - signal.sl) / signal.price
        tp_pct = abs(signal.price - signal.tp) / signal.price

        try:
            self._broker.submit_market_order(
                TICKER, signal.action.lower(), LOTS,
                sl_pct=sl_pct, tp_pct=tp_pct,
                comment="GoldSwing"
            )
        except Exception as exc:
            logger.error(f"[SwingAgent] Ordre refusé : {exc}")
            return

        reason_full = (
            f"SWING {signal.action} | {signal.reason} | "
            f"ATR={signal.atr} | SL={signal.sl} TP={signal.tp} | "
            f"RSI(4H)={signal.rsi_4h} | EMA20(4H)={signal.ema20_4h}"
        )

        mem.log_decision(
            ticker=TICKER,
            action=signal.action,
            confidence=signal.confidence,
            strategy="GoldSwing",
            price=signal.price,
            ml_prob=None,
            reason=reason_full,
        )

        logger.success(
            f"[SwingAgent] {signal.action} {LOTS} XAUUSD @ ${signal.price:.2f} | "
            f"SL=${signal.sl:.2f} TP=${signal.tp:.2f} | Conf={signal.confidence:.0%} | "
            f"Tendance={signal.daily_trend}"
        )

    def get_status(self) -> dict:
        signal = self._strategy.analyze()
        positions = self._broker.get_positions(TICKER)
        return {
            "running": self._running,
            "last_signal": signal.action,
            "confidence": signal.confidence,
            "daily_trend": signal.daily_trend,
            "rsi_4h": signal.rsi_4h,
            "price": signal.price,
            "ema20_4h": signal.ema20_4h,
            "atr": signal.atr,
            "positions": positions,
            "reason": signal.reason,
        }
