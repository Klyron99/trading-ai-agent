""" Si j'avais investi $10 000, combien aurais-je aujourd'hui ?
"""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"
_PURPLE= "#7B2FFF"

CAPITAL = 10_000.0


def _card(label, value, sub=None, color=None):
    color = color or _TEXT
    sub_html = f'<div style="color:{_MUTED};font-size:11px;margin-top:6px;">{sub}</div>' if sub else ""
    st.markdown(
        f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;'
        f'padding:20px 24px;text-align:center;height:100%;">'
        f'<div style="color:{_MUTED};font-size:10px;font-weight:700;letter-spacing:1.5px;'
        f'text-transform:uppercase;margin-bottom:10px;">{label}</div>'
        f'<div style="font-size:28px;font-weight:800;color:{color};">{value}</div>'
        f'{sub_html}</div>',
        unsafe_allow_html=True,
    )


def _pnl_card(label, invest_date, price_then, price_now, color):
    if price_then is None or price_then <= 0:
        _card(label, "—", "Données indisponibles", _MUTED)
        return
    qty = CAPITAL / price_then
    value_now = qty * price_now
    gain = value_now - CAPITAL
    pct = gain / CAPITAL * 100
    sign = "+" if gain >= 0 else ""
    c = _GREEN if gain >= 0 else _RED
    arrow = "---" if gain >= 0 else "---"
    sub = f'{arrow} {sign}{gain:,.2f} $ ({sign}{pct:.2f}%) · depuis {invest_date}'
    _card(label, f"{value_now:,.2f} $", sub, c)


