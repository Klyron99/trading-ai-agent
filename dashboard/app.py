"""
Dashboard Agent de Trading Adaptatif
Lancement : python -m streamlit run dashboard/app.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

st.set_page_config(
    page_title="NEXORA — Trading Next Gen",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.data_loader import inject_css
inject_css()

import importlib
import dashboard.views.accueil as accueil
import dashboard.views.controles as controles
import dashboard.views.marches as marches
import dashboard.views.decisions as decisions
import dashboard.views.strategies as strategies
import dashboard.views.performance as performance
import dashboard.views.logs as logs
import dashboard.views.parametres as parametres
import dashboard.views.guide as guide
import dashboard.views.simulation as simulation
import dashboard.views.macro_events as macro_events
import dashboard.views.journal as journal
for _m in (accueil, controles, marches, decisions, strategies, performance, logs, parametres, guide, simulation, macro_events, journal):
    try:
        importlib.reload(_m)
    except Exception:
        pass
from dashboard.agent_state import get_agent_status, get_live_price, get_price_info

# Chargement sécurisé des settings — fallback si chemin non encore dans sys.path
try:
    from config.settings import AGENT_ALLOWED_TICKERS, LIVE_TICKER
except ImportError:
    import importlib.util, os
    _spec = importlib.util.spec_from_file_location(
        "config.settings", _ROOT / "config" / "settings.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    AGENT_ALLOWED_TICKERS = getattr(_mod, "AGENT_ALLOWED_TICKERS", ["AAPL", "MSFT", "SPY"])
    LIVE_TICKER = getattr(_mod, "LIVE_TICKER", "QQQ")

_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_PURPLE = "#8b5cf6"

_PAGES_AGENT = {
    "🏠  Accueil":      "accueil",
    "🎮  Contrôles":    "controles",
    "🌍  Marchés":      "marches",
    "📈  Performance":  "performance",
    "📋  Décisions":    "decisions",
    "🏆  Stratégies":   "strategies",
    "📄  Logs":         "logs",
    "⚙️  Paramètres":   "parametres",
    "💰  Simulation":   "simulation",
    "📖  Guide":        "guide",
}
_PAGES_PERSO = {
    "📓  Journal":      "journal",
}
_PAGES = {**_PAGES_AGENT, **_PAGES_PERSO}

with st.sidebar:
    logo_b64 = st.session_state.get("_logo_b64", "")
    logo_img = f'<img src="data:image/svg+xml;base64,{logo_b64}" style="width:44px;height:44px;margin-right:10px;vertical-align:middle;">' if logo_b64 else ""
    st.markdown(
        f'<div class="sidebar-logo">'
        f'<div style="display:flex;align-items:center;">'
        f'{logo_img}'
        f'<div>'
        f'<div class="brand">NEXORA</div>'
        f'<div class="sub">Trading Next Gen</div>'
        f'</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    @st.fragment(run_every=1)
    def _agent_status_widget():
        from dashboard.agent_state import get_all_agents_status, start_agent, stop_agent
        import time as _t
        import sqlite3 as _sq, json as _js
        from agent.memory import _DB_PATH as _DBPATH
        all_agents = get_all_agents_status()
        st.session_state["_all_agents_status"] = all_agents
        # Compat backward : expose le premier agent actif comme "_agent_status"
        if all_agents:
            t0, i0 = next(iter(all_agents.items()))
            st.session_state["_agent_status"] = {"running": True, "pid": i0.get("pid"), "ticker": t0, "started_at": i0.get("started_at")}
        else:
            st.session_state["_agent_status"] = {"running": False, "pid": None, "ticker": None}

        def _get_capital(_tk):
            try:
                _con = _sq.connect(str(_DBPATH))
                _con.row_factory = _sq.Row
                _snap = _con.execute(
                    "SELECT total_value FROM portfolio_snapshots WHERE ticker=? ORDER BY ts DESC LIMIT 1", (_tk,)
                ).fetchone()
                if _snap:
                    _con.close()
                    return float(_snap["total_value"])
                _br = _con.execute("SELECT cash FROM broker_state WHERE ticker=?", (_tk,)).fetchone()
                _con.close()
                return float(_br["cash"]) if _br else None
            except Exception:
                return None

        if not all_agents:
            st.error("● AUCUN AGENT ACTIF")
            if st.button("▶ Démarrer", use_container_width=True, type="primary", key="sb_start_all"):
                _tk = st.session_state.get("_ticker_sel", ticker)
                ok, msg = start_agent(_tk, 120)
                st.toast(msg)
                st.rerun()
        else:
            for _tk, _info in all_agents.items():
                _pid = _info.get("pid", -1)
                _starting = _pid == -1
                if _starting:
                    st.warning(f"⏳ {_tk} — démarrage…")
                else:
                    _sat = _info.get("started_at")
                    _uptime = ""
                    if _sat:
                        _secs = int(_t.time() - _sat)
                        _h, _rem = divmod(_secs, 3600)
                        _m, _s = divmod(_rem, 60)
                        _uptime = f" · {_h}h{_m:02d}m" if _h else f" · {_m}m{_s:02d}s"
                    _cap = _get_capital(_tk)
                    _pnl = _cap - 10000 if _cap is not None else None
                    _cap_str = f"${_cap:,.0f}" if _cap is not None else "—"
                    _pnl_color = _GREEN if (_pnl or 0) >= 0 else _RED
                    _pnl_str = (f'<span style="color:{_pnl_color};font-size:10px;font-weight:700;">{"+" if (_pnl or 0)>=0 else ""}{_pnl:+.0f}</span>' if _pnl is not None else "")
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.success(f"● {_tk}{_uptime}")
                        st.markdown(
                            f'<div style="margin-top:-8px;padding:0 4px 4px 4px;font-size:11px;color:{_TEXT};">'
                            f'<span style="font-weight:700;">{_cap_str}</span> {_pnl_str}</div>',
                            unsafe_allow_html=True,
                        )
                    with col_b:
                        if st.button("⏹", key=f"sb_stop_{_tk}", help=f"Arrêter {_tk}"):
                            ok, msg = stop_agent(_tk)
                            st.toast(msg)
                            st.rerun()
            pass  # arrêt individuel via ⏹ par ticker

    _agent_status_widget()

    # ── Switch automatique BTC/SPY ───────────────────────────────────────────
    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:12px 0;">', unsafe_allow_html=True)

    @st.fragment(run_every=10)
    def _scheduler_widget():
        import json as _json, subprocess as _sp, os as _os, sys as _sys
        from pathlib import Path as _Path
        _sched_file = _Path(__file__).resolve().parents[1] / "agent" / "memory_store" / "scheduler_pid.json"

        def _sched_alive():
            try:
                _data = _json.loads(_sched_file.read_text())
                _pid  = _data.get("pid")
                if not _pid:
                    return None
                import psutil as _ps
                p = _ps.Process(_pid)
                return _pid if p.is_running() and p.status() != "zombie" else None
            except Exception:
                return None

        _pid = _sched_alive()

        if _pid:
            st.markdown(
                f'<div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);'
                f'border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
                f'<span style="color:#10b981;font-size:9px;">●</span>'
                f'<span style="color:#10b981;font-size:11px;font-weight:700;letter-spacing:0.5px;">SWITCH AUTO</span>'
                f'<span style="color:#64748b;font-size:10px;margin-left:auto;">BTC / SPY</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("Désactiver", use_container_width=True, key="sb_stop_sched", type="secondary"):
                try:
                    import psutil as _ps
                    _ps.Process(_pid).kill()
                except Exception:
                    pass
                _sched_file.write_text(_json.dumps({"pid": None}))
                st.toast("Switch auto désactivé")
                st.rerun()
        else:
            st.markdown(
                f'<div style="background:rgba(100,116,139,0.08);border:1px solid rgba(100,116,139,0.2);'
                f'border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
                f'<span style="color:#64748b;font-size:9px;">●</span>'
                f'<span style="color:#64748b;font-size:11px;font-weight:700;letter-spacing:0.5px;">SWITCH AUTO</span>'
                f'<span style="color:#64748b;font-size:10px;margin-left:auto;">inactif</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("▶ Switch auto  BTC → SPY", use_container_width=True, key="sb_start_sched", type="primary"):
                _script = _Path(__file__).resolve().parents[1] / "agent_scheduler.py"
                _log    = _Path(__file__).resolve().parents[1] / "logs" / "scheduler.log"
                _log.parent.mkdir(parents=True, exist_ok=True)
                with open(_log, "a") as _fout:
                    _proc = _sp.Popen(
                        [_sys.executable, str(_script)],
                        cwd=str(_Path(__file__).resolve().parents[1]),
                        stdout=_fout, stderr=_fout,
                        stdin=_sp.DEVNULL,
                        creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                        env={**_os.environ, "PYTHONUNBUFFERED": "1"},
                    )
                _sched_file.parent.mkdir(parents=True, exist_ok=True)
                _sched_file.write_text(_json.dumps({"pid": _proc.pid}))
                st.toast("Switch auto activé — BTC 24/7, SPY 15h30→22h")
                st.rerun()

    _scheduler_widget()

    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:12px 0;">', unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:10px;font-weight:600;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:{_MUTED};margin-bottom:6px;">🤖 Agent IA</div>',
        unsafe_allow_html=True,
    )
    selected_label = st.radio("nav_agent", list(_PAGES_AGENT.keys()), label_visibility="collapsed", key="nav_agent_radio")

    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:10px 0 8px;">', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:10px;font-weight:600;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:#f59e0b;margin-bottom:6px;">📓 Trading Personnel</div>',
        unsafe_allow_html=True,
    )
    selected_perso = st.radio("nav_perso", list(_PAGES_PERSO.keys()), label_visibility="collapsed", key="nav_perso_radio")

    # Page active : bouton cliqué en dernier
    if st.session_state.get("_last_nav") not in ("agent", "perso"):
        st.session_state["_last_nav"] = "agent"
    prev_a = st.session_state.get("_cache_agent")
    prev_p = st.session_state.get("_cache_perso")
    if selected_label != prev_a:
        st.session_state["_last_nav"] = "agent"
        st.session_state["_cache_agent"] = selected_label
    if selected_perso != prev_p:
        st.session_state["_last_nav"] = "perso"
        st.session_state["_cache_perso"] = selected_perso

    if st.session_state["_last_nav"] == "perso":
        current_page = _PAGES_PERSO[selected_perso]
    else:
        current_page = _PAGES_AGENT[selected_label]

    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:12px 0;">', unsafe_allow_html=True)

    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _paris_now = _dt.now(_tz.utc) + _td(hours=2)
    _market_open = _paris_now.hour > 15 or (_paris_now.hour == 15 and _paris_now.minute >= 30)
    _market_close = _paris_now.hour >= 22
    _default_ticker = "SPY" if (_market_open and not _market_close) else "BTC-USD"
    tickers_opts = list(dict.fromkeys([_default_ticker, "BTC-USD", "SPY", "QQQ", "ETH-USD", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN"] + AGENT_ALLOWED_TICKERS))
    ticker = st.selectbox("Ticker", tickers_opts, index=0)

    @st.fragment(run_every=2)
    def _live_price_widget(t):
        info = get_price_info(t)
        live  = info["live"]
        close = info["close"]
        # variation live vs clôture
        if live and close:
            chg = live - close
            pct = chg / close * 100
            chg_color = _GREEN if chg >= 0 else _RED
            chg_str = f'<span style="color:{chg_color};font-size:10px;">{chg:+.2f} ({pct:+.2f}%)</span>'
        else:
            chg_str = ""
        price_html  = f'${live:,.2f} {chg_str}' if live else '<span style="color:#787b86;">—</span>'
        close_html  = f'${close:,.2f}' if close else '—'
        st.markdown(
            f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;'
            f'padding:12px 14px;font-size:12px;margin-top:6px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,0.35);">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<span style="color:{_MUTED};font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Cours en cours</span>'
            f'<span style="background:rgba(244,63,94,0.12);color:#f43f5e;font-size:9px;font-weight:700;'
            f'padding:2px 7px;border-radius:20px;border:1px solid rgba(244,63,94,0.25);">&#9679; LIVE</span></div>'
            f'<div style="color:{_TEXT};font-weight:800;font-size:17px;letter-spacing:-0.3px;'
            f'font-variant-numeric:tabular-nums;">{price_html}</div>'
            f'<div style="border-top:1px solid {_GRID};margin-top:10px;padding-top:8px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="color:{_MUTED};font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;">Clôture J-1</span>'
            f'<span style="color:{_TEXT};font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;">{close_html}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    _live_price_widget(ticker)

    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:16px 0;">', unsafe_allow_html=True)

    if st.button("⟳ Rafraîchir", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        f'<div class="sidebar-footer">'
        f'<span style="background:linear-gradient(135deg,#7B2FFF,#00B4FF);'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
        f'font-weight:800;letter-spacing:1px;">NEXORA</span> · Paper Trading<br>'
        f'<span style="color:rgba(120,123,134,0.4);">Smarter Decisions. Stronger Performance.</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

with st.container():
    if current_page == "accueil":
        accueil.render(ticker)
    elif current_page == "controles":
        controles.render(ticker)
    elif current_page == "marches":
        marches.render(ticker)
    elif current_page == "performance":
        performance.render(ticker)
    elif current_page == "decisions":
        decisions.render(ticker)
    elif current_page == "strategies":
        strategies.render(ticker)
    elif current_page == "logs":
        logs.render(ticker)
    elif current_page == "parametres":
        parametres.render(ticker)
    elif current_page == "simulation":
        simulation.render(ticker)
    elif current_page == "guide":
        guide.render(ticker)
    elif current_page == "macro_events":
        macro_events.render(ticker)
    elif current_page == "journal":
        journal.render(ticker)

