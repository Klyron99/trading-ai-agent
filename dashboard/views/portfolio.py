"""
Page Portfolio — Vue principale du capital et de l'equity curve.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.charts import (
    cumulative_returns_chart,
    equity_curve_chart,
    price_chart,
)
from dashboard.components.metrics import (
    divider,
    kpi_card,
    section_title,
    signal_badge,
    status_indicator,
)
from dashboard.data_loader import (
    compute_daily_pnl,
    format_currency,
    format_pct,
    get_live_account,
    get_ohlcv,
    run_backtest,
)


def render(ticker: str, strategy: str, initial_capital: float) -> None:
    # ── En-tête ──────────────────────────────────────────────────────────────
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.markdown(
            f'<h2 style="margin:0;color:#d1d4dc;font-size:20px;font-weight:700;">'
            f'Portfolio — {ticker}</h2>',
            unsafe_allow_html=True,
        )
    with status_col:
        live = get_live_account()
        status_indicator("ALPACA PAPER" if live else "SIMULATION")

    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

    # ── Chargement des données ────────────────────────────────────────────────
    with st.spinner("Chargement du backtest…"):
        data = run_backtest(ticker, strategy, initial_capital)

    equity_curve = data["equity_curve"]
    metrics      = data["metrics"]

    # Si mode live disponible, on affiche les vraies valeurs Alpaca en priorité
    if live:
        portfolio_val = live["portfolio_value"]
        cash_val      = live["cash"]
        pnl_val       = portfolio_val - initial_capital
        pnl_pct       = (pnl_val / initial_capital) * 100
    else:
        portfolio_val = metrics["capital_final"]
        cash_val      = equity_curve["cash"].iloc[-1]
        pnl_val       = portfolio_val - initial_capital
        pnl_pct       = metrics["performance_totale"]

    # ── Signal actuel ────────────────────────────────────────────────────────
    current_signal = int(equity_curve["signal"].iloc[-1])
    current_price  = float(equity_curve["price"].iloc[-1])

    # ── Rang 1 : métriques principales ───────────────────────────────────────
    section_title("Métriques du Portefeuille")
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card(
            "Capital Total",
            f"${portfolio_val:,.0f}",
            f"Initial : ${initial_capital:,.0f}",
            None,
            accent_color="#3b82f6",
        )
    with c2:
        kpi_card(
            "Cash Disponible",
            f"${cash_val:,.0f}",
            f"{cash_val/portfolio_val*100:.1f}% du portefeuille",
            None,
            accent_color="#64748b",
        )
    with c3:
        kpi_card(
            "PnL Total",
            format_currency(pnl_val),
            format_pct(pnl_pct),
            pnl_val >= 0,
            accent_color="#10b981" if pnl_val >= 0 else "#f43f5e",
        )
    with c4:
        kpi_card(
            "Prix Actuel",
            f"${current_price:,.2f}",
            ticker,
            None,
            accent_color="#ff9800",
        )

    st.markdown('<div style="margin:12px 0;"></div>', unsafe_allow_html=True)

    # ── Rang 2 : métriques secondaires ───────────────────────────────────────
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        kpi_card("Sharpe Ratio",   f"{metrics['sharpe_ratio']:.3f}",
                 "Annualisé (252j)", metrics["sharpe_ratio"] >= 1)
    with c6:
        kpi_card("Drawdown Max",   f"{metrics['drawdown_max']:.2f}%",
                 "Perte max depuis pic", False)
    with c7:
        kpi_card("Nb Trades",      str(metrics["nombre_trades"]),
                 f"Win rate : {metrics['taux_reussite_pct']:.1f}%", None)
    with c8:
        kpi_card("Win Rate",       f"{metrics['taux_reussite_pct']:.1f}%",
                 "Trades positifs / total", metrics["taux_reussite_pct"] >= 50)

    divider()

    # ── Signal actuel ────────────────────────────────────────────────────────
    sig_col, _ = st.columns([1, 3])
    with sig_col:
        section_title("Signal Actuel")
        signal_badge(current_signal)

    divider()

    # ── Equity curve ─────────────────────────────────────────────────────────
    section_title("Courbe du Capital")
    st.plotly_chart(
        equity_curve_chart(equity_curve, initial_capital),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # ── Prix & signaux ───────────────────────────────────────────────────────
    section_title("Prix & Signaux (6 derniers mois)")
    df_ohlcv = get_ohlcv(ticker)
    df_recent = df_ohlcv.tail(126)
    eq_recent = equity_curve.reindex(df_recent.index, method="nearest")
    st.plotly_chart(
        price_chart(df_recent, eq_recent),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # ── Performance cumulée ──────────────────────────────────────────────────
    section_title("Performance Cumulée (%)")
    st.plotly_chart(
        cumulative_returns_chart(equity_curve, initial_capital),
        use_container_width=True,
        config={"displayModeBar": False},
    )
