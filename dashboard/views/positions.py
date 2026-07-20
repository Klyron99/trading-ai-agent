"""—" Positions ouvertes et exposition du portefeuille.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.components.metrics import divider, kpi_card, section_title
from dashboard.components.tables import positions_table
from dashboard.data_loader import get_live_account, run_backtest

_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"


def _donut_allocation(cash: float, positions_value: float) -> go.Figure:
    labels = ["Cash", "Positions"]
    values = [cash, positions_value]
    colors = [_MUTED, _BLUE]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.65,
        marker=dict(colors=colors, line=dict(color=_BG, width=2)),
        textfont=dict(color=_TEXT, size=12),
        hovertemplate="<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    total = cash + positions_value
    fig.add_annotation(
        text=f"<b>${total:,.0f}</b><br><span style='font-size:10px'>Total</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(color=_TEXT, size=16),
    )
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(font=dict(color=_MUTED), bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
        height=280,
    )
    return fig


def render(ticker: str, strategy: str, initial_capital: float) -> None:
    st.markdown(
        '<h2 style="margin:0 0 20px;color:#d1d4dc;font-size:20px;font-weight:700;">'
        'Positions Ouvertes</h2>',
        unsafe_allow_html=True,
    )

    # -"?-"? Données -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    live = get_live_account()

    if live and live.get("position"):
        # Mode Alpaca Paper réel
        pos = live["position"]
        price = live["live_price"]
        avg_price = pos.get("avg_price", price)
        qty = pos.get("qty", 0)
        unrealized = (price - avg_price) * qty
        pct = (price / avg_price - 1) * 100 if avg_price else 0

        positions = [{
            "Ticker": live["live_ticker"],
            "Quantité": qty,
            "Prix moy. ($)": round(avg_price, 2),
            "Prix actuel ($)": round(price, 2),
            "Valeur ($)": round(qty * price, 2),
            "PnL latent ($)": round(unrealized, 2),
            "PnL latent (%)": round(pct, 2),
        }]
        cash = live["cash"]
        portfolio_value = live["portfolio_value"]
        positions_value = portfolio_value - cash

    else:
        # Mode backtest
        with st.spinner("Chargement des positions-?-"):
            data = run_backtest(ticker, strategy, initial_capital)

        positions      = data["positions"]
        equity_curve   = data["equity_curve"]
        cash           = float(equity_curve["cash"].iloc[-1])
        portfolio_value = data["metrics"]["capital_final"]
        positions_value = portfolio_value - cash

    # -"?-"? KPIs allocation -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Allocation du Portefeuille")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Portefeuille Total", f"${portfolio_value:,.0f}", "", None, _BLUE)
    with k2:
        kpi_card("Cash", f"${cash:,.0f}",
                 f"{cash/portfolio_value*100:.1f}%", None, _MUTED)
    with k3:
        kpi_card("En Positions", f"${positions_value:,.0f}",
                 f"{positions_value/portfolio_value*100:.1f}%", None, _BLUE)
    with k4:
        kpi_card("Positions Ouvertes", str(len(positions)),
                 ticker if positions else "Aucune", None, _GREEN if positions else _MUTED)

    divider()

    # -"?-"? Donut allocation + table -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    chart_col, table_col = st.columns([1, 2])
    with chart_col:
        section_title("Répartition")
        st.plotly_chart(
            _donut_allocation(cash, positions_value),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with table_col:
        section_title("Détail des Positions")
        positions_table(positions)

    # -"?-"? Exposition par ticker -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if positions:
        divider()
        section_title("Risque & Exposition")
        for pos in positions:
            pnl = pos.get("PnL latent ($)", 0)
            pct = pos.get("PnL latent (%)", 0)
            color = _GREEN if pnl >= 0 else _RED

            st.markdown(
                f"""
                <div style="background:{_CARD};border:1px solid {_GRID};border-radius:6px;
                            padding:14px 18px;margin-bottom:10px;display:flex;
                            align-items:center;justify-content:space-between;">
                    <div>
                        <span style="font-weight:700;color:{_TEXT};font-size:15px;">
                            {pos['Ticker']}
                        </span>
                        <span style="color:{_MUTED};font-size:12px;margin-left:10px;">
                            {pos['Quantité']} actions @ ${pos["Prix moy. ($)"]:,.2f}
                        </span>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:{color};font-weight:700;font-size:14px;">
                            ${pnl:+,.2f}
                        </div>
                        <div style="color:{color};font-size:12px;">{pct:+.2f}%</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"""
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;
                        padding:40px;text-align:center;margin-top:20px;">
                <div style="font-size:32px;margin-bottom:12px;">"-</div>
                <div style="color:{_TEXT};font-weight:600;">Aucune position ouverte</div>
                <div style="color:{_MUTED};font-size:13px;margin-top:6px;">
                    Le portefeuille est 100% cash en fin de backtest.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
