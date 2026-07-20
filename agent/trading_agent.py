"""
Agent de trading adaptatif — cerveau du système.

Cycle par tick :
  1. Télécharge le prix courant
  2. Génère le signal de la stratégie active
  3. Récupère la probabilité ML (confiance)
  4. Combine → BUY / SELL / HOLD selon confidence ≥ AGENT_MIN_CONFIDENCE
  5. Valide via RiskManager
  6. Exécute l'ordre sur le paper broker
  7. Logue la décision en mémoire

Garde-fous de sécurité :
  - AGENT_MODE doit être "paper"
  - LIVE_TRADING doit être False
  - Drawdown max → arrêt automatique
  - Aucun vrai ordre n'est jamais envoyé
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import yfinance as yf
from loguru import logger

from agent import memory as mem
from agent.strategy_selector import select_best_strategy
from config.settings import (
    AGENT_MAX_DRAWDOWN,
    AGENT_MIN_CONFIDENCE,
    AGENT_MODE,
    INITIAL_CAPITAL,
    LIVE_TRADING,
    MODEL_STORE_DIR,
)
from execution.alpaca_paper_broker import AlpacaPaperBroker
from risk.risk_manager import RiskManager


# ── Garde-fous de sécurité ────────────────────────────────────────────────────

def _assert_agent_safe() -> None:
    if AGENT_MODE != "paper":
        raise EnvironmentError(
            f"AGENT_MODE='{AGENT_MODE}' interdit — seul 'paper' est autorisé."
        )
    if LIVE_TRADING:
        raise EnvironmentError(
            "LIVE_TRADING=True détecté — l'agent refuse de démarrer. "
            "Mettez LIVE_TRADING=false dans .env."
        )


# ── Agent ─────────────────────────────────────────────────────────────────────

class TradingAgent:
    """Agent de paper trading adaptatif.

    Args:
        ticker: Ticker à trader.
        interval_sec: Pause entre chaque tick (en secondes).
    """

    def __init__(self, ticker: str, interval_sec: int = 60) -> None:
        _assert_agent_safe()
        mem.init_db()

        self.ticker = ticker
        self.interval_sec = interval_sec

        self.broker = AlpacaPaperBroker(simulation_capital=INITIAL_CAPITAL)
        self.broker.restore_state(ticker)  # restaure le solde depuis la DB
        self.risk = RiskManager()

        self._peak_value = INITIAL_CAPITAL
        self._running = True

        self._last_signal: int = 0
        self._ml_model = None
        self._ml_model_mtime: float = 0.0
        self._last_trade_ts: float = time.time()
        self._reinforce_count: int = 0  # max 1 renforcement par trade

        # Gestion de la thèse de trade (persistée en fichier JSON)
        self._thesis_file = (
            Path(__file__).resolve().parent / "memory_store" / f"thesis_{ticker}.json"
        )
        # Thèse long
        self._entry_price: float = 0.0
        self._peak_since_entry: float = 0.0
        self._entry_score: int = 0
        self._entry_signals: list = []
        self._entry_ts: float = 0.0
        # Thèse short (miroir exact)
        self._short_entry_price: float = 0.0
        self._trough_since_entry: float = 0.0  # plus bas depuis l'ouverture du short
        self._short_entry_score: int = 0
        self._short_entry_signals: list = []
        self._short_entry_ts: float = 0.0
        self._load_thesis()   # restaure si l'agent a été redémarré avec position ouverte

        # Stratégie : restaure depuis la mémoire ou backteste une seule fois
        self._strategy_name: str | None = mem.get_best_strategy(ticker)
        self._strategy = self._init_strategy()

        logger.info(
            f"[TradingAgent] Démarré — ticker={ticker} mode=paper "
            f"min_confidence={AGENT_MIN_CONFIDENCE} max_drawdown={AGENT_MAX_DRAWDOWN:.0%}"
        )

    # ── Cycle principal ───────────────────────────────────────────────────────

    def run(self, max_ticks: int | None = None) -> None:
        tick = 0
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"[TradingAgent] Erreur tick : {exc}")

            tick += 1
            if max_ticks and tick >= max_ticks:
                break

            self._wait(self.interval_sec)

    def stop(self) -> None:
        self._running = False
        logger.info("[TradingAgent] Arrêt demandé.")

    def close_all_positions(self) -> None:
        """Ferme toutes les positions ouvertes au prix du marché avant l'arrêt."""
        try:
            price_data = yf.download(self.ticker, period="1d", interval="1m", progress=False, auto_adjust=True)
            if hasattr(price_data.columns, "levels"):
                price_data.columns = price_data.columns.get_level_values(0)
            price = float(price_data["Close"].iloc[-1]) if not price_data.empty else None
        except Exception:
            price = None

        pos = self.broker.get_positions()
        long_pos  = pos.get("long",  {}).get(self.ticker)
        short_pos = pos.get("short", {}).get(self.ticker)

        if long_pos and long_pos.get("qty", 0) > 0:
            qty = long_pos["qty"]
            logger.warning(f"[TradingAgent] Fermeture LONG {qty:.4f} {self.ticker} à l'arrêt")
            try:
                self.broker.submit_market_order(self.ticker, "sell", qty)
                mem.log_decision(
                    ticker=self.ticker, action="SELL",
                    confidence=1.0, strategy="SHUTDOWN_CLOSE",
                    price=price or 0, ml_prob=None,
                    reason="Fermeture automatique à l'arrêt de l'agent",
                )
                logger.success(f"[TradingAgent] Position LONG fermée @ ${price:.2f}" if price else "[TradingAgent] Position LONG fermée")
            except Exception as exc:
                logger.error(f"[TradingAgent] Erreur fermeture LONG : {exc}")

        elif short_pos and short_pos.get("qty", 0) > 0:
            qty = short_pos["qty"]
            logger.warning(f"[TradingAgent] Fermeture SHORT {qty:.4f} {self.ticker} à l'arrêt")
            try:
                self.broker.submit_market_order(self.ticker, "cover", qty)
                mem.log_decision(
                    ticker=self.ticker, action="COVER",
                    confidence=1.0, strategy="SHUTDOWN_CLOSE",
                    price=price or 0, ml_prob=None,
                    reason="Fermeture automatique à l'arrêt de l'agent",
                )
                logger.success(f"[TradingAgent] Position SHORT couverte @ ${price:.2f}" if price else "[TradingAgent] Position SHORT couverte")
            except Exception as exc:
                logger.error(f"[TradingAgent] Erreur fermeture SHORT : {exc}")
        else:
            logger.info("[TradingAgent] Aucune position ouverte à fermer.")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        import pandas as pd

        # ── 1 seul download yfinance par tick ────────────────────────────────
        # Crypto : 6 mois horaire (~4300 bougies)
        # Actions/ETF : 2 ans daily (~500 bougies) — nécessaire pour MA200, dist_high52
        _CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"}
        _period   = "6mo"  if self.ticker in _CRYPTO else "2y"
        _interval = "1h"   if self.ticker in _CRYPTO else "1d"
        try:
            df = yf.download(
                self.ticker, period=_period, interval=_interval,
                auto_adjust=False, group_by="column",
                threads=False, progress=False,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if df.empty:
                return
            price = float(df["Close"].iloc[-1])
        except Exception as exc:
            logger.warning(f"[TradingAgent] Download échoué : {exc}")
            return

        # Met à jour le prix dans le broker (évite un 2ème appel réseau)
        self.broker._last_sim_price[self.ticker] = price

        # Drawdown check
        pv = self.broker.get_portfolio_value({self.ticker: price})
        self._peak_value = max(self._peak_value, pv)
        dd = (self._peak_value - pv) / self._peak_value
        if dd >= AGENT_MAX_DRAWDOWN:
            logger.warning(f"[TradingAgent] Drawdown {dd:.1%} ≥ {AGENT_MAX_DRAWDOWN:.1%} — arrêt.")
            self._running = False
            return

        # Stratégie active (df déjà téléchargé)
        strat_name, strat, signal = self._get_signal(df)

        # Confiance ML (df déjà téléchargé)
        ml_prob, confidence = self._get_ml_confidence(df)

        # Analyse complète du marché
        ctx = self._analyze_market(df, price, ml_prob)

        # Position longue
        _pos_now = self.broker.get_position(self.ticker)
        _pos_qty = float(_pos_now.get("qty", 0)) if isinstance(_pos_now, dict) else 0.0
        _pos_avg = float(_pos_now.get("avg_price", 0)) if isinstance(_pos_now, dict) else 0.0
        _has_long = _pos_qty > 0 and _pos_avg > 0

        # Position short
        _short_now = self.broker.get_short_position(self.ticker)
        _short_qty = float(_short_now.get("qty", 0)) if _short_now else 0.0
        _short_avg = float(_short_now.get("avg_price", 0)) if _short_now else 0.0
        _has_short = _short_qty > 0 and _short_avg > 0

        _has_position = _has_long or _has_short

        # ── Heures de marché : skip si marché fermé et pas de position ouverte ──
        _CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"}
        if self.ticker not in _CRYPTO:
            import datetime as _dt
            _now_utc = _dt.datetime.utcnow()
            _hour_utc = _now_utc.hour + _now_utc.minute / 60
            _market_open = (_now_utc.weekday() < 5) and (13.5 <= _hour_utc <= 21.0)
            if not _market_open and not _has_position:
                logger.debug(f"[TradingAgent] {self.ticker} marché fermé — HOLD")
                return

        # Suivi de position longue
        if _has_long:
            if self._entry_price == 0.0:
                self._entry_price = _pos_avg
                self._peak_since_entry = max(_pos_avg, price)
                self._entry_ts = time.time()
                self._entry_score = 2
            self._peak_since_entry = max(self._peak_since_entry, price)
        elif self._entry_price > 0:
            self._clear_thesis()

        # Suivi de position short
        if _has_short:
            if self._short_entry_price == 0.0:
                self._short_entry_price = _short_avg
                self._trough_since_entry = min(_short_avg, price)
                self._short_entry_ts = time.time()
                self._short_entry_score = -2
            self._trough_since_entry = min(self._trough_since_entry, price)
        elif self._short_entry_price > 0:
            self._clear_short_thesis()

        action, reason = "HOLD", ""

        if _has_long:
            action, reason = self._check_exit(price, _pos_avg, ctx)
        elif _has_short:
            action, reason = self._check_exit_short(price, _short_avg, ctx)

        if action == "HOLD":
            action, reason = self._decide(signal, ml_prob, confidence, _has_position, ctx)

        # ── Filtre de confluence BTC : win rate > 55% ─────────────────────────
        # On ne prend une nouvelle entrée que quand PLUSIEURS signaux s'alignent.
        # Les sorties (SELL/COVER) ne sont jamais bloquées.
        _NEW_ENTRY = action in ("BUY", "SHORT")
        if _NEW_ENTRY and self.ticker == "BTC-USD":
            action, reason = self._btc_confluence_filter(action, reason, df, ml_prob)

        grade = self._grade(ml_prob, confidence)

        # ── Exécution ─────────────────────────────────────────────────────────
        from risk.risk_manager import OrderRequest

        if action == "BUY":
            cash = float(self.broker.get_account().cash)
            if cash < price * 0.000001:
                action, reason = "HOLD", "Cash insuffisant pour acheter"
            else:
                qty = self.risk.compute_position_size(price, pv, available_cash=cash)
                if qty > 0:
                    order = OrderRequest(ticker=self.ticker, side="buy", price=price,
                                        quantity=qty, portfolio_value=pv, cash=cash)
                    ok, msg = self.risk.validate(order)
                    if ok:
                        self.broker.submit_market_order(self.ticker, "buy", qty)
                        self._last_trade_ts = time.time()
                        self._entry_price = price
                        self._peak_since_entry = price
                        self._entry_score = ctx.get("score", 0)
                        self._entry_signals = list(ctx.get("signals", []))
                        self._entry_ts = time.time()
                        self._reinforce_count = 0
                        self._open_trade_id = mem.log_trade_entry(self.ticker, price, "long", ml_prob)
                        self._save_thesis()
                    else:
                        action, reason = "HOLD", f"Risk refusé : {msg}"

        elif action == "SELL":
            pos = self.broker.get_position(self.ticker)
            pos_qty_sell = float(pos.get("qty", 0)) if isinstance(pos, dict) else 0.0
            if pos and pos_qty_sell > 0:
                self.broker.submit_market_order(self.ticker, "sell", pos_qty_sell)
                self._last_trade_ts = time.time()
                if hasattr(self, "_open_trade_id") and self._open_trade_id:
                    mem.log_trade_exit(self._open_trade_id, price)
                    self._open_trade_id = None
                self._clear_thesis()
            else:
                action, reason = "HOLD", "Aucune position longue à vendre"

        elif action == "SHORT":
            cash = float(self.broker.get_account().cash)
            qty = self.risk.compute_position_size(price, pv, available_cash=cash)
            if qty > 0:
                order = OrderRequest(ticker=self.ticker, side="short", price=price,
                                     quantity=qty, portfolio_value=pv, cash=cash)
                ok, msg = self.risk.validate(order)
                if ok:
                    self.broker.submit_market_order(self.ticker, "sell", qty)
                    self._last_trade_ts = time.time()
                    self._short_entry_price = price
                    self._trough_since_entry = price
                    self._short_entry_score = ctx.get("score", 0)
                    self._short_entry_signals = list(ctx.get("signals", []))
                    self._short_entry_ts = time.time()
                    self._save_thesis()
                else:
                    action, reason = "HOLD", f"Risk refusé short : {msg}"

        elif action == "COVER":
            short_pos = self.broker.get_short_position(self.ticker)
            short_qty_cover = float(short_pos.get("qty", 0)) if short_pos else 0.0
            if short_pos and short_qty_cover > 0:
                self.broker.submit_market_order(self.ticker, "buy", short_qty_cover)
                self._last_trade_ts = time.time()
                self._clear_short_thesis()
            else:
                action, reason = "HOLD", "Aucune position short à couvrir"

        elif action == "REINFORCE_LONG":
            cash = float(self.broker.get_account().cash)
            if cash < price * 0.000001:
                action, reason = "HOLD", "Cash insuffisant pour renforcer"
            else:
                # Renforcement = 33% de la taille normale (pyramiding prudent)
                qty = self.risk.compute_position_size(price, pv, available_cash=cash) / 3
                qty = round(max(qty, 0.000001), 6)
                order = OrderRequest(ticker=self.ticker, side="buy", price=price,
                                     quantity=qty, portfolio_value=pv, cash=cash)
                ok, msg = self.risk.validate(order)
                if ok:
                    self.broker.submit_market_order(self.ticker, "buy", qty)
                    self._last_trade_ts = time.time()
                    self._reinforce_count += 1
                    self._save_thesis()
                else:
                    action, reason = "HOLD", f"Risk refusé renforcement : {msg}"

        elif action == "REINFORCE_SHORT":
            cash = float(self.broker.get_account().cash)
            qty = self.risk.compute_position_size(price, pv, available_cash=cash) / 3
            qty = round(max(qty, 0.000001), 6)
            order = OrderRequest(ticker=self.ticker, side="short", price=price,
                                 quantity=qty, portfolio_value=pv, cash=cash)
            ok, msg = self.risk.validate(order)
            if ok:
                self.broker.submit_market_order(self.ticker, "sell", qty)
                self._last_trade_ts = time.time()
                self._save_thesis()
            else:
                action, reason = "HOLD", f"Risk refusé renforcement short : {msg}"

        mem.log_decision(
            ticker=self.ticker,
            action=action,
            confidence=confidence,
            strategy=strat_name,
            price=price,
            ml_prob=ml_prob,
            reason=reason,
        )

        # Snapshot du portefeuille + log budget
        try:
            acct = self.broker.get_account()
            # Vérifie long ET short séparément (get_position ne retourne jamais side=short)
            long_obj  = self.broker.get_position(self.ticker)
            short_obj = self.broker.get_short_position(self.ticker) if hasattr(self.broker, "get_short_position") else None

            if short_obj and float(short_obj.get("qty", 0)) > 0:
                pos_qty   = float(short_obj.get("qty", 0))
                pos_side  = "short"
            elif long_obj:
                pos_qty  = float(long_obj.get("qty", 0)) if isinstance(long_obj, dict) else float(long_obj.qty)
                pos_side = "long"
            else:
                pos_qty  = 0.0
                pos_side = "long"

            # SHORT : le cash inclut les recettes de vente — valeur réelle = cash - coût de rachat
            if pos_side == "short":
                pos_value = -(pos_qty * price)
            else:
                pos_value = pos_qty * price
            total_value = float(acct.cash) + pos_value
            pnl = total_value - INITIAL_CAPITAL
            pnl_str = f"{pnl:+.2f}"

            mem.log_portfolio_snapshot(
                ticker=self.ticker,
                cash=float(acct.cash),
                positions_value=pos_value,
                action=action,
            )

            # Sauvegarde broker_state à chaque tick pour que le dashboard l'affiche
            # Préserve avg_price d'entrée — ne l'écraser qu'au moment d'un BUY/SHORT réel
            long_pos = {}
            short_pos = {}
            if pos_qty > 0:
                _prev_state = mem.load_broker_state(self.ticker)
                if action in ("BUY", "SHORT"):
                    _entry_price = price  # nouveau trade : prix courant = prix d'entrée
                elif action in ("REINFORCE_LONG", "REINFORCE_SHORT"):
                    # Moyenne pondérée entre l'avg_price existant et le prix du renforcement
                    _prev_state2 = mem.load_broker_state(self.ticker)
                    _prev_longs2 = (_prev_state2 or {}).get("positions", {})
                    _prev_shorts2 = (_prev_state2 or {}).get("short_positions", {})
                    _prev_entry2 = (_prev_longs2.get(self.ticker) or _prev_shorts2.get(self.ticker) or {})
                    _old_avg = float(_prev_entry2.get("avg_price", price))
                    _old_qty = float(_prev_entry2.get("qty", pos_qty))
                    _reinf_qty = pos_qty - _old_qty
                    if _reinf_qty > 0 and pos_qty > 0:
                        _entry_price = (_old_avg * _old_qty + price * _reinf_qty) / pos_qty
                    else:
                        _entry_price = _old_avg
                elif _prev_state:
                    _prev_longs  = _prev_state.get("positions", {})
                    _prev_shorts = _prev_state.get("short_positions", {})
                    _prev_entry  = (_prev_longs.get(self.ticker) or _prev_shorts.get(self.ticker) or {})
                    _entry_price = float(_prev_entry.get("avg_price", price))
                else:
                    _entry_price = price
                if pos_side == "long":
                    long_pos = {self.ticker: {"qty": pos_qty, "avg_price": _entry_price}}
                else:
                    short_pos = {self.ticker: {"qty": pos_qty, "avg_price": _entry_price}}
            mem.save_broker_state(
                ticker=self.ticker,
                cash=float(acct.cash),
                positions=long_pos,
                short_positions=short_pos,
            )

            if action in ("BUY", "SELL", "SHORT", "COVER"):
                logger.info(
                    f"[{self.ticker}] {action:5s} | prix=${price:,.2f} | "
                    f"cash=${acct.cash:,.2f} | pos={pos_qty}x${price:,.2f}=${pos_value:,.2f} | "
                    f"total=${total_value:,.2f} | P&L={pnl_str}$"
                )
            else:
                _score = ctx.get("score", "?") if "ctx" in dir() else "?"
                logger.info(
                    f"[{self.ticker}] {action:4s} | conf={confidence:.2f} | score={_score} "
                    f"| prix=${price:,.2f} | total=${total_value:,.2f} | P&L={pnl_str}$ | {reason}"
                )
        except Exception:
            logger.info(
                f"[{self.ticker}] {action:4s} | conf={confidence:.2f} "
                f"| prix=${price:,.2f} | strat={strat_name} | {reason}"
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _init_strategy(self):
        """Charge la stratégie depuis la mémoire ou backteste une seule fois au démarrage."""
        from strategies.moving_average_strategy import MovingAverageStrategy
        from strategies.rsi_strategy import RSIStrategy
        from strategies.macd_strategy import MACDStrategy
        from strategies.ml_strategy import MLStrategy
        _classes = {"SMA": MovingAverageStrategy, "RSI": RSIStrategy,
                    "MACD": MACDStrategy, "ML": MLStrategy}

        if self._strategy_name:
            cls = _classes.get(self._strategy_name)
            if cls:
                strat = cls(self.ticker) if self._strategy_name == "ML" else cls()
                logger.info(f"[TradingAgent] Stratégie {self._strategy_name} restaurée (sans backtest)")
                return strat

        # Aucune stratégie connue → backtest unique au démarrage
        try:
            import pandas as pd
            df = yf.download(self.ticker, period="6mo", auto_adjust=False,
                             group_by="column", threads=False, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.index = df.index.tz_localize(None)  # normalise timezone
            best_name, best_strat, results = select_best_strategy(self.ticker, df)
            self._strategy_name = best_name
            for r in results:
                mem.log_strategy_performance(
                    ticker=self.ticker, strategy=r["strategy"],
                    sharpe=r["sharpe"], perf_pct=r["perf_pct"],
                    drawdown_pct=r["drawdown_pct"], win_rate_pct=r["win_rate_pct"],
                    n_trades=r["n_trades"], score=r["score"],
                )
            return best_strat
        except Exception as exc:
            logger.warning(f"[TradingAgent] Sélection stratégie échouée : {exc} — SMA par défaut")
            self._strategy_name = "SMA"
            return MovingAverageStrategy()

    def _get_signal(self, df) -> tuple[str, Any, int]:
        """Signal depuis la stratégie active. df déjà téléchargé."""
        try:
            signals = self._strategy.generate_signals(df)
            last_signal = int(signals.iloc[-1]) if not signals.empty else 0
        except Exception:
            last_signal = 0
        return self._strategy_name, self._strategy, last_signal

    def _get_ml_confidence(self, df) -> tuple[float | None, float]:
        """Confiance ML depuis le df déjà téléchargé. Modèle mis en cache."""
        model_path = MODEL_STORE_DIR / f"{self.ticker}_rf_model.joblib"
        if not model_path.exists():
            return None, 0.5

        try:
            import joblib
            from ml.feature_engineering import build_features

            # Recharge le modèle dès que le fichier change (après réentraînement)
            mtime = model_path.stat().st_mtime
            if self._ml_model is None or mtime != self._ml_model_mtime:
                self._ml_model = joblib.load(model_path)
                self._ml_model_mtime = mtime
                logger.info(f"[TradingAgent] Modèle ML rechargé ({model_path.name})")

            feat = build_features(df, ticker=self.ticker)
            feat = feat.ffill().replace([float("inf"), float("-inf")], float("nan")).fillna(0)
            if feat.empty:
                return None, 0.5

            # Filtre les features selon ce que le modèle attend
            feat_cols = getattr(self._ml_model, "_nexora_feature_cols", None)
            if feat_cols:
                missing = [c for c in feat_cols if c not in feat.columns]
                if missing:
                    logger.warning(f"[TradingAgent] Features manquantes : {missing}")
                    return None, 0.5
                last_feat = feat[feat_cols].iloc[[-1]]
            else:
                last_feat = feat.iloc[[-1]]

            proba = self._ml_model.predict_proba(last_feat)[0]
            ml_prob = float(proba[1])
            confidence = max(ml_prob, 1 - ml_prob)
            return ml_prob, confidence
        except Exception as exc:
            logger.debug(f"[TradingAgent] ML confidence échouée : {exc}")
            return None, 0.5

    @staticmethod
    def _grade(ml_prob: float | None, confidence: float) -> str:
        """Grade A/B/C/D selon la force du signal ML.
        A = très fort (≥80%), B = fort (≥65%), C = modéré (≥55%), D = faible (<55%)
        """
        if ml_prob is None:
            return "C" if confidence >= 0.65 else "D"
        conf = max(ml_prob, 1 - ml_prob)
        if conf >= 0.80: return "A"
        if conf >= 0.65: return "B"
        if conf >= 0.55: return "C"
        return "D"

    def _analyze_market(self, df, price: float, ml_prob: float | None) -> dict:
        """
        Lecture complète du marché — régime, momentum, indicateurs techniques.
        Calcule un score de conviction de -5 (très baissier) à +5 (très haussier).
        """
        import numpy as np
        ctx: dict = {"score": 0, "regime": "ranging", "signals": []}

        try:
            close = df["Close"]
            volume = df["Volume"]

            # ── Régime de marché (tendance ou range) ──────────────────────────
            ma20 = close.rolling(20).mean().iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else ma50

            if ma20 > ma50 > ma200:
                ctx["regime"] = "trending_up"
            elif ma20 < ma50 < ma200:
                ctx["regime"] = "trending_down"
            else:
                ctx["regime"] = "ranging"

            score = 0

            # ── Signal 1 : position par rapport aux MAs ───────────────────────
            if price > ma20 > ma50:
                score += 1
                ctx["signals"].append("Prix > MA20 > MA50 (haussier)")
            elif price < ma20 < ma50:
                score -= 1
                ctx["signals"].append("Prix < MA20 < MA50 (baissier)")

            # ── Signal 2 : RSI ────────────────────────────────────────────────
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-9)
            rsi = 100 - (100 / (1 + rs))
            ctx["rsi"] = rsi

            if rsi < 35:
                score += 1
                ctx["signals"].append(f"RSI survendu ({rsi:.0f}) — rebond probable")
            elif rsi > 65:
                score -= 1
                ctx["signals"].append(f"RSI suracheté ({rsi:.0f}) — correction probable")

            # ── Signal 3 : MACD histogram ─────────────────────────────────────
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd  = ema12 - ema26
            sig_line = macd.ewm(span=9, adjust=False).mean()
            hist = macd - sig_line
            hist_now  = hist.iloc[-1]
            hist_prev = hist.iloc[-2] if len(hist) > 1 else 0
            ctx["macd_hist"] = hist_now

            if hist_now > 0 and hist_now > hist_prev:
                score += 1
                ctx["signals"].append("MACD haussier et accélère")
            elif hist_now < 0 and hist_now < hist_prev:
                score -= 1
                ctx["signals"].append("MACD baissier et accélère")
            elif hist_now > 0 and hist_now < hist_prev:
                score -= 1
                ctx["signals"].append("MACD haussier mais momentum ralentit")

            # ── Signal 4 : Bollinger Bands ────────────────────────────────────
            std20 = close.rolling(20).std().iloc[-1]
            bb_upper = ma20 + 2 * std20
            bb_lower = ma20 - 2 * std20
            bb_pos = (price - bb_lower) / (bb_upper - bb_lower + 1e-9)
            ctx["bb_position"] = bb_pos

            if bb_pos < 0.15:
                score += 1
                ctx["signals"].append(f"Proche bas Bollinger ({bb_pos:.0%}) — zone d'achat")
            elif bb_pos > 0.85:
                score -= 1
                ctx["signals"].append(f"Proche haut Bollinger ({bb_pos:.0%}) — zone de vente")

            # ── Signal 5 : momentum prix (3 derniers jours) ───────────────────
            if len(close) >= 4:
                mom3 = (close.iloc[-1] / close.iloc[-4] - 1)
                ctx["momentum_3d"] = mom3
                if mom3 > 0.02:
                    score += 1
                    ctx["signals"].append(f"Momentum +{mom3:.1%} sur 3 jours")
                elif mom3 < -0.02:
                    score -= 1
                    ctx["signals"].append(f"Momentum {mom3:.1%} sur 3 jours")

            # ── Signal 6 : ML probability ─────────────────────────────────────
            if ml_prob is not None:
                if ml_prob >= 0.65:
                    score += 2
                    ctx["signals"].append(f"ML très haussier ({ml_prob:.0%})")
                elif ml_prob >= 0.55:
                    score += 1
                    ctx["signals"].append(f"ML haussier ({ml_prob:.0%})")
                elif ml_prob <= 0.35:
                    score -= 2
                    ctx["signals"].append(f"ML très baissier ({1-ml_prob:.0%})")
                elif ml_prob <= 0.45:
                    score -= 1
                    ctx["signals"].append(f"ML baissier ({1-ml_prob:.0%})")

            ctx["score"] = max(-5, min(5, score))

        except Exception as exc:
            logger.debug(f"[TradingAgent] analyze_market erreur : {exc}")
            ctx["score"] = 0

        return ctx

    def _check_exit(self, price: float, avg_price: float, ctx: dict) -> tuple[str, str]:
        """
        Raisonnement de sortie d'un trader senior — thèse d'abord, prix ensuite.

        Ordre d'évaluation :
        1. Protection du capital (stop-loss dur non négociable)
        2. Trailing stop (protège les gains acquis)
        3. Thèse d'entrée invalidée (raison principale de sortie)
        4. Momentum qui s'épuise (prise de profit proactive)
        5. Take-profit de sécurité (filet de dernier recours)
        """
        chg = (price - avg_price) / avg_price
        score_now = ctx.get("score", 0)
        rsi = ctx.get("rsi", 50)
        macd_hist = ctx.get("macd_hist", 0)
        bb_pos = ctx.get("bb_position", 0.5)
        regime = ctx.get("regime", "ranging")
        trailing_chg = (
            (price - self._peak_since_entry) / self._peak_since_entry
            if self._peak_since_entry > 0 else 0
        )
        time_in_trade_h = (time.time() - self._entry_ts) / 3600 if self._entry_ts > 0 else 0

        # ── 1. Stop-loss dur — non négociable ─────────────────────────────────
        if chg <= -0.03:
            return "SELL", (
                f"STOP-LOSS — Perte {chg:+.1%} dépasse le seuil de -3%. "
                f"Protection du capital avant tout."
            )

        # ── 2. Trailing stop — protège les gains ──────────────────────────────
        # Seulement si on a vraiment gagné quelque chose (> +1.5%)
        if self._peak_since_entry > avg_price * 1.015 and trailing_chg <= -0.018:
            gain_from_entry = (self._peak_since_entry - avg_price) / avg_price
            return "SELL", (
                f"TRAILING STOP — Position avait gagné {gain_from_entry:+.1%}, "
                f"recul de {trailing_chg:+.1%} depuis le sommet. Gains sécurisés."
            )

        # ── 3. Thèse d'entrée invalidée ───────────────────────────────────────
        # Reconstitue combien de signaux d'entrée sont encore actifs
        signals_now = set(ctx.get("signals", []))
        signals_entry = set(self._entry_signals)
        # Signaux bullish qui se sont retournés en bearish
        bullish_entry = [s for s in signals_entry if any(
            kw in s for kw in ["haussier", "achat", "rebond", "Momentum +", "ML très haussier", "ML haussier"]
        )]
        bullish_still_active = sum(1 for s in bullish_entry if s in signals_now)
        thesis_survival = bullish_still_active / max(len(bullish_entry), 1)

        # Si score actuel << score d'entrée ET majorité des signaux ont disparu
        score_drop = self._entry_score - score_now
        if score_drop >= 3 and thesis_survival < 0.4:
            lost_signals = [s for s in bullish_entry if s not in signals_now][:2]
            return "SELL", (
                f"THÈSE INVALIDÉE — Score {self._entry_score}→{score_now}, "
                f"signaux perdus : {', '.join(lost_signals) or 'tous'}."
            )

        # Score clairement négatif = marché a retourné
        if score_now <= -2:
            bearish_signals = [s for s in ctx.get("signals", []) if any(
                kw in s for kw in ["baissier", "vente", "correction", "Momentum -"]
            )]
            return "SELL", (
                f"MARCHÉ RETOURNÉ — Score {score_now}/5. "
                f"{bearish_signals[0] if bearish_signals else 'Consensus baissier'}."
            )

        # ── 4. Momentum qui s'épuise — sortie proactive ───────────────────────
        # Cas 1 : RSI suracheté + MACD ralentit + on est en profit
        if chg > 0.01 and rsi > 68 and macd_hist < 0:
            return "SELL", (
                f"MOMENTUM ÉPUISÉ — En profit {chg:+.1%}, RSI suracheté ({rsi:.0f}), "
                f"MACD en décélération. Prise de profit proactive."
            )

        # Cas 2 : Prix au sommet des Bollinger Bands en range → retour probable
        if regime == "ranging" and bb_pos > 0.88 and chg > 0.005:
            return "SELL", (
                f"RÉSISTANCE BOLLINGER — Prix à {bb_pos:.0%} des bandes en marché range. "
                f"Retour vers la moyenne attendu. Profit {chg:+.1%}."
            )

        # Cas 3 : Trade ouvert depuis > 6h et score clairement négatif
        # Score 0 = neutre, pas une raison de sortir — attendre signal baissier
        if time_in_trade_h > 6 and score_now <= -1 and chg > -0.01:
            return "SELL", (
                f"CATALYSEUR JOUÉ — Trade ouvert depuis {time_in_trade_h:.1f}h, "
                f"score retombé à {score_now}/5. La thèse initiale a expiré."
            )

        # ── 5. Take-profit de sécurité ────────────────────────────────────────
        if chg >= 0.07:
            return "SELL", (
                f"TAKE-PROFIT CIBLE — Objectif {chg:+.1%} atteint. "
                f"Score actuel {score_now}/5."
            )

        return "HOLD", f"Thèse maintenue — score {score_now}/5, P&L {chg:+.2%}"

    def _check_exit_short(self, price: float, avg_price: float, ctx: dict) -> tuple[str, str]:
        """
        Miroir exact de _check_exit — raisonnement de sortie d'une position short.
        Le profit vient d'une BAISSE du prix, les stop/TP sont inversés.
        """
        chg = (avg_price - price) / avg_price  # positif si prix a baissé (profit pour short)
        score_now = ctx.get("score", 0)
        rsi = ctx.get("rsi", 50)
        macd_hist = ctx.get("macd_hist", 0)
        bb_pos = ctx.get("bb_position", 0.5)
        regime = ctx.get("regime", "ranging")
        trailing_chg = (
            (self._trough_since_entry - price) / self._trough_since_entry
            if self._trough_since_entry > 0 else 0
        )
        time_in_trade_h = (time.time() - self._short_entry_ts) / 3600 if self._short_entry_ts > 0 else 0

        # ── 1. Stop-loss dur (prix monte contre nous) ─────────────────────────
        if chg <= -0.02:
            return "COVER", (
                f"STOP-LOSS SHORT — Prix remonté de {-chg:+.1%}, dépasse +2%. "
                f"Protection du capital — short coupé rapidement."
            )

        # ── 2. Trailing stop (protège les gains du short) ─────────────────────
        if self._trough_since_entry < avg_price * 0.985 and trailing_chg >= 0.018:
            gain_from_entry = (avg_price - self._trough_since_entry) / avg_price
            return "COVER", (
                f"TRAILING STOP SHORT — Position avait gagné {gain_from_entry:+.1%}, "
                f"rebond de {trailing_chg:+.1%} depuis le bas. Gains sécurisés."
            )

        # ── 3. Thèse short invalidée (marché redevient haussier) ──────────────
        signals_now = set(ctx.get("signals", []))
        signals_entry = set(self._short_entry_signals)
        bearish_entry = [s for s in signals_entry if any(
            kw in s for kw in ["baissier", "vente", "correction", "Momentum -", "ML très baissier", "ML baissier"]
        )]
        bearish_still_active = sum(1 for s in bearish_entry if s in signals_now)
        thesis_survival = bearish_still_active / max(len(bearish_entry), 1)

        score_rise = score_now - self._short_entry_score  # positif = marché remonte
        if score_rise >= 3 and thesis_survival < 0.4:
            lost_signals = [s for s in bearish_entry if s not in signals_now][:2]
            return "COVER", (
                f"THÈSE SHORT INVALIDÉE — Score {self._short_entry_score}→{score_now}, "
                f"signaux perdus : {', '.join(lost_signals) or 'tous'}."
            )

        # Score clairement positif = marché retourné haussier
        if score_now >= 2:
            return "COVER", (
                f"MARCHÉ RETOURNÉ HAUSSIER — Score {score_now}/5. "
                f"Thèse baissière invalide."
            )

        # ── 4. Momentum baissier qui s'épuise ─────────────────────────────────
        # RSI survendu + MACD remonte + on est en profit
        if chg > 0.01 and rsi < 32 and macd_hist > 0:
            return "COVER", (
                f"MOMENTUM SHORT ÉPUISÉ — Profit {chg:+.1%}, RSI survendu ({rsi:.0f}), "
                f"MACD remonte. Prise de profit proactive."
            )

        # Prix au plancher des Bollinger en range → rebond probable
        if regime == "ranging" and bb_pos < 0.12 and chg > 0.005:
            return "COVER", (
                f"SUPPORT BOLLINGER — Prix à {bb_pos:.0%} des bandes en range. "
                f"Rebond vers la moyenne attendu. Profit {chg:+.1%}."
            )

        # Trade ouvert > 3h et score redevenu positif = thèse baissière clairement morte
        if time_in_trade_h > 3 and score_now >= 1 and chg > -0.01:
            return "COVER", (
                f"CATALYSEUR SHORT JOUÉ — Trade ouvert depuis {time_in_trade_h:.1f}h, "
                f"score {score_now}/5. Thèse baissière expirée."
            )

        # ── 5. Take-profit de sécurité ────────────────────────────────────────
        if chg >= 0.07:
            return "COVER", (
                f"TAKE-PROFIT SHORT — Objectif {chg:+.1%} atteint. "
                f"Score actuel {score_now}/5."
            )

        return "HOLD", f"Short maintenu — score {score_now}/5, P&L {chg:+.2%}"

    # ──────────────────────────────────────────────────────────────────────────
    def _btc_confluence_filter(self, action: str, reason: str,
                                df, ml_prob: float | None) -> tuple[str, str]:
        """
        Filtre de confluence BTC — n'entre en position que quand 2+ signaux s'alignent.
        Objectif : win rate > 55% en sacrifiant la fréquence des trades.

        Conditions LONG (BUY) :
          - ML confiance ≥ 62% (seuil élevé)
          - ET au moins 1 condition parmi :
              a) Fear & Greed < 30 (Extreme Fear → bon moment d'acheter)
              b) RSI14 < 40 (survente)
              c) Prix > MA20 ET momentum positif (tendance haussière confirmée)

        Conditions SHORT :
          - ML confiance ≥ 62%
          - ET au moins 1 condition parmi :
              a) Fear & Greed > 70 (Extreme Greed → bon moment de shorter)
              b) RSI14 > 65 (surachat)
              c) Prix < MA20 ET momentum négatif
        """
        # ML doit être suffisamment confiant
        _MIN_CONF = 0.62
        prob = ml_prob if ml_prob is not None else 0.5
        _MIN_CONF_SHORT = 0.65
        if action == "BUY"   and prob < _MIN_CONF:
            return "HOLD", f"BTC confluence: ML={prob:.0%} < {_MIN_CONF:.0%} requis"
        if action == "SHORT" and (1 - prob) < _MIN_CONF_SHORT:
            return "HOLD", f"BTC confluence: ML bear={1-prob:.0%} < {_MIN_CONF_SHORT:.0%} requis pour shorter"

        # Indicateurs techniques locaux
        close = df["Close"]
        rsi14 = None
        try:
            from ml.feature_engineering import compute_rsi
            rsi14 = float(compute_rsi(close, 14).iloc[-1])
        except Exception:
            pass

        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else float(close.iloc[-1])
        price_now = float(close.iloc[-1])
        mom3 = float(close.pct_change(3).iloc[-1]) if len(close) >= 3 else 0.0

        # Fear & Greed
        fg_val = None
        try:
            from data.fear_greed import get_fear_greed_today
            fg_val = get_fear_greed_today()
        except Exception:
            pass

        conditions_met = 0
        conditions_log = []

        if action == "BUY":
            if fg_val is not None and fg_val < 30:
                conditions_met += 1
                conditions_log.append(f"F&G={fg_val:.0f}<30✓")
            if rsi14 is not None and rsi14 < 40:
                conditions_met += 1
                conditions_log.append(f"RSI={rsi14:.0f}<40✓")
            if price_now > ma20 and mom3 > 0:
                conditions_met += 1
                conditions_log.append(f"prix>MA20+mom↑✓")
            # Bonus : F&G extrême (< 20) compte double
            if fg_val is not None and fg_val < 20:
                conditions_met += 1
                conditions_log.append(f"F&G_extreme<20✓✓")

        elif action == "SHORT":
            if fg_val is not None and fg_val > 70:
                conditions_met += 1
                conditions_log.append(f"F&G={fg_val:.0f}>70✓")
            if rsi14 is not None and rsi14 > 65:
                conditions_met += 1
                conditions_log.append(f"RSI={rsi14:.0f}>65✓")
            if price_now < ma20 and mom3 < 0:
                conditions_met += 1
                conditions_log.append(f"prix<MA20+mom↓✓")
            if fg_val is not None and fg_val > 80:
                conditions_met += 1
                conditions_log.append(f"F&G_extreme>80✓✓")

        min_signals = 1 if action == "BUY" else 2
        if conditions_met >= min_signals:
            return action, f"BTC confluence [{conditions_met} signaux: {', '.join(conditions_log)}] — {reason}"
        else:
            conds = ", ".join(conditions_log) if conditions_log else "aucun"
            return "HOLD", f"BTC confluence insuffisante [{conds}] — {min_signals} signaux requis pour {action}"

    def _decide(self, signal: int, ml_prob: float | None, confidence: float,
                has_position: bool = False, ctx: dict | None = None) -> tuple[str, str]:
        """
        Entrée en position longue ou short selon la conviction du marché.
        Symétrique : les mêmes seuils s'appliquent dans les deux sens.
        """
        if ctx is None:
            ctx = {"score": 0, "signals": [], "regime": "ranging"}

        grade = self._grade(ml_prob, confidence)
        score = ctx.get("score", 0)
        regime = ctx.get("regime", "ranging")
        signals_desc = ", ".join(ctx.get("signals", [])[:2])

        ml_strong_bull = ml_prob is not None and ml_prob >= 0.65
        ml_bull        = ml_prob is not None and ml_prob >= 0.58
        ml_strong_bear = ml_prob is not None and ml_prob <= 0.35
        ml_bear        = ml_prob is not None and ml_prob <= 0.42

        # ── Entrée LONG (pas de position) ─────────────────────────────────────
        # ML ≥58% : seuil 1/5 (le ML suffit seul au-dessus du seuil de confiance)
        # ML ≥65% : trade immédiat même à score 0
        if ml_bull:       # ML ≥ 58% : le modèle a prouvé son edge, score ignoré
            long_threshold = 0
        else:
            long_threshold = 2 if regime == "trending_up" else 3

        # ── En position : renforcement si signal fort et pas encore renforcé ────
        if has_position:
            can_reinforce = self._reinforce_count < 1
            strong_signal = score >= 3 and (ml_prob is not None and ml_prob >= 0.65)
            if can_reinforce and strong_signal:
                return "REINFORCE_LONG", f"[{grade}] Renforcement — score {score}/5 ML={ml_prob:.0%} — pyramiding"
            return "HOLD", f"[{grade}] En position — score {score} — thèse maintenue"

        if score >= long_threshold:
            tag = " [ML override]" if ml_strong_bull and score < 2 else ""
            return "BUY", f"[{grade}] Long — conviction {score}/5{tag} — {signals_desc}"

        # ── Entrée SHORT (pas de position) ────────────────────────────────────
        if ml_bear:       # ML ≤ 42% : short autorisé sans score
            short_threshold = 0
        else:
            short_threshold = -2 if regime == "trending_down" else -3
        if score <= short_threshold:
            tag = " [ML override]" if ml_strong_bear and score > -2 else ""
            return "SHORT", f"[{grade}] Short — conviction {score}/5{tag} — {signals_desc}"

        return "HOLD", f"[{grade}] Conviction insuffisante ({score}/5) — attente"

    def _save_thesis(self) -> None:
        import json
        try:
            self._thesis_file.parent.mkdir(parents=True, exist_ok=True)
            self._thesis_file.write_text(json.dumps({
                "entry_price": self._entry_price,
                "peak_since_entry": self._peak_since_entry,
                "entry_score": self._entry_score,
                "entry_signals": self._entry_signals,
                "entry_ts": self._entry_ts,
                "short_entry_price": self._short_entry_price,
                "trough_since_entry": self._trough_since_entry,
                "short_entry_score": self._short_entry_score,
                "short_entry_signals": self._short_entry_signals,
                "short_entry_ts": self._short_entry_ts,
            }))
        except Exception:
            pass

    def _load_thesis(self) -> None:
        import json
        try:
            if self._thesis_file.exists():
                d = json.loads(self._thesis_file.read_text())
                self._entry_price         = float(d.get("entry_price", 0))
                self._peak_since_entry    = float(d.get("peak_since_entry", 0))
                self._entry_score         = int(d.get("entry_score", 0))
                self._entry_signals       = list(d.get("entry_signals", []))
                self._entry_ts            = float(d.get("entry_ts", 0))
                self._short_entry_price   = float(d.get("short_entry_price", 0))
                self._trough_since_entry  = float(d.get("trough_since_entry", 0))
                self._short_entry_score   = int(d.get("short_entry_score", 0))
                self._short_entry_signals = list(d.get("short_entry_signals", []))
                self._short_entry_ts      = float(d.get("short_entry_ts", 0))
                if self._entry_price > 0:
                    logger.info(f"[TradingAgent] Thèse LONG restaurée — entrée ${self._entry_price:,.2f}")
                if self._short_entry_price > 0:
                    logger.info(f"[TradingAgent] Thèse SHORT restaurée — entrée ${self._short_entry_price:,.2f}")
        except Exception:
            pass

    def _clear_thesis(self) -> None:
        self._entry_price = 0.0
        self._peak_since_entry = 0.0
        self._entry_score = 0
        self._entry_signals = []
        self._entry_ts = 0.0
        self._save_thesis()

    def _clear_short_thesis(self) -> None:
        self._short_entry_price = 0.0
        self._trough_since_entry = 0.0
        self._short_entry_score = 0
        self._short_entry_signals = []
        self._short_entry_ts = 0.0
        self._save_thesis()

    def _clear_all_thesis(self) -> None:
        self._clear_thesis()
        self._clear_short_thesis()
        try:
            if self._thesis_file.exists():
                self._thesis_file.unlink()
        except Exception:
            pass

    def _wait(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)