@st.cache_data(ttl=300, show_spinner=False)
def _fetch(ticker: str):
    import yfinance as yf
    try:
        df = yf.download(ticker, period="max", interval="1d",
                         auto_adjust=True, progress=False, threads=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Close"]].dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


def _price_at(df: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if df.empty:
        return None
    sub = df[df.index <= date]
    if sub.empty:
        return None
    return float(sub["Close"].iloc[-1])


def render(ticker: str = "BTC-USD", **kwargs):
    import plotly.graph_objects as go

    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:800;margin-bottom:4px;font-size:26px;">'
        f'💰 Simulation d\'investissement</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
        f'Si j\'avais investi <b style="color:{_TEXT};">${CAPITAL:,.0f}</b> '
        f'sur <b style="color:{_BLUE};">{ticker}</b>, combien aurais-je aujourd\'hui ?</div>',
        unsafe_allow_html=True,
    )

    # Ticker selector
    col_t, col_c, _ = st.columns([2, 2, 4])
    with col_t:
        tickers = ["BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ", "AMZN", "GOOGL"]
        sel = st.selectbox("Actif", tickers,
                           index=tickers.index(ticker) if ticker in tickers else 0,
                           key="sim_ticker")
    with col_c:
        capital_input = st.number_input("Capital investi ($)", min_value=100, max_value=1_000_000,
                                        value=int(CAPITAL), step=1000, key="sim_capital")

    capital = float(capital_input)

    with st.spinner("Chargement des données historiques..."):
        df = _fetch(sel)

    if df.empty:
        st.error("Impossible de charger les données pour ce ticker.")
        return

    price_now = float(df["Close"].iloc[-1])
    today = pd.Timestamp.today().normalize()

    # Dates de référence
    periods = {
        "Hier":      today - pd.Timedelta(days=1),
        "1 semaine": today - pd.Timedelta(weeks=1),
        "1 mois":    today - pd.DateOffset(months=1),
        "3 mois":    today - pd.DateOffset(months=3),
        "6 mois":    today - pd.DateOffset(months=6),
        "1 an":      today - pd.DateOffset(years=1),
        "3 ans":     today - pd.DateOffset(years=3),
        "5 ans":     today - pd.DateOffset(years=5),
        "10 ans":    today - pd.DateOffset(years=10),
        "Depuis le début": df.index[0],
    }

    # -"?-"? KPIs principaux -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:700;letter-spacing:1.8px;'
        f'text-transform:uppercase;margin:8px 0 16px;border-bottom:1px solid {_GRID};'
        f'padding-bottom:8px;">Cours actuel · {sel}</div>',
        unsafe_allow_html=True,
    )
    k1, k2, k3 = st.columns(3)
    with k1:
        _card("Cours actuel", f"${price_now:,.2f}", f"{sel} · en direct", _BLUE)
    with k2:
        p1y = _price_at(df, today - pd.DateOffset(years=1))
        if p1y:
            perf1y = (price_now - p1y) / p1y * 100
            c = _GREEN if perf1y >= 0 else _RED
            _card("Performance 1 an", f"{perf1y:+.1f}%", f"était ${p1y:,.2f} il y a 1 an", c)
        else:
            _card("Performance 1 an", "—", "", _MUTED)
    with k3:
        p_start = float(df["Close"].iloc[0])
        d_start = df.index[0].strftime("%d/%m/%Y")
        perf_all = (price_now - p_start) / p_start * 100
        c = _GREEN if perf_all >= 0 else _RED
        _card("Performance totale", f"{perf_all:+,.0f}%", f"depuis {d_start}", c)

    # -"?-"? Tableau des scénarios -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:700;letter-spacing:1.8px;'
        f'text-transform:uppercase;margin:28px 0 16px;border-bottom:1px solid {_GRID};'
        f'padding-bottom:8px;"—" si j\'avais investi ${capital:,.0f}</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for label, date in periods.items():
        p = _price_at(df, date)
        if p is None or p <= 0:
            continue
        qty = capital / p
        val = qty * price_now
        gain = val - capital
        pct = gain / capital * 100
        rows.append({
            "Période": label,
            "Date d'achat": pd.Timestamp(date).strftime("%d/%m/%Y"),
            "Prix d'achat": p,
            "Quantité": qty,
            "Valeur actuelle": val,
            "Gain / Perte ($)": gain,
            "Gain / Perte (%)": pct,
        })

    if not rows:
        st.warning("Pas assez de données historiques.")
        return

    # Cartes visuelles 4 colonnes
    display_periods = ["1 mois", "1 an", "5 ans", "Depuis le début"]
    display_rows = [r for r in rows if r["Période"] in display_periods]
    if display_rows:
        cols = st.columns(len(display_rows))
        for col, r in zip(cols, display_rows):
            with col:
                gain = r["Gain / Perte ($)"]
                pct = r["Gain / Perte (%)"]
                c = _GREEN if gain >= 0 else _RED
                sign = "+" if gain >= 0 else ""
                arrow = "---" if gain >= 0 else "---"
                st.markdown(
                    f'<div style="background:{_CARD};border:1px solid {_GRID};'
                    f'border-top:3px solid {c};border-radius:10px;padding:18px;text-align:center;">'
                    f'<div style="color:{_MUTED};font-size:10px;font-weight:700;'
                    f'letter-spacing:1.2px;text-transform:uppercase;margin-bottom:8px;">{r["Période"]}</div>'
                    f'<div style="font-size:22px;font-weight:800;color:{c};">'
                    f'{r["Valeur actuelle"]:,.0f} $</div>'
                    f'<div style="font-size:12px;color:{c};margin-top:6px;">'
                    f'{arrow} {sign}{gain:,.0f} $ ({sign}{pct:.1f}%)</div>'
                    f'<div style="font-size:10px;color:{_MUTED};margin-top:4px;">'
                    f'acheté le {r["Date d\'achat"]} à ${r["Prix d\'achat"]:,.2f}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Tableau complet
    st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
    df_table = pd.DataFrame(rows)
    df_display = df_table.copy()
    df_display["Prix d'achat"]      = df_display["Prix d'achat"].map(lambda x: f"${x:,.2f}")
    df_display["Quantité"]          = df_display["Quantité"].map(lambda x: f"{x:.6f}")
    df_display["Valeur actuelle"]   = df_display["Valeur actuelle"].map(lambda x: f"${x:,.2f}")
    df_display["Gain / Perte ($)"]  = df_display["Gain / Perte ($)"].map(lambda x: f"{'+'if x>=0 else ''}${x:,.2f}")
    df_display["Gain / Perte (%)"]  = df_display["Gain / Perte (%)"].map(lambda x: f"{'+'if x>=0 else ''}{x:.2f}%")

    def _style(val):
        s = str(val)
        if s.startswith("+"):  return f"color:{_GREEN};font-weight:700"
        if s.startswith("-"):  return f"color:{_RED};font-weight:700"
        return ""

    styled = df_display.style.map(_style, subset=["Gain / Perte ($)", "Gain / Perte (%)"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # -"?-"? Courbe de croissance -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:700;letter-spacing:1.8px;'
        f'text-transform:uppercase;margin:28px 0 16px;border-bottom:1px solid {_GRID};'
        f'padding-bottom:8px;">-?volution de ${capital:,.0f} investis dans le temps</div>',
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4 = st.tabs(["1 Mois", "1 An", "5 Ans", "Depuis le debut"])

    def _plot(period_label, start_date, tab):
        with tab:
            hist = df[df.index >= pd.Timestamp(start_date)].copy()
            if hist.empty or len(hist) < 2:
                st.info("Pas assez de données pour cette période.")
                return
            price_entry = float(hist["Close"].iloc[0])
            hist["valeur"] = (hist["Close"] / price_entry) * capital
            hist["gain"]   = hist["valeur"] - capital
            final = float(hist["valeur"].iloc[-1])
            gain_final = final - capital
            c = _GREEN if gain_final >= 0 else _RED
            rgb = "38,166,154" if gain_final >= 0 else "239,83,80"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist.index, y=hist["valeur"],
                mode="lines",
                line=dict(color=c, width=2),
                fill="tozeroy",
                fillcolor=f"rgba({rgb},0.08)",
                hovertemplate="<b>%{x|%d %b %Y}</b><br>Valeur : $%{y:,.2f}<extra></extra>",
                name="Valeur du portefeuille",
            ))
            fig.add_hline(
                y=capital, line_dash="dash", line_color=_MUTED, line_width=1,
                annotation_text=f"  Mise initiale ${capital:,.0f}",
                annotation_font_color=_MUTED, annotation_font_size=10,
            )
            # Point d'entrée
            fig.add_trace(go.Scatter(
                x=[hist.index[0]], y=[capital],
                mode="markers", marker=dict(color=_BLUE, size=10, symbol="circle"),
                name=f"Achat à ${price_entry:,.2f}",
                hovertemplate=f"Achat : ${price_entry:,.2f}<extra></extra>",
            ))
            # Point actuel
            fig.add_trace(go.Scatter(
                x=[hist.index[-1]], y=[final],
                mode="markers", marker=dict(color=c, size=10, symbol="circle"),
                name=f"Valeur actuelle ${final:,.2f}",
                hovertemplate=f"Valeur : ${final:,.2f}<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor=_BG, plot_bgcolor=_BG,
                font=dict(color=_TEXT, size=11),
                margin=dict(l=0, r=0, t=20, b=0),
                height=320,
                xaxis=dict(gridcolor=_GRID, showgrid=True),
                yaxis=dict(gridcolor=_GRID, showgrid=True, tickprefix="$"),
                legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.1),
                showlegend=True,
            )
            st.plotly_chart(fig, use_container_width=True)

            sign = "+" if gain_final >= 0 else ""
            st.markdown(
                f'<div style="display:flex;gap:16px;flex-wrap:wrap;">'
                f'<span style="background:{_CARD};border:1px solid {_GRID};border-radius:6px;'
                f'padding:6px 14px;font-size:12px;color:{_TEXT};">Valeur finale : '
                f'<b style="color:{c};">${final:,.2f}</b></span>'
                f'<span style="background:{_CARD};border:1px solid {_GRID};border-radius:6px;'
                f'padding:6px 14px;font-size:12px;color:{_TEXT};">Gain : '
                f'<b style="color:{c};">{sign}${gain_final:,.2f} ({sign}{gain_final/capital*100:.1f}%)</b></span>'
                f'<span style="background:{_CARD};border:1px solid {_GRID};border-radius:6px;'
                f'padding:6px 14px;font-size:12px;color:{_TEXT};">Quantité achetée : '
                f'<b>{capital/price_entry:.6f} {sel.replace("-USD","")}</b></span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    _plot("1 Mois",         today - pd.DateOffset(months=1),  tab1)
    _plot("1 An",           today - pd.DateOffset(years=1),   tab2)
    _plot("5 Ans",          today - pd.DateOffset(years=5),   tab3)
    _plot("Depuis le début", df.index[0],                     tab4)
