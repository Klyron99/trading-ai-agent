"""
Bibliothèque de graphiques Plotly pour le dashboard.
Tous les graphiques utilisent le thème sombre Bloomberg/TradingView.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Palette ───────────────────────────────────────────────────────────────────
_BG          = "#0a0e17"
_PAPER       = "#0a0e17"
_CARD        = "#131722"
_GRID        = "#1e2433"
_TEXT        = "#d1d4dc"
_MUTED       = "#787b86"
_GREEN       = "#26a69a"
_RED         = "#ef5350"
_BLUE        = "#2962ff"
_BLUE_LIGHT  = "#5c85ff"
_ORANGE      = "#ff9800"

_LAYOUT_BASE = dict(
    paper_bgcolor=_PAPER,
    plot_bgcolor=_BG,
    font=dict(family="Inter, Arial, sans-serif", color=_TEXT, size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(
        gridcolor=_GRID, linecolor=_GRID, tickcolor=_MUTED,
        tickfont=dict(color=_MUTED, size=10), showgrid=True,
    ),
    yaxis=dict(
        gridcolor=_GRID, linecolor=_GRID, tickcolor=_MUTED,
        tickfont=dict(color=_MUTED, size=10), showgrid=True,
    ),
    hoverlabel=dict(bgcolor=_CARD, bordercolor=_GRID, font_color=_TEXT, font_size=12),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=_GRID, font_color=_MUTED),
)


def _apply_base(fig: go.Figure, title: str = "") -> go.Figure:
    layout = dict(_LAYOUT_BASE)
    if title:
        layout["title"] = dict(text=title, font=dict(color=_TEXT, size=14, weight=600), x=0)
    fig.update_layout(**layout)
    return fig


# ── Equity Curve ──────────────────────────────────────────────────────────────

def equity_curve_chart(equity_curve: pd.DataFrame, initial_capital: float) -> go.Figure:
    """Courbe du capital avec aire de remplissage et annotations buy/sell."""
    fig = go.Figure()

    equity = equity_curve["equity"]
    dates  = equity_curve.index

    # Aire de remplissage gradient
    color_line = _GREEN if equity.iloc[-1] >= initial_capital else _RED
    fig.add_trace(go.Scatter(
        x=dates, y=equity,
        name="Capital",
        line=dict(color=color_line, width=2),
        fill="tozeroy",
        fillcolor=f"rgba({_hex_to_rgb(color_line)},0.06)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Capital : $%{y:,.0f}<extra></extra>",
    ))

    # Ligne du capital initial
    fig.add_hline(
        y=initial_capital,
        line_dash="dot",
        line_color=_MUTED,
        line_width=1,
        annotation_text=f"  Capital initial : ${initial_capital:,.0f}",
        annotation_font_color=_MUTED,
        annotation_font_size=10,
    )

    # Annotations buy/sell
    if "signal" in equity_curve.columns:
        signals = equity_curve["signal"]
        buys  = equity_curve[signals.diff() == 1]
        sells = equity_curve[signals.diff() == -2]

        if not buys.empty:
            fig.add_trace(go.Scatter(
                x=buys.index, y=buys["equity"],
                mode="markers",
                marker=dict(symbol="triangle-up", color=_GREEN, size=8),
                name="Achat",
                hovertemplate="<b>Achat</b><br>%{x|%d %b %Y}<br>$%{y:,.0f}<extra></extra>",
            ))
        if not sells.empty:
            fig.add_trace(go.Scatter(
                x=sells.index, y=sells["equity"],
                mode="markers",
                marker=dict(symbol="triangle-down", color=_RED, size=8),
                name="Vente",
                hovertemplate="<b>Vente</b><br>%{x|%d %b %Y}<br>$%{y:,.0f}<extra></extra>",
            ))

    _apply_base(fig, "Courbe du Capital")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(rangeslider=dict(visible=False))
    return fig


# ── Drawdown ─────────────────────────────────────────────────────────────────

def drawdown_chart(equity_curve: pd.DataFrame) -> go.Figure:
    """Graphique de drawdown avec coloration en dégradé."""
    equity = equity_curve["equity"]
    rolling_max = equity.cummax()
    drawdown = ((equity - rolling_max) / rolling_max) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_curve.index,
        y=drawdown,
        name="Drawdown",
        fill="tozeroy",
        fillcolor=f"rgba({_hex_to_rgb(_RED)},0.15)",
        line=dict(color=_RED, width=1.5),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Drawdown : %{y:.2f}%<extra></extra>",
    ))

    max_dd = drawdown.min()
    max_dd_date = drawdown.idxmin()
    fig.add_annotation(
        x=max_dd_date, y=max_dd,
        text=f"Max: {max_dd:.1f}%",
        showarrow=True, arrowhead=2,
        arrowcolor=_RED, font=dict(color=_RED, size=11),
        bgcolor=_CARD, bordercolor=_RED,
    )

    _apply_base(fig, "Drawdown (%)")
    fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    return fig


# ── PnL journalier ───────────────────────────────────────────────────────────

def daily_pnl_chart(equity_curve: pd.DataFrame) -> go.Figure:
    """Barres de PnL journalier avec coloration positive/négative."""
    daily_pnl = equity_curve["equity"].diff().dropna()
    colors = [_GREEN if v >= 0 else _RED for v in daily_pnl]

    fig = go.Figure(go.Bar(
        x=daily_pnl.index,
        y=daily_pnl.values,
        marker_color=colors,
        name="PnL journalier",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>PnL : $%{y:+,.2f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color=_MUTED, line_width=1)
    _apply_base(fig, "PnL Journalier ($)")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return fig


# ── Candlestick + Moyennes mobiles ───────────────────────────────────────────

def price_chart(df: pd.DataFrame, equity_curve: pd.DataFrame | None = None) -> go.Figure:
    """Graphique de prix OHLCV avec bougies japonaises et MA 20/50."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
        subplot_titles=("", "Volume"),
    )

    # Bougies
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="Prix",
        increasing_line_color=_GREEN, decreasing_line_color=_RED,
        increasing_fillcolor=_GREEN, decreasing_fillcolor=_RED,
    ), row=1, col=1)

    # MA 20
    ma20 = df["Close"].rolling(20).mean()
    fig.add_trace(go.Scatter(
        x=df.index, y=ma20, name="MA 20",
        line=dict(color=_ORANGE, width=1.5),
    ), row=1, col=1)

    # MA 50
    ma50 = df["Close"].rolling(50).mean()
    fig.add_trace(go.Scatter(
        x=df.index, y=ma50, name="MA 50",
        line=dict(color=_BLUE_LIGHT, width=1.5),
    ), row=1, col=1)

    # Volume
    vol_colors = [_GREEN if c >= o else _RED
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors, name="Volume",
        opacity=0.6,
    ), row=2, col=1)

    # Signaux buy/sell sur les bougie
    if equity_curve is not None and "signal" in equity_curve.columns:
        sig = equity_curve["signal"]
        buys  = df[sig.reindex(df.index).diff() == 1]
        sells = df[sig.reindex(df.index).diff() == -2]
        if not buys.empty:
            fig.add_trace(go.Scatter(
                x=buys.index, y=buys["Low"] * 0.995,
                mode="markers",
                marker=dict(symbol="triangle-up", color=_GREEN, size=9),
                name="Signal Achat",
            ), row=1, col=1)
        if not sells.empty:
            fig.add_trace(go.Scatter(
                x=sells.index, y=sells["High"] * 1.005,
                mode="markers",
                marker=dict(symbol="triangle-down", color=_RED, size=9),
                name="Signal Vente",
            ), row=1, col=1)

    _apply_base(fig, "Prix & Signaux")
    fig.update_layout(xaxis_rangeslider_visible=False)
    fig.update_xaxes(gridcolor=_GRID, row=2, col=1)
    fig.update_yaxes(gridcolor=_GRID, tickprefix="$", row=1, col=1)
    fig.update_yaxes(gridcolor=_GRID, row=2, col=1)
    for ann in fig.layout.annotations:
        ann.font.color = _MUTED
        ann.font.size = 10
    return fig


