"""—" Historique complet des ordres.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.metrics import divider, kpi_card, section_title
from dashboard.components.tables import trades_table
from dashboard.data_loader import run_backtest

_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"


def render(ticker: str, strategy: str, initial_capital: float) -> None:
    st.markdown(
        '<h2 style="margin:0 0 20px;color:#d1d4dc;font-size:20px;font-weight:700;">'
        'Historique des Trades</h2>',
        unsafe_allow_html=True,
    )

    with st.spinner("Chargement des trades-?-"):
        data = run_backtest(ticker, strategy, initial_capital)

    orders  = data["orders"]
    metrics = data["metrics"]

    if not orders:
        st.info("Aucun trade à afficher. Lancez d'abord un backtest.")
        return

    df = pd.DataFrame(orders)

    # -"?-"? KPIs résumé -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Résumé des Trades")

    sells_df = df[df["Sens"] == "VENTE"].copy() if "Sens" in df.columns else pd.DataFrame()
    pnl_series = sells_df["PnL ($)"].dropna() if "PnL ($)" in sells_df.columns else pd.Series([], dtype=float)

    total_trades = len(df)
    buy_count    = len(df[df["Sens"] == "ACHAT"]) if "Sens" in df.columns else 0
    sell_count   = len(df[df["Sens"] == "VENTE"]) if "Sens" in df.columns else 0
    total_pnl    = pnl_series.sum()
    winners      = int((pnl_series > 0).sum()) if not pnl_series.empty else 0
    losers       = int((pnl_series < 0).sum()) if not pnl_series.empty else 0
    best_trade   = float(pnl_series.max()) if not pnl_series.empty else 0
    worst_trade  = float(pnl_series.min()) if not pnl_series.empty else 0
    avg_pnl      = float(pnl_series.mean()) if not pnl_series.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Trades", str(total_trades),
                 f"{buy_count} achats · {sell_count} ventes", None, _BLUE)
    with c2:
        kpi_card("PnL Total Réalisé", f"${total_pnl:+,.2f}",
                 f"{winners} gagnants · {losers} perdants",
                 total_pnl >= 0, _GREEN if total_pnl >= 0 else _RED)
    with c3:
        kpi_card("Meilleur Trade", f"${best_trade:+,.2f}",
                 "PnL max réalisé", True, _GREEN)
    with c4:
        kpi_card("Pire Trade", f"${worst_trade:+,.2f}",
                 "PnL min réalisé", False, _RED)

    st.markdown('<div style="margin:12px 0;"></div>', unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        win_rate = (winners / sell_count * 100) if sell_count > 0 else 0
        kpi_card("Win Rate", f"{win_rate:.1f}%",
                 "Trades clos positifs", win_rate >= 50, _GREEN if win_rate >= 50 else _RED)
    with c6:
        kpi_card("PnL Moyen / Trade", f"${avg_pnl:+,.2f}",
                 "Sur trades clos", avg_pnl >= 0, _GREEN if avg_pnl >= 0 else _RED)
    with c7:
        profit_factor = (
            pnl_series[pnl_series > 0].sum() / abs(pnl_series[pnl_series < 0].sum())
            if (pnl_series < 0).any() else float("inf")
        )
        pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "-^z"
        kpi_card("Profit Factor", pf_str,
                 "Gains bruts / Pertes brutes", profit_factor >= 1, _GREEN if profit_factor >= 1 else _RED)
    with c8:
        kpi_card("Sharpe Ratio", f"{metrics['sharpe_ratio']:.3f}",
                 "Annualisé", metrics["sharpe_ratio"] >= 1)

    divider()

    # -"?-"? Distribution PnL -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if not pnl_series.empty:
        import plotly.graph_objects as go
        section_title("Distribution des PnL (Trades Clos)")

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=pnl_series,
            nbinsx=30,
            marker_color=[
                "#10b981" if v >= 0 else "#f43f5e" for v in pnl_series
            ],
            name="PnL",
            hovertemplate="PnL : $%{x:,.2f}<br>Fréquence : %{y}<extra></extra>",
        ))
        fig.add_vline(x=0, line_dash="dot", line_color="#64748b", line_width=1)
        fig.add_vline(x=avg_pnl, line_dash="dash", line_color="#ff9800", line_width=1.5,
                      annotation_text=f"  Moy: ${avg_pnl:+,.0f}",
                      annotation_font_color="#ff9800", annotation_font_size=10)
        fig.update_layout(
            paper_bgcolor="#080c14", plot_bgcolor="#080c14",
            font=dict(color="#e2e8f0"),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor="#1a2235", tickprefix="$", tickformat=",.0f",
                       title=dict(text="PnL ($)", font=dict(color="#64748b"))),
            yaxis=dict(gridcolor="#1a2235", title=dict(text="Fréquence", font=dict(color="#64748b"))),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        divider()

    # -"?-"? Tableau complet -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Tous les Trades")
    trades_table(orders, key="trades_main")
