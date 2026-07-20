"""
Couche d'accès aux données pour le dashboard Streamlit.

Fournit des fonctions cachées qui chargent, calculent et retournent
toutes les données dont les pages ont besoin.
Gère deux modes :
  - Backtest   : données historiques, simulation locale.
  - Live/Paper : connexion Alpaca ou simulation temps réel.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

# Racine du projet → imports absolus
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics
from config.settings import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    DATA_END_DATE,
    DATA_START_DATE,
    INITIAL_CAPITAL,
    LIVE_MA_LONG,
    LIVE_MA_SHORT,
    LIVE_TICKER,
    LIVE_TRADING,
)
from data.market_data import download_ohlcv
from ml.feature_engineering import build_features, build_target, compute_rsi
from strategies.moving_average_strategy import MovingAverageStrategy
from strategies.ml_strategy import MLStrategy


# ── Helpers CSS ───────────────────────────────────────────────────────────────

def inject_css() -> None:
    # Google Fonts — injecté en Python pour éviter les problèmes d'encodage Windows
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    css_path = Path(__file__).parent / "assets" / "style.css"
    if css_path.exists():
        try:
            css_text = css_path.read_text(encoding='ascii', errors='replace')
            st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)
        except Exception:
            pass
    # Logo SVG inline
    logo_path = Path(__file__).parent / "assets" / "logo.svg"
    if logo_path.exists():
        import base64
        svg_b64 = base64.b64encode(logo_path.read_bytes()).decode()
        st.session_state["_logo_b64"] = svg_b64
    st.markdown(
        "<style>[data-testid='stSidebarCollapseButton'] { display: none !important; }</style>",
        unsafe_allow_html=True,
    )


# ── Données de marché ────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_ohlcv(ticker: str, start: str = DATA_START_DATE, end: str = DATA_END_DATE) -> pd.DataFrame:
    return download_ohlcv(ticker, start=start, end=end)


# ── Backtest complet ─────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def run_backtest(
    ticker: str,
    strategy_name: str = "SMA",
    initial_capital: float = INITIAL_CAPITAL,
) -> dict[str, Any]:
    """Exécute un backtest et retourne toutes les données nécessaires au dashboard.

    Returns:
        dict avec clés :
          equity_curve   : pd.DataFrame (equity, cash, signal, price)
          metrics        : dict de métriques
          orders         : list[dict] (historique des ordres)
          positions      : list[dict] (positions ouvertes)
          strategy_label : str
    """
    df = get_ohlcv(ticker)

    if strategy_name == "SMA":
        strategy = MovingAverageStrategy()
    else:
        try:
            strategy = MLStrategy(ticker=ticker)
        except FileNotFoundError:
            strategy = MovingAverageStrategy()
            strategy_name = "SMA (ML model manquant)"

    bt = Backtester(strategy, initial_capital=initial_capital)
    equity_curve = bt.run(ticker, df)
    metrics = compute_metrics(equity_curve, initial_capital)

    # Ordres formatés
    orders = []
    if bt.broker and bt.broker.order_history:
        for o in bt.broker.order_history:
            orders.append({
                "Date": o.timestamp.strftime("%Y-%m-%d"),
                "Ticker": o.ticker,
                "Sens": "ACHAT" if o.side == "buy" else "VENTE",
                "Quantité": o.quantity,
                "Prix ($)": round(o.price, 2),
                "Valeur ($)": round(o.value, 2),
                "PnL ($)": round(o.pnl, 2) if o.side == "sell" else None,
            })

    # Positions ouvertes
    positions = []
    if bt.broker:
        for ticker_sym, pos in bt.broker.positions.items():
            last_price = float(df["Close"].iloc[-1])
            market_value = pos.quantity * last_price
            unrealized_pnl = (last_price - pos.avg_price) * pos.quantity
            pct_change = (last_price / pos.avg_price - 1) * 100
            positions.append({
                "Ticker": ticker_sym,
                "Quantité": pos.quantity,
                "Prix moy. ($)": round(pos.avg_price, 2),
                "Prix actuel ($)": round(last_price, 2),
                "Valeur ($)": round(market_value, 2),
                "PnL latent ($)": round(unrealized_pnl, 2),
                "PnL latent (%)": round(pct_change, 2),
            })

    return {
        "equity_curve": equity_curve,
        "metrics": metrics,
        "orders": orders,
        "positions": positions,
        "strategy_label": strategy_name,
        "ticker": ticker,
        "initial_capital": initial_capital,
    }


# ── Données ML / IA ──────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def get_ml_analysis(ticker: str) -> dict[str, Any]:
    """Calcule les prédictions ML et l'analyse des features.

    Returns:
        dict avec clés :
          features_df       : pd.DataFrame des features (100 dernières barres)
          latest_features   : dict feature → valeur actuelle
          feature_importance: dict feature → importance (si modèle dispo)
          bull_probability  : float 0–1
          signal_label      : str
          model_available   : bool
          accuracy          : float | None
    """
    df = get_ohlcv(ticker)
    features = build_features(df)
    target = build_target(df)

    latest = features.iloc[-1].to_dict()
    result: dict[str, Any] = {
        "features_df": features.tail(100),
        "latest_features": latest,
        "feature_importance": {},
        "bull_probability": 0.5,
        "signal_label": "NEUTRE",
        "model_available": False,
        "accuracy": None,
    }

    from config.settings import MODEL_STORE_DIR
    model_path = MODEL_STORE_DIR / f"{ticker}_rf_model.joblib"

    if model_path.exists():
        import joblib
        from sklearn.metrics import accuracy_score

        model = joblib.load(model_path)

        # Importance des features
        feat_names = features.columns.tolist()
        importances = dict(zip(feat_names, model.feature_importances_))
        result["feature_importance"] = dict(
            sorted(importances.items(), key=lambda x: x[1], reverse=True)
        )

        # Prédiction sur les dernières données valides
        valid = features.dropna()
        if not valid.empty:
            proba = model.predict_proba(valid.iloc[[-1]])
            bull_prob = float(proba[0][1])
            result["bull_probability"] = bull_prob
            result["signal_label"] = (
                "HAUSSIER" if bull_prob > 0.55 else
                "BAISSIER" if bull_prob < 0.45 else "NEUTRE"
            )

        # Accuracy sur la fin de la série (20%)
        combined = features.join(target.rename("t")).dropna()
        n = len(combined)
        split = int(n * 0.8)
        if split < n:
            X_test = combined.iloc[split:].drop(columns=["t"])
            y_test = combined.iloc[split:]["t"]
            preds = model.predict(X_test)
            result["accuracy"] = float((preds == y_test).mean())

        result["model_available"] = True

    return result


# ── Live / Alpaca ────────────────────────────────────────────────────────────

def get_live_account() -> dict[str, Any] | None:
    """Tente de se connecter à Alpaca Paper et retourne l'état du compte.

    Returns None si pas de clés configurées (mode simulation).
    """
    if not (ALPACA_API_KEY and ALPACA_SECRET_KEY):
        return None
    if LIVE_TRADING:
        return None

    try:
        from execution.alpaca_paper_broker import AlpacaPaperBroker
        broker = AlpacaPaperBroker()
        info = broker.get_account()
        price = broker.get_latest_price(LIVE_TICKER)
        pos = broker.get_position(LIVE_TICKER)
        return {
            "portfolio_value": info.portfolio_value,
            "cash": info.cash,
            "buying_power": info.buying_power,
            "live_ticker": LIVE_TICKER,
            "live_price": price,
            "position": pos,
            "mode": "ALPACA PAPER",
        }
    except Exception:
        return None


# ── Calculs dérivés ───────────────────────────────────────────────────────────

def compute_daily_pnl(equity_curve: pd.DataFrame) -> pd.DataFrame:
    """Retourne le PnL journalier à partir de la courbe d'equity."""
    df = equity_curve[["equity"]].copy()
    df["pnl_daily"] = df["equity"].diff()
    df["pnl_pct"] = df["equity"].pct_change() * 100
    return df.dropna()


def compute_drawdown_series(equity_curve: pd.DataFrame) -> pd.Series:
    equity = equity_curve["equity"]
    rolling_max = equity.cummax()
    return ((equity - rolling_max) / rolling_max) * 100


def compute_rolling_sharpe(equity_curve: pd.DataFrame, window: int = 30) -> pd.Series:
    daily_ret = equity_curve["equity"].pct_change()
    roll_mean = daily_ret.rolling(window).mean()
    roll_std  = daily_ret.rolling(window).std()
    return (roll_mean / roll_std.replace(0, np.nan)) * np.sqrt(252)


def format_currency(value: float, symbol: str = "$") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{symbol}{value:,.2f}"


def format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"
