"""—" Prix live de tous les tickers + graphique interactif.
"""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"

_ALL_TICKERS = ["BTC-USD", "QQQ", "AAPL", "MSFT", "SPY", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]

_PERIODS = {
    "Jour":         ("1d",  "5m",  True),
    "Semaine":      ("5d",  "30m", False),
    "Mois":         ("1mo", "1d",  False),
    "Année":        ("1y",  "1wk", False),
    "Depuis toujours": ("max", "1mo", False),
}


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_closes(tickers: list[str]) -> dict[str, float | None]:
    """—" mises en cache 1h (ne changent pas en journée)."""
    import yfinance as yf
    closes = {}
    try:
        data = yf.download(tickers, period="2d", interval="1d",
                           auto_adjust=False, progress=False, threads=True)
        if isinstance(data.columns, pd.MultiIndex):
            cl = data.get("Close", pd.DataFrame())
            for t in tickers:
                if t in cl.columns:
                    v = cl[t].dropna()
                    closes[t] = float(v.iloc[-2]) if len(v) >= 2 else (float(v.iloc[-1]) if not v.empty else None)
        else:
            if "Close" in data.columns:
                v = data["Close"].dropna()
                val = float(v.iloc[-2]) if len(v) >= 2 else (float(v.iloc[-1]) if not v.empty else None)
                for t in tickers:
                    closes[t] = val
    except Exception:
        pass
    return closes


def _fetch_lives(tickers: list[str]) -> dict[str, float | None]:
    """—" 1 seule requête HTTP pour tous les tickers, sans cache."""
    import yfinance as yf
    lives = {}
    try:
        data = yf.download(
            tickers, period="1d", interval="1m",
            auto_adjust=False, progress=False, threads=True, prepost=True,
            group_by="column",
        )
        if isinstance(data.columns, pd.MultiIndex):
            cl = data["Close"] if "Close" in data.columns.get_level_values(0) else pd.DataFrame()
            for t in tickers:
                if t in cl.columns:
                    v = cl[t].dropna()
                    if not v.empty:
                        lives[t] = float(v.iloc[-1])
        elif "Close" in data.columns:
            v = data["Close"].dropna()
            if not v.empty and len(tickers) == 1:
                lives[tickers[0]] = float(v.iloc[-1])
    except Exception:
        pass
    return lives


def _fetch_prices_bulk(tickers: list[str]) -> dict[str, dict]:
    closes = _fetch_closes(tickers)
    lives  = _fetch_lives(tickers)
    return {t: {"live": lives.get(t), "close": closes.get(t)} for t in tickers}


@st.cache_data(ttl=60)
def _fetch_chart(ticker: str, period: str, interval: str, prepost: bool) -> pd.DataFrame:
    import yfinance as yf
    try:
        df = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=True, progress=False, prepost=prepost,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()


def _price_card(ticker: str, live: float | None, close: float | None) -> str:
    if live and close:
        chg = live - close
        pct = chg / close * 100
        color = _GREEN if chg >= 0 else _RED
        arrow = "---" if chg >= 0 else "---"
        chg_html = (
            f'<div style="color:{color};font-size:12px;margin-top:2px;">'
            f'{arrow} {abs(chg):.2f} ({pct:+.2f}%)</div>'
        )
        price_str = f"${live:,.2f}"
    elif live:
        color = _TEXT
        chg_html = ""
        price_str = f"${live:,.2f}"
    else:
        color = _MUTED
        chg_html = ""
        price_str = "—"

    return f"""
    <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;
                padding:14px 16px;height:100%;">
        <div style="color:{_MUTED};font-size:10px;font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;">{ticker}</div>
        <div style="color:{color};font-size:20px;font-weight:700;margin-top:6px;">{price_str}</div>
        {chg_html}
    </div>"""


