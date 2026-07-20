"""Statut en temps réel de l'agent."""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from dashboard.agent_state import get_agent_status, get_price_info
from agent import memory as mem
from config.settings import INITIAL_CAPITAL

_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"

_TZ2 = pd.Timedelta(hours=2)

_PAGE_HEADER = f"""
<style>
@media (max-width: 768px) {{
    .mobile-topbar {{ display: flex !important; }}
}}
.mobile-topbar {{
    display: none;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0 16px;
    border-bottom: 1px solid #1e2433;
    margin-bottom: 16px;
}}
.mobile-topbar .brand {{ font-size: 16px; font-weight: 800; color: #d1d4dc; }}
.mobile-topbar .brand span {{ color: #2962ff; }}
</style>
<div class="mobile-topbar">
    <div class="brand">&#9671; Alpha<span>Bot</span></div>
</div>
"""


def _card(label, value, color=None, sub=None):
    color = color or _TEXT
    sub_html = f'<div style="color:{_MUTED};font-size:11px;margin-top:5px;font-weight:400;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div style="background:{_CARD};border:1px solid {_GRID};border-radius:12px;
                padding:18px 22px;margin-bottom:8px;position:relative;overflow:hidden;
                box-shadow:0 2px 8px rgba(0,0,0,0.4);">
        <div style="position:absolute;top:0;left:0;width:3px;height:100%;
                    background:{color};border-radius:12px 0 0 12px;opacity:0.7;"></div>
        <div style="position:absolute;top:0;left:0;right:0;height:1px;
                    background:linear-gradient(90deg,{color} 0%,transparent 50%);opacity:0.3;"></div>
        <div style="color:{_MUTED};font-size:10px;font-weight:700;
                    text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;">{label}</div>
        <div style="color:{color};font-size:24px;font-weight:700;
                    line-height:1.1;font-variant-numeric:tabular-nums;">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def render(ticker: str, **kwargs):

    st.markdown(_PAGE_HEADER, unsafe_allow_html=True)

    @st.fragment(run_every=5)
    def _accueil_live():
        status = st.session_state.get("_agent_status") or get_agent_status()
        running = status["running"]
        starting = running and status.get("pid") == -1

        if starting:
            dot_color = _ORANGE
            dot_label = "AGENT EN DEMARRAGE..."
            rgb = "255,152,0"
        elif running:
            dot_color = _GREEN
            dot_label = "AGENT ACTIF"
            rgb = "38,166,154"
        else:
            dot_color = _RED
            dot_label = "AGENT ARRETE"
            rgb = "239,83,80"

        ticker_running = status.get("ticker", ticker) if running else ticker
        ticker_info = (f"&nbsp;&middot;&nbsp;<span style='color:{_MUTED};font-size:12px;'>"
                       f"Ticker : <b style='color:{_TEXT};'>{ticker_running}</b></span>") if running else ""
        st.markdown(
            f'<p style="background:rgba({rgb},0.08);border:1px solid {dot_color};'
            f'border-radius:8px;padding:12px 20px;margin-bottom:24px;font-size:14px;">'
            f'<b style="color:{dot_color};">&#9679; {dot_label}</b>{ticker_info}</p>',
            unsafe_allow_html=True,
        )

        # Valeurs par défaut — évite UnboundLocalError si pas encore de données broker
        pos_qty   = 0.0
        pos_avg   = 0.0
        pos_value = 0.0
        is_short  = False
        broker_cash = INITIAL_CAPITAL
        total_val   = INITIAL_CAPITAL

        try:
            mem.init_db()
            decisions = mem.get_recent_decisions(ticker, limit=10)
            best_strat = mem.get_best_strategy(ticker) or "—"
            last_model = mem.get_last_model(ticker)
        except Exception:
            decisions, best_strat, last_model = [], "—", None

        if decisions:
            last = dict(decisions[0])
            if last.get("ts"):
                try:
                    ts = pd.to_datetime(last["ts"], format="mixed", utc=True).tz_localize(None) + _TZ2
                    last["ts"] = ts.strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass
        else:
            last = {}

        info = get_price_info(ticker)
        live = info["live"]
        close = info["close"]

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            if live and close:
                chg = live - close
                pct = chg / close * 100
                arr = "▲" if chg >= 0 else "▼"
                sub = f"{arr} {chg:+.2f} ({pct:+.2f}%) · live"
                color = _GREEN if chg >= 0 else _RED
            else:
                sub = f"{ticker} · live"
                color = _BLUE
            _card("Cours en cours", f"${live:,.2f}" if live else "—", color=color, sub=sub)
        with c2:
            _card("Derniere cloture", f"${close:,.2f}" if close else "—", color=_MUTED, sub=f"{ticker} · J-1")
        with c3:
            action = last.get("action", "—")
            color = {"BUY": _GREEN, "SELL": _RED}.get(action, _MUTED)
            _card("Derniere decision", action, color=color,
                  sub=last.get("ts", "")[:16].replace("T", " ") if last else "Aucune")
        with c4:
            conf = last.get("confidence")
            conf_str = f"{conf:.0%}" if conf is not None else "—"
            conf_color = _GREEN if conf and conf >= 0.65 else _ORANGE if conf and conf >= 0.55 else _RED
            _card("Confiance", conf_str, color=conf_color, sub="Min requis : 60%")
        with c5:
            model_label = last_model['model_type'] if last_model else "—"
            _card("Strategie active", best_strat, color=_BLUE, sub=f"Modele : {model_label}")

        INITIAL = INITIAL_CAPITAL
        st.markdown(f'<div style="color:{_MUTED};font-size:10px;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:1px;margin:24px 0 10px;">Portfolio</div>',
                    unsafe_allow_html=True)

        try:
            import json, sqlite3
            from pathlib import Path
            _db = Path(__file__).resolve().parents[2] / "agent" / "memory_store" / "agent_memory.db"
            _con = sqlite3.connect(str(_db), timeout=5)
            _con.execute("PRAGMA journal_mode=WAL")
            _con.execute("PRAGMA wal_checkpoint(FULL)")
            _row = _con.execute(
                "SELECT cash, positions, updated_at FROM broker_state WHERE ticker=?", (ticker,)
            ).fetchone()
            _con.close()
            if _row:
                broker_cash = float(_row[0])
                broker_positions = json.loads(_row[1])
                broker_updated = _row[2]
                pos_qty = 0.0
                pos_avg = 0.0
                is_short = False
                longs  = broker_positions.get("long",  broker_positions)
                shorts = broker_positions.get("short", {})
                # Dénormalize le double-nesting résiduel {"long": {"long": {"SPY": ...}}}
                while "long" in longs and isinstance(longs.get("long"), dict) and ticker not in longs:
                    longs = longs["long"]
                if ticker in longs:
                    pos_qty = float(longs[ticker].get("qty", 0))
                    pos_avg = float(longs[ticker].get("avg_price", 0))
                    is_short = False
                elif ticker in shorts:
                    pos_qty = float(shorts[ticker].get("qty", 0))
                    pos_avg = float(shorts[ticker].get("avg_price", 0))
                    is_short = True
                cur_price = live or pos_avg
                if is_short:
                    pos_value = -(pos_qty * cur_price)
                else:
                    pos_value = pos_qty * cur_price
                total_val = broker_cash + pos_value
                broker_ok = True
            else:
                broker_ok = False
        except Exception:
            broker_ok = False

        if not broker_ok:
            try:
                portfolio_history = mem.get_portfolio_history(ticker, limit=10000)
            except Exception:
                portfolio_history = []
            if portfolio_history:
                last_snap = portfolio_history[-1]
                total_val = last_snap["total_value"]
                broker_cash = last_snap["cash"]
                pos_value = last_snap["positions_value"]
                pos_qty = 0.0
                pos_avg = 0.0
                broker_updated = last_snap.get("ts", "")
            else:
                total_val = INITIAL
                broker_cash = INITIAL
                pos_value = 0.0
                pos_qty = 0.0
                pos_avg = 0.0
                broker_updated = ""

        try:
            import sqlite3 as _sq3
            from pathlib import Path as _P
            _db2 = _P(__file__).resolve().parents[2] / "agent" / "memory_store" / "agent_memory.db"
            _con2 = _sq3.connect(str(_db2), timeout=5)
            _con2.execute("PRAGMA journal_mode=WAL")
            _con2.execute("PRAGMA wal_checkpoint(FULL)")
            _rows2 = _con2.execute(
                "SELECT ts, cash, positions_value, total_value, action "
                "FROM portfolio_snapshots WHERE ticker=? ORDER BY ts ASC", (ticker,)
            ).fetchall()
            _con2.close()
            portfolio_history = [{"ts": r[0], "cash": r[1], "positions_value": r[2],
                                   "total_value": r[3], "action": r[4]} for r in _rows2]
        except Exception:
            portfolio_history = []

        # P&L réalisé = cash actuel + coût base position ouverte - capital initial
        # Formule exacte indépendante du schéma trade_outcomes
        _closed_count = 0
        try:
            import sqlite3 as _sq3r
            from pathlib import Path as _Pr
            _dbr = _Pr(__file__).resolve().parents[2] / "agent" / "memory_store" / "agent_memory.db"
            _conr = _sq3r.connect(str(_dbr), timeout=5)
            _closed_count = _conr.execute(
                "SELECT COUNT(*) FROM trade_outcomes WHERE ticker=? AND exit_price IS NOT NULL",
                (ticker,)
            ).fetchone()[0]
            _conr.close()
        except Exception:
            pass
        cost_basis = pos_qty * pos_avg if pos_qty > 0 else 0.0
        realized_pnl = broker_cash + cost_basis - INITIAL

        pnl_color = _GREEN if realized_pnl >= 0 else _RED
        pnl_sign  = "+" if realized_pnl >= 0 else ""
        pnl_pct   = realized_pnl / INITIAL * 100

        # P&L non réalisé (position ouverte)
        unrealized_pnl = pos_value - (pos_qty * pos_avg) if pos_qty > 0 and not is_short else pos_value

        total_gain = total_val - INITIAL
        total_gain_sign = "+" if total_gain >= 0 else ""
        total_gain_color = _GREEN if total_gain >= 0 else _RED
        total_gain_pct = total_gain / INITIAL * 100

        p1, p2, p3, p4, p5 = st.columns(5)
        with p1: _card("Capital initial", f"${INITIAL:,.0f}", color=_MUTED)
        with p2:
            _card("Valeur actuelle",
                  f"{total_gain_sign}${total_gain:,.2f}",
                  color=total_gain_color,
                  sub=f"{total_gain_sign}{total_gain_pct:.2f}% depuis le début")
        with p3: _card("P&L réalisé", f"{pnl_sign}${realized_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)", color=pnl_color, sub=f"{_closed_count} trade(s) clôturé(s)" if _closed_count else "Aucun trade clôturé")
        # Pour un SHORT, le cash inclut le produit de vente — on affiche le cash net réel
        display_cash = broker_cash + pos_value if is_short else broker_cash
        _cash_sub = "net · dette short déduite" if is_short else None
        with p4: _card("Cash disponible", f"${display_cash:,.2f}", color=_BLUE, sub=_cash_sub)
        with p5:
            if pos_qty > 0 and is_short:
                _card(f"SHORT {ticker}", f"{pos_qty:.6f}",
                      color=_RED, sub=f"P&L non realise : {'+' if pos_value>=0 else ''}${pos_value:,.2f} · entree ${pos_avg:,.2f}")
            elif pos_qty > 0:
                _unr = pos_value - (pos_qty * pos_avg)
                _unr_sign = "+" if _unr >= 0 else ""
                _unr_pct = _unr / (pos_qty * pos_avg) * 100 if pos_avg else 0
                _card(f"P&L non réalisé (LONG)", f"{_unr_sign}${_unr:,.2f}",
                      color=_GREEN if _unr >= 0 else _RED,
                      sub=f"{_unr_sign}{_unr_pct:.2f}% · {pos_qty:.6f} {ticker} @ ${pos_avg:,.2f}")
            else:
                _card("Position ouverte", "Aucune", color=_MUTED, sub="Pas de position active")

        if portfolio_history:
            import plotly.graph_objects as go
            df_port = pd.DataFrame(portfolio_history)
            df_port["ts"] = pd.to_datetime(df_port["ts"], format="mixed", utc=True).dt.tz_localize(None) + _TZ2
            df_port["gain"] = df_port["total_value"] - INITIAL

            fig = go.Figure()

            # Zone colorée selon positif/négatif
            df_pos = df_port.copy(); df_pos["gain"] = df_pos["gain"].clip(lower=0)
            df_neg = df_port.copy(); df_neg["gain"] = df_neg["gain"].clip(upper=0)

            fig.add_trace(go.Scatter(
                x=df_port["ts"], y=df_port["gain"],
                name="Capital", line=dict(color=_GREEN, width=2),
                fill="tozeroy", fillcolor="rgba(16,185,129,0.12)",
            ))

            # Ligne zéro = capital initial
            fig.add_hline(y=0, line_dash="dash", line_color=_MUTED, line_width=1,
                          annotation_text=f"Capital initial (${INITIAL:,.0f})",
                          annotation_font_color=_MUTED, annotation_position="right")

            buys  = df_port[df_port.get("action", pd.Series()) == "BUY"]  if "action" in df_port else pd.DataFrame()
            sells = df_port[df_port.get("action", pd.Series()) == "SELL"] if "action" in df_port else pd.DataFrame()
            reinf = df_port[df_port.get("action", pd.Series()) == "REINFORCE_LONG"] if "action" in df_port else pd.DataFrame()

            if not buys.empty:
                fig.add_trace(go.Scatter(x=buys["ts"], y=buys["gain"],
                    mode="markers", name="Entrée",
                    marker=dict(color=_GREEN, size=10, symbol="triangle-up"),
                    text=[f"+${v:,.0f}" for v in buys["gain"]], textposition="top center"))
            if not sells.empty:
                fig.add_trace(go.Scatter(x=sells["ts"], y=sells["gain"],
                    mode="markers+text", name="Sortie",
                    marker=dict(color=_RED, size=10, symbol="triangle-down"),
                    text=[f"+${v:,.0f}" if v >= 0 else f"-${abs(v):,.0f}" for v in sells["gain"]],
                    textposition="bottom center", textfont=dict(color=_RED)))
            if not reinf.empty:
                fig.add_trace(go.Scatter(x=reinf["ts"], y=reinf["gain"],
                    mode="markers", name="Renfort",
                    marker=dict(color="#f59e0b", size=8, symbol="diamond")))

            # Axe Y zoomé sur les vraies valeurs
            y_vals = df_port["gain"].dropna()
            y_min = min(y_vals.min(), 0)
            y_max = y_vals.max()
            y_pad = max((y_max - y_min) * 0.25, 5)

            fig.update_layout(
                paper_bgcolor="#080c14", plot_bgcolor="#080c14",
                font=dict(color=_TEXT), height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(gridcolor=_GRID, showgrid=True),
                yaxis=dict(
                    gridcolor=_GRID, showgrid=True,
                    tickprefix="+$", tickformat=",.0f",
                    range=[y_min - y_pad, y_max + y_pad],
                    zeroline=False,
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
        elif not broker_ok:
            st.info("Demarrez l'agent pour voir l'evolution du capital.")

    _accueil_live()
