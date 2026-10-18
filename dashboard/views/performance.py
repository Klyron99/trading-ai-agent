""" -?volution du capital, taux de réussite, métriques de l'agent.
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"
_BG     = "#080c14"

_DB_PATH = _ROOT / "agent" / "memory_store" / "agent_memory.db"

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except ImportError:
    _PLOTLY = False


def _card(label, value, color=None, sub=None):
    color = color or _TEXT
    sub_html = f'<div style="color:{_MUTED};font-size:11px;margin-top:4px;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;
                padding:16px 20px;margin-bottom:8px;">
        <div style="color:{_MUTED};font-size:11px;font-weight:600;
                    text-transform:uppercase;letter-spacing:1px;">{label}</div>
        <div style="color:{color};font-size:24px;font-weight:700;margin-top:6px;">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def _section(title):
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:1.5px;'
        f'margin:28px 0 12px;border-bottom:1px solid {_GRID};padding-bottom:8px;">{title}</div>',
        unsafe_allow_html=True,
    )


def _layout(fig, title="", height=320):
    fig.update_layout(
        title=title,
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(color=_TEXT, size=11),
        xaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False),
        yaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=_GRID, orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=30, b=0),
        height=height,
    )
    return fig


def _read_broker_state(ticker: str) -> dict | None:
    """Lit l'état live du broker depuis broker_state."""
    try:
        con = sqlite3.connect(str(_DB_PATH), timeout=5)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_checkpoint(FULL)")
        row = con.execute(
            "SELECT cash, positions, updated_at FROM broker_state WHERE ticker=?", (ticker,)
        ).fetchone()
        con.close()
        if row:
            return {"cash": float(row[0]), "positions": json.loads(row[1]), "updated_at": row[2]}
    except Exception:
        pass
    return None


def _read_portfolio_history(ticker: str) -> list[dict]:
    try:
        con = sqlite3.connect(str(_DB_PATH), timeout=5)
        con.execute("PRAGMA journal_mode=WAL")
        rows = con.execute(
            "SELECT ts, cash, positions_value, total_value, action FROM portfolio_snapshots "
            "WHERE ticker=? ORDER BY ts ASC", (ticker,)
        ).fetchall()
        con.close()
        return [{"ts": r[0], "cash": r[1], "positions_value": r[2],
                 "total_value": r[3], "action": r[4]} for r in rows]
    except Exception:
        return []


def _read_decisions(ticker: str) -> list[dict]:
    try:
        con = sqlite3.connect(str(_DB_PATH), timeout=5)
        con.execute("PRAGMA journal_mode=WAL")
        rows = con.execute(
            "SELECT ts, action, confidence, strategy, price, ml_prob, reason "
            "FROM decisions WHERE ticker=? ORDER BY ts DESC LIMIT 1000", (ticker,)
        ).fetchall()
        con.close()
        return [{"ts": r[0], "action": r[1], "confidence": r[2], "strategy": r[3],
                 "price": r[4], "ml_prob": r[5], "reason": r[6]} for r in rows]
    except Exception:
        return []