def render(ticker: str = "QQQ", **kwargs):
    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">-YO- Marchés</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:20px;">'
        f'Prix en temps réel · mis à jour toutes les 2 secondes</div>',
        unsafe_allow_html=True,
    )

    # -"?-"? Grille de prix live -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    @st.fragment(run_every=1)
    def _prix_grid():
        prices = _fetch_prices_bulk(_ALL_TICKERS)
        cols = st.columns(5)
        for i, t in enumerate(_ALL_TICKERS):
            with cols[i % 5]:
                info = prices[t]
                st.markdown(
                    _price_card(t, info["live"], info["close"]),
                    unsafe_allow_html=True,
                )
        st.markdown("<br>", unsafe_allow_html=True)

    _prix_grid()

    # -"?-"? Graphique interactif -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:1.5px;'
        f'margin:8px 0 16px;border-bottom:1px solid {_GRID};padding-bottom:8px;">Graphique</div>',
        unsafe_allow_html=True,
    )

    col_t, col_p = st.columns([2, 4])
    with col_t:
        sel_ticker = st.selectbox("Ticker", _ALL_TICKERS,
                                  index=_ALL_TICKERS.index(ticker) if ticker in _ALL_TICKERS else 0,
                                  key="marches_ticker")
    with col_p:
        st.markdown("<br>", unsafe_allow_html=True)
        period_label = st.radio(
            "", list(_PERIODS.keys()),
            horizontal=True,
            index=0,
            key="marches_period",
        )

    period, interval, prepost = _PERIODS[period_label]
    df = _fetch_chart(sel_ticker, period, interval, prepost)

    if df.empty:
        st.warning("Données indisponibles pour ce ticker / cette période.")
        return

    first = float(df["Close"].iloc[0])
    last  = float(df["Close"].iloc[-1])
    chg   = last - first
    pct   = chg / first * 100
    line_color = _GREEN if chg >= 0 else _RED
    fill_color = f"rgba({'38,166,154' if chg >= 0 else '239,83,80'},0.08)"

    fig = go.Figure()

    if period_label == "Jour":
        # Chandelier pour le jour
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            increasing_line_color=_GREEN, decreasing_line_color=_RED,
            increasing_fillcolor=_GREEN,  decreasing_fillcolor=_RED,
            name=sel_ticker,
        ))
    else:
        # Ligne pour les autres périodes
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Close"],
            mode="lines",
            line=dict(color=line_color, width=2),
            fill="tozeroy",
            fillcolor=fill_color,
            name=sel_ticker,
            hovertemplate="<b>%{x}</b><br>$%{y:,.2f}<extra></extra>",
        ))

    # Ligne de référence = premier prix
    fig.add_hline(
        y=first, line_dash="dash", line_color=_MUTED, line_width=1,
        annotation_text=f"Départ ${first:,.2f}",
        annotation_position="left",
        annotation_font_color=_MUTED,
    )

    arrow = "---" if chg >= 0 else "---"
    fig.update_layout(
        title=dict(
            text=f"{sel_ticker}  ·  ${last:,.2f}  "
                 f"<span style='color:{'#26a69a' if chg>=0 else '#ef5350'}'>"
                 f"{arrow} {abs(chg):.2f} ({pct:+.2f}%)</span>  ·  {period_label}",
            font=dict(color=_TEXT, size=14),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1117",
        font=dict(color=_TEXT, size=11),
        xaxis=dict(
            gridcolor=_GRID, showgrid=True, zeroline=False,
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False, tickprefix="$"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=50, b=0),
        height=420,
    )

    st.plotly_chart(fig, use_container_width=True)

    # -"?-"? Volume -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if "Volume" in df.columns and df["Volume"].sum() > 0:
        fig_vol = go.Figure(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color=[_GREEN if df["Close"].iloc[i] >= df["Open"].iloc[i] else _RED
                          for i in range(len(df))],
            opacity=0.6,
            hovertemplate="<b>%{x}</b><br>Volume: %{y:,.0f}<extra></extra>",
        ))
        fig_vol.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0d1117",
            font=dict(color=_TEXT, size=10),
            xaxis=dict(gridcolor=_GRID, showgrid=False, zeroline=False),
            yaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False),
            margin=dict(l=0, r=0, t=10, b=0),
            height=100,
            showlegend=False,
        )
        st.plotly_chart(fig_vol, use_container_width=True)
