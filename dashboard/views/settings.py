""" Configuration du dashboard et affichage de l'environnement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.components.metrics import divider, kpi_card, section_title
from dashboard.data_loader import get_live_account

_MUTED  = "#64748b"
_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"


def _env_row(label: str, value: str, status: str = "ok") -> None:
    color = {"ok": _GREEN, "warn": _ORANGE, "error": _RED, "info": _MUTED}.get(status, _MUTED)
    icon  = {"ok": "✓", "warn": "⚠", "error": "✗", "info": "·"}.get(status, "·")
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:8px 0;border-bottom:1px solid {_GRID};">
            <span style="color:{_MUTED};font-size:12px;">{label}</span>
            <span style="font-size:12px;font-weight:600;color:{color};">
                {icon} {value}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render(ticker: str, strategy: str, initial_capital: float) -> None:
    st.markdown(
        '<h2 style="margin:0 0 20px;color:#d1d4dc;font-size:20px;font-weight:700;">'
        'Paramètres & Environnement</h2>',
        unsafe_allow_html=True,
    )

    from config.settings import (
        ALPACA_API_KEY,
        ALPACA_BASE_URL,
        ALPACA_PAPER_URL,
        DATA_END_DATE,
        DATA_START_DATE,
        INITIAL_CAPITAL,
        LIVE_INTERVAL_SEC,
        LIVE_MA_LONG,
        LIVE_MA_SHORT,
        LIVE_TICKER,
        LIVE_TRADING,
        LOG_LEVEL,
        MAX_POSITION_SIZE,
        MODEL_STORE_DIR,
        RISK_PER_TRADE,
        STOP_LOSS_PCT,
    )

    # -"?-"? Configuration active -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Configuration Active (Dashboard)")
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Ticker", ticker, "Actif surveillé", None, _BLUE)
    with c2:
        kpi_card("Stratégie", strategy, "Modèle de signal", None, _BLUE)
    with c3:
        kpi_card("Capital Initial", f"${initial_capital:,.0f}", "Paper trading", None, _MUTED)

    divider()

    # -"?-"? Statut Alpaca -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Connexion Alpaca Paper Trading")

    live = get_live_account()
    alpaca_ok = live is not None
    key_configured = bool(ALPACA_API_KEY)
    url_safe = "paper-api.alpaca.markets" in ALPACA_BASE_URL

    st.markdown(
        f"""
        <div style="background:{_CARD};border:1px solid {'#26a69a' if alpaca_ok else _GRID};
                    border-radius:8px;padding:16px 20px;margin-bottom:16px;">
        """,
        unsafe_allow_html=True,
    )
    _env_row("Statut de connexion",
             "Connecté (Alpaca Paper)" if alpaca_ok else "Non connecté (Simulation locale)",
             "ok" if alpaca_ok else "warn")
    _env_row("ALPACA_API_KEY",
             "Configuree ✓" if key_configured else "Non configuree (simulation activee)",
             "ok" if key_configured else "warn")
    _env_row("ALPACA_BASE_URL", ALPACA_BASE_URL,
             "ok" if url_safe else "error")
    _env_row("URL Paper Trading",
             "✓ paper-api.alpaca.markets" if url_safe else "✗ URL incorrecte",
             "ok" if url_safe else "error")
    _env_row("LIVE_TRADING",
             "false (Paper sécurisé)" if not LIVE_TRADING else "⚠ LIVE TRADING ACTIF",
             "ok" if not LIVE_TRADING else "error")

    if live:
        _env_row("Portefeuille Alpaca", f"${live['portfolio_value']:,.2f}", "info")
        _env_row("Cash Alpaca",         f"${live['cash']:,.2f}", "info")

    st.markdown("</div>", unsafe_allow_html=True)

    if not alpaca_ok:
        st.markdown(
            f"""
            <div style="background:rgba(255,152,0,0.08);border:1px solid {_ORANGE};
                        border-radius:6px;padding:12px 16px;font-size:12px;color:{_MUTED};">
                <b style="color:{_ORANGE};">Mode simulation actif.</b>
                Pour connecter Alpaca Paper Trading, ajoutez vos clés dans <code>.env</code> :<br><br>
                <code style="color:{_TEXT};">ALPACA_API_KEY=PKxxxxxxx</code><br>
                <code style="color:{_TEXT};">ALPACA_SECRET_KEY=xxxxxxx</code><br>
                <code style="color:{_TEXT};">ALPACA_BASE_URL=https://paper-api.alpaca.markets</code>
            </div>
            """,
            unsafe_allow_html=True,
        )

    divider()

    # -"?-"? Paramètres risque -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    col_risk, col_data, col_live = st.columns(3)

    with col_risk:
        section_title("Gestion du Risque")
        st.markdown(f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:14px 18px;">', unsafe_allow_html=True)
        _env_row("Risque / trade",         f"{RISK_PER_TRADE*100:.1f}% du capital", "info")
        _env_row("Taille max position",    f"{MAX_POSITION_SIZE*100:.0f}% du portefeuille", "info")
        _env_row("Stop loss",              f"{STOP_LOSS_PCT*100:.0f}%", "info")
        _env_row("Capital initial",        f"${INITIAL_CAPITAL:,.0f}", "info")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_data:
        section_title("Données Historiques")
        st.markdown(f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:14px 18px;">', unsafe_allow_html=True)
        _env_row("Début",  DATA_START_DATE, "info")
        _env_row("Fin",    DATA_END_DATE,   "info")
        _env_row("Tickers", "AAPL, MSFT, SPY", "info")
        _env_row("Source", "yfinance", "info")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_live:
        section_title("Bot Temps Réel")
        st.markdown(f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:14px 18px;">', unsafe_allow_html=True)
        _env_row("Ticker live",     LIVE_TICKER, "info")
        _env_row("Intervalle",      f"{LIVE_INTERVAL_SEC}s", "info")
        _env_row("MA courte",       str(LIVE_MA_SHORT), "info")
        _env_row("MA longue",       str(LIVE_MA_LONG), "info")
        st.markdown("</div>", unsafe_allow_html=True)

    divider()

    # -"?-"? Modèles ML disponibles -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Modèles ML Disponibles")
    models = list(MODEL_STORE_DIR.glob("*.joblib"))

    if models:
        for m in models:
            size_kb = m.stat().st_size / 1024
            st.markdown(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:8px 12px;background:{_CARD};border:1px solid {_GRID};
                            border-radius:6px;margin-bottom:6px;">
                    <span style="color:{_GREEN};font-size:13px;">-o" {m.stem}</span>
                    <span style="color:{_MUTED};font-size:11px;"·""",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<div style="color:{_MUTED};font-size:13px;padding:12px;">'
            "Aucun modèle entraîné. Lancez <code>python main.py</code>.</div>",
            unsafe_allow_html=True,
        )

    divider()

    # -"?-"? Logs récents -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Logs Récents")
    from config.settings import LOGS_DIR
    log_file = LOGS_DIR / "trading.log"
    live_log = LOGS_DIR / "live_paper_trading.log"

    for lf in [live_log, log_file]:
        if lf.exists():
            try:
                lines = lf.read_text(encoding="utf-8", errors="replace").splitlines()
                last_lines = lines[-30:]
                with st.expander(f" {lf.name} (30 dernières lignes)", expanded=lf == live_log):
                    st.code("\n".join(last_lines), language="text")
            except Exception:
                pass