def render(ticker: str = "BTC-USD", **kwargs):
    from config.settings import INITIAL_CAPITAL

    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">Performance</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
        f'Résultats et évolution de l\'agent sur <b style="color:{_BLUE};">{ticker}</b></div>',
        unsafe_allow_html=True,
    )

    if not _PLOTLY:
        st.warning("Installez plotly : `pip install plotly`")
        return

    # -"?-"? Lecture données statiques -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    portfolio_hist  = _read_portfolio_history(ticker)
    decisions_raw   = _read_decisions(ticker)

    # -"?-"—" se rafraîchit toutes les 5s -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    _section(f"Etat du portefeuille — {ticker}")

    @st.fragment(run_every=2)
    def _live_portfolio():
        broker_state = _read_broker_state(ticker)
        if not broker_state:
            st.info(f"Aucun état broker pour {ticker}. Lance l'agent sur ce ticker.")
            return

        cash      = broker_state["cash"]
        raw_pos   = broker_state["positions"]
        longs     = raw_pos.get("long",  raw_pos)
        shorts    = raw_pos.get("short", {})
        is_short  = False
        pos_qty   = 0.0
        pos_avg   = 0.0
        if ticker in longs:
            pos_qty  = float(longs[ticker].get("qty", 0))
            pos_avg  = float(longs[ticker].get("avg_price", 0))
        elif ticker in shorts:
            pos_qty  = float(shorts[ticker].get("qty", 0))
            pos_avg  = float(shorts[ticker].get("avg_price", 0))
            is_short = True

        try:
            import yfinance as yf
            _h = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=True)
            live_price = float(_h["Close"].iloc[-1]) if not _h.empty else pos_avg
        except Exception:
            live_price = pos_avg

        # Partage le prix live avec le reste de la page
        st.session_state[f"_perf_live_{ticker}"] = live_price

        # SHORT : le cash inclut les recettes de la vente — on soustrait le coût de rachat
        if is_short:
            pos_value = -(pos_qty * live_price)
        else:
            pos_value = pos_qty * live_price
        total_val = cash + pos_value
        pnl       = total_val - INITIAL_CAPITAL
        pnl_pct   = pnl / INITIAL_CAPITAL * 100
        pnl_c     = _GREEN if pnl >= 0 else _RED
        pnl_sign  = "+" if pnl >= 0 else ""
        updated   = broker_state.get("updated_at", "")[:16].replace("T", " ")

        b1, b2, b3, b4, b5 = st.columns(5)
        with b1:
            _card("Capital initial", f"${INITIAL_CAPITAL:,.0f}", color=_MUTED)
        with b2:
            _card("Valeur totale", f"${total_val:,.2f}", color=_TEXT,
                  sub=f"live · prix {ticker} : ${live_price:,.2f}")
        with b3:
            _card("P&L total", f"{pnl_sign}${pnl:,.2f}",
                  color=pnl_c, sub=f"{pnl_sign}{pnl_pct:.2f}% depuis le début")
        with b4:
            display_cash = cash + pos_value if is_short else cash
            _cash_sub = "net · dette short déduite" if is_short else "Non investi"
            _card("Cash disponible", f"${display_cash:,.2f}", color=_BLUE, sub=_cash_sub)
        with b5:
            if pos_qty > 0:
                if is_short:
                    unrealized = (pos_avg - live_price) * pos_qty
                else:
                    unrealized = (live_price - pos_avg) * pos_qty
                ur_pct       = unrealized / (pos_avg * pos_qty) * 100
                ur_sign      = "+" if unrealized >= 0 else ""
                ur_c         = _GREEN if unrealized >= 0 else _RED
                _card(
                    f"P&L non réalisé ({'SHORT' if is_short else 'LONG'})",
                    f"{ur_sign}${unrealized:,.2f}",
                    color=ur_c,
                    sub=f"{ur_sign}{ur_pct:.2f}% · {pos_qty:.6f} {ticker.replace('-USD','')} @ ${pos_avg:,.2f}"
                )
            else:
                _card("Position ouverte", "Aucune", color=_MUTED, sub="Pas de position active")

        st.caption(f"Mise à jour live toutes les 2s · Dernier trade broker : {updated} UTC")

    _live_portfolio()

    # -"?-"? Courbe d'évolution du capital -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if portfolio_hist:
        _section("Évolution du capital (snapshots réels)")
        df_port = pd.DataFrame(portfolio_hist)
        df_port["ts"] = pd.to_datetime(df_port["ts"], errors="coerce", utc=True).dt.tz_localize(None) + pd.Timedelta(hours=2)
        df_port = df_port.dropna(subset=["ts"]).reset_index(drop=True)

        final_v = float(df_port["total_value"].iloc[-1])
        gain_v  = final_v - INITIAL_CAPITAL
        gc      = _GREEN if gain_v >= 0 else _RED
        rgb     = "38,166,154" if gain_v >= 0 else "239,83,80"

        # Gain relatif au capital initial — axe Y zoomé sur les vraies variations
        df_port["gain"] = df_port["total_value"] - INITIAL_CAPITAL

        if df_port.empty:
            st.info("Pas encore de snapshots valides pour ce ticker.")
        col_g, col_i = st.columns([3, 1])
        with col_g:
          try:
            fig = go.Figure()

            # Zone remplie sous la courbe
            fig.add_trace(go.Scatter(
                x=df_port["ts"], y=df_port["gain"],
                mode="lines", line=dict(color=gc, width=2.5),
                fill="tozeroy", fillcolor=f"rgba({rgb},0.10)",
                name="Capital",
                hovertemplate="<b>%{x|%d/%m %H:%M}</b><br>Gain : <b>%{customdata}</b><extra></extra>",
                customdata=[f"{'+'if v>=0 else ''}${v:,.2f} ({v/INITIAL_CAPITAL*100:+.2f}%)" for v in df_port["gain"]],
            ))

            # Ligne zéro = capital initial
            fig.add_hline(y=0, line_dash="dot", line_color=_MUTED, line_width=1,
                          annotation_text=f"Départ ${INITIAL_CAPITAL:,.0f}",
                          annotation_font_color=_MUTED, annotation_position="bottom right",
                          annotation_font_size=10)

            buys_p  = df_port[df_port["action"].isin(["BUY", "SHORT"])]
            sells_p = df_port[df_port["action"].isin(["SELL", "COVER"])]
            reinf_p = df_port[df_port["action"].isin(["REINFORCE_LONG", "REINFORCE_SHORT"])]

            if not buys_p.empty:
                fig.add_trace(go.Scatter(
                    x=buys_p["ts"], y=buys_p["gain"],
                    mode="markers", name="Entrée",
                    marker=dict(color=_GREEN, size=12, symbol="triangle-up",
                                line=dict(color="white", width=1)),
                    hovertemplate="<b>Entrée</b> %{x|%d/%m %H:%M}<br>Gain : %{customdata}<extra></extra>",
                    customdata=[f"{'+'if v>=0 else ''}${v:,.2f}" for v in buys_p["gain"]],
                ))

            if not sells_p.empty:
                # Alterner textposition pour éviter les chevauchements
                positions = []
                for i in range(len(sells_p)):
                    positions.append("top center" if i % 2 == 0 else "bottom center")
                fig.add_trace(go.Scatter(
                    x=sells_p["ts"], y=sells_p["gain"],
                    mode="markers+text", name="Sortie",
                    text=[f"{'+'if v>=0 else ''}${v:,.0f}" for v in sells_p["gain"]],
                    textposition=positions,
                    textfont=dict(color=_RED, size=10, family="monospace"),
                    marker=dict(color=_RED, size=12, symbol="triangle-down",
                                line=dict(color="white", width=1)),
                    hovertemplate="<b>Sortie</b> %{x|%d/%m %H:%M}<br>Gain : %{customdata}<extra></extra>",
                    customdata=[f"{'+'if v>=0 else ''}${v:,.2f}" for v in sells_p["gain"]],
                ))

            if not reinf_p.empty:
                fig.add_trace(go.Scatter(
                    x=reinf_p["ts"], y=reinf_p["gain"],
                    mode="markers", name="Renfort",
                    marker=dict(color=_ORANGE, size=10, symbol="diamond",
                                line=dict(color="white", width=1)),
                    hovertemplate="<b>Renfort</b> %{x|%d/%m %H:%M}<br>Gain : %{customdata}<extra></extra>",
                    customdata=[f"{'+'if v>=0 else ''}${v:,.2f}" for v in reinf_p["gain"]],
                ))

            # Axe Y zoomé
            _yvals = df_port["gain"].dropna()
            _ymin  = min(_yvals.min(), 0)
            _ymax  = _yvals.max()
            _ypad  = max((_ymax - _ymin) * 0.30, 5)

            fig.update_layout(
                yaxis=dict(
                    range=[_ymin - _ypad, _ymax + _ypad],
                    tickprefix="$", tickformat="+,.0f",
                    zeroline=False, gridcolor=_GRID,
                    title=dict(text="Gain / Perte ($)", font=dict(size=10, color=_MUTED)),
                ),
                xaxis=dict(
                    gridcolor=_GRID, showgrid=True,
                    rangeslider=dict(visible=True, thickness=0.04, bgcolor=_CARD),
                    rangeselector=dict(
                        bgcolor=_CARD, bordercolor=_GRID, borderwidth=1,
                        font=dict(color=_TEXT, size=10),
                        buttons=[
                            dict(count=6,  label="6h",  step="hour",  stepmode="backward"),
                            dict(count=24, label="24h", step="hour",  stepmode="backward"),
                            dict(count=3,  label="3j",  step="day",   stepmode="backward"),
                            dict(step="all", label="Tout"),
                        ]
                    ),
                ),
                hoverlabel=dict(bgcolor=_CARD, bordercolor=_GRID,
                                font=dict(color=_TEXT, size=12)),
                hovermode="x unified",
            )
            st.plotly_chart(_layout(fig, height=380), use_container_width=True)
          except Exception as _e:
            st.error(f"Erreur graphique : {_e}")
        with col_i:
            st.markdown("<br>", unsafe_allow_html=True)

            @st.fragment(run_every=2)
            def _live_sidebar_cards():
                live_p = st.session_state.get(f"_perf_live_{ticker}", 0)
                bs = _read_broker_state(ticker)
                if bs and live_p > 0:
                    _cash   = bs["cash"]
                    _raw    = bs["positions"]
                    _longs  = _raw.get("long",  _raw)
                    _shorts = _raw.get("short", {})
                    _qty = 0.0; _is_short = False
                    if ticker in _longs:
                        _qty = float(_longs[ticker].get("qty", 0))
                    elif ticker in _shorts:
                        _qty = float(_shorts[ticker].get("qty", 0))
                        _is_short = True
                    # Valeur réelle : soustraire coût de rachat pour les shorts
                    _pos_val    = -(_qty * live_p) if _is_short else (_qty * live_p)
                    _live_total = _cash + _pos_val
                    _live_gain  = _live_total - INITIAL_CAPITAL
                    _gc = _GREEN if _live_gain >= 0 else _RED
                    _card("Capital réel", f"${_live_total:,.2f}", color=_gc, sub="live · short déduit")
                    _card("Gain / Perte", f"${_live_gain:+,.2f}", color=_gc,
                          sub=f"{_live_gain/INITIAL_CAPITAL*100:+.2f}%")
                else:
                    _gc = _GREEN if gain_v >= 0 else _RED
                    _card("Capital réel", f"${final_v:,.2f}", color=_gc)
                    _card("Gain / Perte", f"${gain_v:+,.2f}", color=_gc)
                # Ne compter que les ordres après le dernier RESET pour éviter les doublons
                _reset_idx = df_port[df_port["action"] == "RESET"].index
                _df_since = df_port.iloc[_reset_idx[-1]+1:] if len(_reset_idx) else df_port
                n_buys  = int(_df_since["action"].isin(["BUY", "SHORT"]).sum())
                n_reinf = int(_df_since["action"].isin(["REINFORCE_LONG", "REINFORCE_SHORT"]).sum())
                n_sells = int(_df_since["action"].isin(["SELL", "COVER"]).sum())
                label = f"{n_buys} entrée{'s' if n_buys>1 else ''}"
                if n_reinf: label += f" +{n_reinf} renf."
                label += f" - {n_sells} sortie{'s' if n_sells>1 else ''}"
                _card("Ordres exécutés", label, color=_BLUE)

            _live_sidebar_cards()

    # -"?-"? Analyse des décisions -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if not decisions_raw:
        st.info("Aucune décision enregistrée. Lance l'agent pour commencer.")
        return

    df = pd.DataFrame(decisions_raw)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True).dt.tz_localize(None) + pd.Timedelta(hours=2)
    df = df.dropna(subset=["ts"]).reset_index(drop=True)
    df = df.sort_values("ts").reset_index(drop=True)

    total  = len(df)
    buys   = (df["action"] == "BUY").sum()
    sells  = (df["action"] == "SELL").sum()
    holds  = (df["action"] == "HOLD").sum()
    avg_c  = df["confidence"].mean()

    # Trades complets depuis les snapshots portfolio (cash réel avant/après)
    # Source unique : portfolio_snapshots — cash après SELL/COVER minus cash avant première entrée
    trades = []
    try:
        import sqlite3 as _sq
        _con = _sq.connect(str(_DB_PATH), timeout=5)
        _con.execute("PRAGMA journal_mode=WAL")
        snaps = _con.execute(
            "SELECT ts, cash, total_value, action FROM portfolio_snapshots WHERE ticker=? ORDER BY ts ASC",
            (ticker,)
        ).fetchall()
        _con.close()
        capital_before = None   # total_value juste AVANT la première entrée
        prev_total = None
        for ts_s, cash_s, total_s, act_s in snaps:
            if act_s in ("BUY", "SHORT") and capital_before is None:
                # On utilise le total_value du snapshot précédent (avant l'entrée)
                capital_before = prev_total if prev_total is not None else INITIAL_CAPITAL
            elif act_s in ("SELL", "COVER") and capital_before is not None:
                pnl_usd = float(total_s) - capital_before
                pnl_pct = pnl_usd / capital_before * 100
                trades.append({"ts": ts_s, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct,
                               "side": "LONG" if act_s == "SELL" else "SHORT"})
                capital_before = None
            prev_total = float(total_s)
    except Exception:
        pass

    n_trades   = len(trades)
    win_trades = sum(1 for t in trades if t["pnl_usd"] > 0)
    win_rate   = win_trades / n_trades if n_trades else 0
    avg_pnl    = sum(t["pnl_pct"] for t in trades) / n_trades if n_trades else 0
    total_pnl  = sum(t["pnl_pct"] for t in trades)

    _section("Vue d'ensemble des décisions")
    if df.empty:
        st.info("Aucune décision valide à afficher.")
        return

    @st.fragment(run_every=2)
    def _live_kpis():
        _live = st.session_state.get(f"_perf_live_{ticker}", 0)
        _bs   = _read_broker_state(ticker)
        ur_pnl = 0.0; ur_pct = 0.0
        if _bs and _live > 0:
            _pos = _bs["positions"].get(ticker, {})
            _qty = float(_pos.get("qty", 0))
            _avg = float(_pos.get("avg_price", 0))
            if _qty > 0 and _avg > 0:
                ur_pnl = (_live - _avg) * _qty
                ur_pct = (_live - _avg) / _avg * 100

        # P&L non réalisé (live) — short ou long
        _live = st.session_state.get(f"_perf_live_{ticker}", 0)
        _bs   = _read_broker_state(ticker)
        ur_pnl = 0.0; ur_pct = 0.0; has_position = False
        if _bs and _live > 0:
            _raw  = _bs["positions"]
            _longs  = _raw.get("long",  _raw)
            _shorts = _raw.get("short", {})
            if ticker in _longs:
                _qty = float(_longs[ticker].get("qty", 0))
                _avg = float(_longs[ticker].get("avg_price", 0))
                if _qty > 0 and _avg > 0:
                    ur_pnl = (_live - _avg) * _qty
                    ur_pct = (_live - _avg) / _avg * 100
                    has_position = True
            elif ticker in _shorts:
                _qty = float(_shorts[ticker].get("qty", 0))
                _avg = float(_shorts[ticker].get("avg_price", 0))
                if _qty > 0 and _avg > 0:
                    ur_pnl = (_avg - _live) * _qty
                    ur_pct = (_avg - _live) / _avg * 100
                    has_position = True

        # P&L total réalisé en $
        total_pnl_usd = sum(t.get("pnl_usd", 0) for t in trades)

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        with k1: _card("Décisions", str(total))
        with k2: _card("Trades complets", str(n_trades), color=_BLUE,
                       sub="LONG + SHORT clôturés")
        with k3: _card("Taux de réussite", f"{win_rate:.0%}",
                       color=_GREEN if win_rate >= 0.5 else (_MUTED if n_trades == 0 else _RED))
        avg_pnl_usd = total_pnl_usd / n_trades if n_trades else 0
        with k4:
            if n_trades > 0:
                s = "+" if avg_pnl_usd >= 0 else ""
                _card("P&L réalisé moy.", f"{s}${avg_pnl_usd:,.2f}",
                      color=_GREEN if avg_pnl_usd >= 0 else _RED,
                      sub=f"{'+' if avg_pnl >= 0 else ''}{avg_pnl:.2f}% par trade")
            elif has_position:
                ur_c = _GREEN if ur_pnl >= 0 else _RED
                ur_s = "+" if ur_pnl >= 0 else ""
                _card("P&L non réalisé", f"{ur_s}${ur_pnl:,.2f}", color=ur_c,
                      sub=f"{ur_s}{ur_pct:.2f}% · live")
            else:
                _card("P&L réalisé moy.", "—", color=_MUTED)
        with k5:
            if n_trades > 0:
                s = "+" if total_pnl_usd >= 0 else ""
                _card("P&L total réalisé", f"{s}${total_pnl_usd:,.2f}",
                      color=_GREEN if total_pnl_usd >= 0 else _RED)
            elif has_position:
                ur_c = _GREEN if ur_pnl >= 0 else _RED
                ur_s = "+" if ur_pnl >= 0 else ""
                _card("Position ouverte", f"{ur_s}${ur_pnl:,.2f}", color=ur_c,
                      sub="En attente de clôture")
            else:
                _card("P&L total réalisé", "—", color=_MUTED)
        with k6: _card("Confiance moy.", f"{avg_c:.0%}", color=_BLUE)

    _live_kpis()

    # -"?-"? 3 graphiques analyse -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    _section("Analyse détaillée")
    col_pie, col_conf, col_pnl = st.columns(3)

    with col_pie:
        fig_pie = go.Figure(go.Pie(
            labels=["BUY", "SELL", "HOLD"],
            values=[int(buys), int(sells), int(holds)],
            hole=0.55,
            marker=dict(colors=[_GREEN, _RED, _MUTED]),
            textinfo="label+percent",
            hovertemplate="%{label}: %{value}<extra></extra>",
        ))
        fig_pie.update_layout(
            paper_bgcolor=_BG, plot_bgcolor=_BG, font=dict(color=_TEXT),
            showlegend=False, margin=dict(l=0, r=0, t=30, b=0), height=280,
            title=dict(text="Répartition des actions", font=dict(color=_MUTED, size=11)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_conf:
        fig_h = go.Figure(go.Histogram(
            x=df["confidence"], nbinsx=20,
            marker_color=_BLUE, opacity=0.8,
            hovertemplate="Confiance: %{x:.0%}<br>N: %{y}<extra></extra>",
        ))
        _layout(fig_h, "Distribution confiance ML", height=280)
        fig_h.update_xaxes(tickformat=".0%")
        fig_h.add_vline(x=0.60, line_dash="dash", line_color=_ORANGE,
                        annotation_text="Seuil 60%", annotation_font_color=_ORANGE)
        st.plotly_chart(fig_h, use_container_width=True)

    with col_pnl:
        if trades:
            pnl_vals = [t["pnl_pct"] for t in trades]
            fig_b = go.Figure(go.Bar(
                x=list(range(1, len(pnl_vals)+1)), y=pnl_vals,
                marker_color=[_GREEN if v >= 0 else _RED for v in pnl_vals],
                text=[f"{v:+.1f}%" for v in pnl_vals], textposition="outside",
                hovertemplate="Trade #%{x}<br>P&L: %{y:+.2f}%<extra></extra>",
            ))
            _layout(fig_b, "P&L par trade (%)", height=280)
            fig_b.add_hline(y=0, line_color=_MUTED, line_width=1)
            st.plotly_chart(fig_b, use_container_width=True)
        else:
            st.info("En attente du 1er trade complet (BUY -?' SELL).")

    # -"?-"? Confiance dans le temps -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if len(df) > 3:
        _section("Confiance ML dans le temps")
        fig_ts = go.Figure()
        for action, color in [("BUY", _GREEN), ("SELL", _RED), ("HOLD", _MUTED)]:
            mask = df["action"] == action
            if mask.any():
                fig_ts.add_trace(go.Scatter(
                    x=df.loc[mask, "ts"], y=df.loc[mask, "confidence"],
                    mode="markers", name=action,
                    marker=dict(color=color, size=8, opacity=0.85),
                    hovertemplate=f"<b>{action}</b> · %{{x}}<br>Conf: %{{y:.0%}}<extra></extra>",
                ))
        fig_ts.add_hline(y=0.60, line_dash="dash", line_color=_ORANGE,
                         annotation_text="Seuil min 60%", annotation_font_color=_ORANGE)
        _layout(fig_ts, height=280)
        fig_ts.update_yaxes(tickformat=".0%", range=[0.50, 1.05])
        st.plotly_chart(fig_ts, use_container_width=True)

    # -"?-"? Stratégies -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    _section("Stratégies utilisées")
    sc = df["strategy"].value_counts().reset_index()
    sc.columns = ["strategy", "count"]
    fig_s = go.Figure(go.Bar(
        x=sc["strategy"], y=sc["count"],
        marker_color=_BLUE,
        text=sc["count"], textposition="outside",
        hovertemplate="%{x}: %{y} décisions<extra></extra>",
    ))
    _layout(fig_s, "Décisions par stratégie", height=260)
    st.plotly_chart(fig_s, use_container_width=True)

    # -"?-"? Tableau trades complets -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if trades:
        _section("Historique des trades complets")
        rows = [{
            "#":           i + 1,
            "Date":        t["ts"][:16].replace("T", " ") if isinstance(t["ts"], str) else t["ts"].strftime("%Y-%m-%d %H:%M"),
            "Sens":        t.get("side", "LONG"),
            "P&L ($)":     f"{'+' if t['pnl_usd'] >= 0 else ''}${t['pnl_usd']:,.2f}",
            "P&L (%)":     f"{t['pnl_pct']:+.2f}%",
            "Résultat":    "Gain" if t["pnl_usd"] > 0 else "Perte",
        } for i, t in enumerate(trades)]

        def _col_color(val):
            s = str(val)
            if "Gain" in s:    return f"color:{_GREEN}"
            if "Perte" in s:   return f"color:{_RED}"
            if s.startswith("+"): return f"color:{_GREEN}"
            if s.startswith("-"): return f"color:{_RED}"
            return ""

        df_t = pd.DataFrame(rows)
        st.dataframe(df_t.style.map(_col_color, subset=["P&L (%)", "Résultat"]),
                     use_container_width=True, hide_index=True)
        st.download_button("-? Exporter (CSV)", data=df_t.to_csv(index=False),
                           file_name=f"trades_{ticker}.csv", mime="text/csv")