# ── Performance cumulée ──────────────────────────────────────────────────────

def cumulative_returns_chart(equity_curve: pd.DataFrame, initial_capital: float) -> go.Figure:
    """Performance cumulée en % depuis le début."""
    cum_ret = (equity_curve["equity"] / initial_capital - 1) * 100

    fig = go.Figure()
    color = _GREEN if cum_ret.iloc[-1] >= 0 else _RED
    fig.add_trace(go.Scatter(
        x=equity_curve.index, y=cum_ret,
        name="Perf. cumulée",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=f"rgba({_hex_to_rgb(color)},0.08)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>%{y:+.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=_MUTED, line_width=1, line_dash="dot")
    _apply_base(fig, "Performance Cumulée (%)")
    fig.update_yaxes(ticksuffix="%", tickformat="+.1f")
    return fig


# ── Rolling Sharpe ────────────────────────────────────────────────────────────

def rolling_sharpe_chart(rolling_sharpe: pd.Series) -> go.Figure:
    rs = rolling_sharpe.dropna()
    colors = [_GREEN if v >= 1 else _ORANGE if v >= 0 else _RED for v in rs]

    fig = go.Figure(go.Bar(
        x=rs.index, y=rs.values,
        marker_color=colors,
        name="Sharpe glissant (30j)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Sharpe : %{y:.3f}<extra></extra>",
    ))
    fig.add_hline(y=1, line_dash="dot", line_color=_GREEN, line_width=1,
                  annotation_text="  Sharpe = 1", annotation_font_color=_GREEN, annotation_font_size=10)
    fig.add_hline(y=0, line_color=_MUTED, line_width=1)
    _apply_base(fig, "Sharpe Ratio Glissant (30j)")
    return fig


# ── Feature importance ────────────────────────────────────────────────────────

def feature_importance_chart(importances: dict[str, float]) -> go.Figure:
    """Barres horizontales des importances de features."""
    labels = list(importances.keys())
    values = list(importances.values())
    colors = [_BLUE if v >= max(values) * 0.5 else _BLUE_LIGHT for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=labels,
        orientation="h",
        marker_color=colors,
        hovertemplate="<b>%{y}</b><br>Importance : %{x:.4f}<extra></extra>",
    ))
    _apply_base(fig, "Importance des Features (Random Forest)")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    fig.update_xaxes(tickformat=".3f")
    return fig


# ── Gauge probabilité haussière ───────────────────────────────────────────────

def bull_probability_gauge(probability: float) -> go.Figure:
    pct = probability * 100
    color = _GREEN if pct > 55 else _RED if pct < 45 else _ORANGE

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pct,
        delta=dict(reference=50, valueformat=".1f", suffix="%"),
        number=dict(suffix="%", valueformat=".1f", font=dict(color=color, size=36)),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=_MUTED,
                      tickfont=dict(color=_MUTED, size=10)),
            bar=dict(color=color, thickness=0.7),
            bgcolor=_CARD,
            borderwidth=1, bordercolor=_GRID,
            steps=[
                dict(range=[0, 45],  color=f"rgba({_hex_to_rgb(_RED)},0.15)"),
                dict(range=[45, 55], color=f"rgba({_hex_to_rgb(_ORANGE)},0.1)"),
                dict(range=[55, 100],color=f"rgba({_hex_to_rgb(_GREEN)},0.15)"),
            ],
            threshold=dict(line=dict(color=_TEXT, width=2), thickness=0.8, value=50),
        ),
        title=dict(text="Probabilité Haussière", font=dict(color=_MUTED, size=13)),
    ))

    fig.update_layout(
        paper_bgcolor=_BG,
        font=dict(color=_TEXT),
        margin=dict(l=20, r=20, t=60, b=20),
        height=280,
    )
    return fig


# ── RSI chart ─────────────────────────────────────────────────────────────────

def rsi_chart(features_df: pd.DataFrame) -> go.Figure:
    if "rsi_14" not in features_df.columns:
        return go.Figure()

    rsi = features_df["rsi_14"].dropna()
    colors = [_RED if v > 70 else _GREEN if v < 30 else _MUTED for v in rsi]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rsi.index, y=rsi,
        line=dict(color=_BLUE_LIGHT, width=1.5), name="RSI 14",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>RSI : %{y:.1f}<extra></extra>",
    ))
    fig.add_hrect(y0=70, y1=100, fillcolor=f"rgba({_hex_to_rgb(_RED)},0.08)",
                  line_width=0, annotation_text="  Surachat",
                  annotation_font_color=_RED, annotation_font_size=10)
    fig.add_hrect(y0=0, y1=30, fillcolor=f"rgba({_hex_to_rgb(_GREEN)},0.08)",
                  line_width=0, annotation_text="  Survente",
                  annotation_font_color=_GREEN, annotation_font_size=10)
    fig.add_hline(y=70, line_color=_RED, line_width=1, line_dash="dot")
    fig.add_hline(y=30, line_color=_GREEN, line_width=1, line_dash="dot")
    fig.add_hline(y=50, line_color=_MUTED, line_width=1)

    _apply_base(fig, "RSI 14")
    fig.update_yaxes(range=[0, 100])
    return fig


# ── Helper couleur ────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"
