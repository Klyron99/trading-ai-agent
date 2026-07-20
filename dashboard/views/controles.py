"""
Page Controles - Panneau de commande de l'agent.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dashboard.agent_state import get_agent_status, get_all_agents_status, start_agent, stop_agent, run_retrain
from agent import memory as mem

_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"

AGENT_ALLOWED_TICKERS = os.getenv("AGENT_ALLOWED_TICKERS", "AAPL,MSFT,SPY,QQQ").split(",")
AGENT_MIN_CONFIDENCE  = float(os.getenv("AGENT_MIN_CONFIDENCE", "0.60"))
AGENT_MAX_DRAWDOWN    = float(os.getenv("AGENT_MAX_DRAWDOWN", "0.15"))

_CRYPTO_SUFFIXES = ("-USD", "-EUR", "-BTC", "-ETH", "-USDT")
_STOCK_OPEN_H  = (9, 30)   # 09h30 ET
_STOCK_CLOSE_H = (16, 0)   # 16h00 ET


def _check_market_open(ticker: str) -> tuple[bool, str]:
    """Retourne (is_open, message_descriptif)."""
    import datetime, zoneinfo

    # Crypto : toujours ouvert 24/7
    if any(ticker.upper().endswith(s) for s in _CRYPTO_SUFFIXES):
        return True, f"{ticker} — cryptomonnaie, marché ouvert 24h/24 7j/7"

    # Actions : NYSE/NASDAQ lun-ven 09:30–16:00 ET
    try:
        et = zoneinfo.ZoneInfo("America/New_York")
    except Exception:
        et = datetime.timezone(datetime.timedelta(hours=-5))

    now_et = datetime.datetime.now(tz=et)
    weekday = now_et.weekday()  # 0=lundi, 6=dimanche

    if weekday >= 5:
        day_name = "samedi" if weekday == 5 else "dimanche"
        next_open = now_et + datetime.timedelta(days=(7 - weekday))
        next_open_str = next_open.strftime("%A %d/%m à 09h30 ET")
        return False, (
            f"{ticker} — marché actions fermé le {day_name}. "
            f"Prochaine ouverture : lundi {next_open.strftime('%d/%m')} à 09h30 ET (15h30 heure française)."
        )

    open_time  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)

    if now_et < open_time:
        opens_in = int((open_time - now_et).total_seconds() / 60)
        return False, (
            f"{ticker} — marché fermé. Ouverture dans {opens_in} min "
            f"(09h30 ET = {open_time.astimezone(zoneinfo.ZoneInfo('Europe/Paris')).strftime('%Hh%M')} heure française)."
        )
    if now_et >= close_time:
        return False, (
            f"{ticker} — marché fermé depuis 16h00 ET. "
            f"Prochaine ouverture demain à 09h30 ET (15h30 heure française)."
        )

    closes_in = int((close_time - now_et).total_seconds() / 60)
    return True, f"{ticker} — marché ouvert, fermeture dans {closes_in} min (16h00 ET)."


def _section(title):
    st.markdown(
        f'<div style="color:{_MUTED};font-size:10px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:1.5px;'
        f'margin:28px 0 12px;border-bottom:1px solid {_GRID};'
        f'padding-bottom:8px;">{title}</div>',
        unsafe_allow_html=True,
    )


def _info_box(text, color=None):
    color = color or _MUTED
    st.markdown(
        f'<div style="background:{_CARD};border-left:3px solid {color};'
        f'border-radius:0 6px 6px 0;padding:12px 16px;'
        f'color:{_TEXT};font-size:13px;margin-bottom:12px;">{text}</div>',
        unsafe_allow_html=True,
    )


def _fmt_duration(seconds: float) -> str:
    """Formate une durée en secondes → '2h 14min' ou '34min' ou '< 1min'."""
    s = int(seconds)
    if s < 60:
        return "< 1 min"
    h, m = divmod(s // 60, 60)
    if h:
        return f"{h}h {m:02d}min"
    return f"{m}min"


def _render_session_history(ticker: str) -> None:
    """Affiche l'historique des sessions de l'agent avec durée, trades et P&L."""
    import sqlite3
    import pandas as _pd

    _db = str(_Path(__file__).resolve().parents[2] / "agent" / "memory_store" / "agent_memory.db")

    try:
        con = sqlite3.connect(_db, timeout=5, isolation_level=None)
        con.execute("PRAGMA wal_checkpoint(FULL)")

        # Snapshots triés par temps
        snaps = con.execute(
            "SELECT ts, cash, positions_value, total_value, action FROM portfolio_snapshots "
            "WHERE ticker=? ORDER BY ts ASC",
            (ticker,),
        ).fetchall()

        # Décisions pour compter BUY/SELL par session
        decisions = con.execute(
            "SELECT ts, action FROM decisions WHERE ticker=? ORDER BY ts ASC",
            (ticker,),
        ).fetchall()

        # Versions modèles avec leurs timestamps
        model_versions = con.execute(
            "SELECT ts, model_type, accuracy FROM model_history WHERE ticker=? ORDER BY ts ASC",
            (ticker,),
        ).fetchall()

        con.close()
    except Exception:
        st.markdown(f'<div style="color:{_MUTED};font-size:13px;">Aucune donnée de session disponible.</div>', unsafe_allow_html=True)
        return

    if not snaps:
        st.markdown(f'<div style="color:{_MUTED};font-size:13px;">Aucune session enregistrée pour {ticker}.</div>', unsafe_allow_html=True)
        return

    # Convertit en timestamps
    def _to_ts(s):
        return _pd.to_datetime(s, format="mixed", utc=True)

    snap_rows = [(
        _to_ts(r[0]),
        float(r[1]), float(r[2]), float(r[3]), r[4]
    ) for r in snaps]

    dec_rows = [(_to_ts(r[0]), r[1]) for r in decisions]

    mv_rows = [(_to_ts(r[0]), r[1], r[2]) for r in model_versions]

    # Détecte les sessions : gap > 3 min entre deux ticks consécutifs
    GAP_SEC = 180
    sessions = []
    session_start = snap_rows[0][0]
    session_snaps = [snap_rows[0]]

    for i in range(1, len(snap_rows)):
        prev_ts, curr_ts = snap_rows[i - 1][0], snap_rows[i][0]
        gap = (curr_ts - prev_ts).total_seconds()
        if gap > GAP_SEC:
            sessions.append((session_start, snap_rows[i - 1][0], session_snaps))
            session_start = snap_rows[i][0]
            session_snaps = [snap_rows[i]]
        else:
            session_snaps.append(snap_rows[i])

    sessions.append((session_start, snap_rows[-1][0], session_snaps))

    # Associe chaque session à une version modèle (version active avant le démarrage de la session)
    def _version_at(ts):
        v = 0
        for mv_ts, mv_type, mv_acc in mv_rows:
            if mv_ts <= ts:
                v += 1
        return v or 1

    # Convertit TZ pour affichage
    _tz_offset = _pd.Timedelta(hours=2)

    def _fmt_ts(ts):
        return (ts.tz_localize(None) + _tz_offset).strftime("%d/%m %H:%M")

    # Affiche uniquement la session en cours (la plus récente)
    current_sessions = list(reversed(sessions))[:1]

    # Source de vérité unique : broker_state (même calcul que la page Accueil)
    try:
        bs_row = con2.execute(
            "SELECT cash, positions FROM broker_state WHERE ticker=?", (ticker,)
        ).fetchone() if False else None  # on relit proprement
        import json as _json
        _db2 = _db
        _con2 = sqlite3.connect(_db2, timeout=5, isolation_level=None)
        _con2.execute("PRAGMA wal_checkpoint(FULL)")
        bs_row = _con2.execute(
            "SELECT cash, positions FROM broker_state WHERE ticker=?", (ticker,)
        ).fetchone()
        _con2.close()
        if bs_row:
            _bs_raw = _json.loads(bs_row[1])
            _bs_cash = float(bs_row[0])
            _bs_positions = _bs_raw.get("long", _bs_raw) if "long" in _bs_raw else _bs_raw
        else:
            _bs_cash, _bs_positions = 10000.0, {}
    except Exception:
        _bs_cash, _bs_positions = 10000.0, {}

    INITIAL_CAPITAL = 10000.0

    for i, (s_start, s_end, s_snaps) in enumerate(current_sessions):
        duration_sec = (s_end - s_start).total_seconds()
        n_ticks = len(s_snaps)

        # P&L = source unique broker_state (identique à la page Accueil)
        # valeur finale réelle = cash + valeur des positions ouvertes (prix dernier snapshot)
        last_price = s_snaps[-1][1] + s_snaps[-1][2]  # cash + positions_value du dernier snap
        # On prend directement le total_value du dernier snapshot (déjà calculé par l'agent)
        final_val = s_snaps[-1][3]
        pnl = final_val - INITIAL_CAPITAL  # même base que Accueil
        pnl_pct = (pnl / INITIAL_CAPITAL * 100)

        # Compte les trades directement depuis les snapshots de la session (source de vérité)
        n_buy   = sum(1 for _, _, _, _, act in s_snaps if act in ("BUY",  "SHORT"))
        n_reinf = sum(1 for _, _, _, _, act in s_snaps if act in ("REINFORCE_LONG", "REINFORCE_SHORT"))
        n_sell  = sum(1 for _, _, _, _, act in s_snaps if act in ("SELL", "COVER"))

        # Version modèle associée
        model_v = _version_at(s_start)

        pnl_color = _GREEN if pnl >= 0 else _RED
        pnl_sign = "+" if pnl >= 0 else ""
        st.markdown(
            f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;'
            f'padding:14px 18px;margin-bottom:10px;">'

            # En-tête : badge version modèle + timestamps
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
            f'<span style="background:#0d2847;color:{_BLUE};font-size:10px;font-weight:700;'
            f'padding:2px 8px;border-radius:12px;border:1px solid {_BLUE};">modèle v{model_v}</span>'
            f'<span style="color:{_MUTED};font-size:11px;">{_fmt_ts(s_start)} → {_fmt_ts(s_end)}</span>'
            f'</div>'

            # Métriques en ligne
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">'

            # Durée
            f'<div style="text-align:center;background:#0d1117;border-radius:6px;padding:8px 4px;">'
            f'<div style="color:{_MUTED};font-size:9px;text-transform:uppercase;letter-spacing:1px;">Durée</div>'
            f'<div style="color:{_TEXT};font-size:15px;font-weight:700;">{_fmt_duration(duration_sec)}</div>'
            f'</div>'

            # Ticks
            f'<div style="text-align:center;background:#0d1117;border-radius:6px;padding:8px 4px;">'
            f'<div style="color:{_MUTED};font-size:9px;text-transform:uppercase;letter-spacing:1px;">Ticks</div>'
            f'<div style="color:{_TEXT};font-size:15px;font-weight:700;">{n_ticks}</div>'
            f'</div>'

            # Trades
            f'<div style="text-align:center;background:#0d1117;border-radius:6px;padding:8px 4px;">'
            f'<div style="color:{_MUTED};font-size:9px;text-transform:uppercase;letter-spacing:1px;">Trades</div>'
            f'<div style="color:{_TEXT};font-size:15px;font-weight:700;">'
            f'<span style="color:{_GREEN};">{n_buy}▲</span>'
            + (f' <span style="color:#f59e0b;">+{n_reinf}</span>' if n_reinf else '')
            + f' <span style="color:{_RED};">{n_sell}▼</span>'
            + f'</div>'
            f'</div>'

            # P&L session
            f'<div style="text-align:center;background:#0d1117;border-radius:6px;padding:8px 4px;">'
            f'<div style="color:{_MUTED};font-size:9px;text-transform:uppercase;letter-spacing:1px;">P&L session</div>'
            f'<div style="color:{pnl_color};font-size:15px;font-weight:700;">'
            f'{pnl_sign}${pnl:,.0f} <span style="font-size:11px;">({pnl_sign}{pnl_pct:.1f}%)</span>'
            f'</div>'
            f'</div>'

            f'</div>'  # fin grid
            f'</div>',  # fin card
            unsafe_allow_html=True,
        )


def render(ticker: str, **kwargs):
    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">Controles</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
        f'Demarrer, arreter et configurer l agent de trading</div>',
        unsafe_allow_html=True,
    )

    all_agents = get_all_agents_status()

    _section("Agents actifs")

    if not all_agents:
        _info_box("● Aucun agent actif", color=_RED)
    else:
        import time as _t
        for _tk, _info in all_agents.items():
            _pid = _info.get("pid", -1)
            _sat = _info.get("started_at")
            _uptime = ""
            if _sat and _pid != -1:
                _secs = int(_t.time() - _sat)
                _h, _rem = divmod(_secs, 3600)
                _m, _ = divmod(_rem, 60)
                _uptime = f" · {_h}h {_m:02d}min" if _h else f" · {_m}min"
            col_info, col_stop = st.columns([4, 1])
            with col_info:
                _info_box(f"● {_tk} — PID {_pid}{_uptime}", color=_GREEN)
            with col_stop:
                st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
                if st.button(f"⏹ Stop", key=f"ctrl_stop_{_tk}", use_container_width=True, type="secondary"):
                    ok, msg = stop_agent(_tk)
                    st.info(msg)
                    st.rerun()
        if len(all_agents) > 1:
            if st.button("⏹ Arrêter tous les agents", use_container_width=True, type="secondary", key="ctrl_stop_all"):
                ok, msg = stop_agent()
                st.info(msg)
                st.rerun()

    _section("Demarrer un agent")

    col1, col2 = st.columns(2)
    with col1:
        tickers_opts = list(dict.fromkeys([ticker, "SPY", "QQQ", "BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "TSLA"] + AGENT_ALLOWED_TICKERS))
        sel_ticker = st.selectbox("Ticker", tickers_opts, key="ctrl_ticker")
    with col2:
        interval = st.selectbox(
            "Intervalle (secondes)",
            [30, 60, 120, 300, 600],
            index=2,
            format_func=lambda x: f"{x}s - {x//60}min" if x >= 60 else f"{x}s",
            key="ctrl_interval",
        )

    # Vérification horaires de marché
    market_open, market_msg = _check_market_open(sel_ticker)
    if market_open:
        _info_box(f"Marché ouvert · {market_msg}", color=_GREEN)
    else:
        st.markdown(
            f'<div style="background:#1a0a0a;border:1px solid {_RED};border-radius:8px;'
            f'padding:14px 18px;margin:8px 0 12px;">'
            f'<div style="color:{_RED};font-weight:700;font-size:14px;">⛔ Marché fermé — démarrage impossible</div>'
            f'<div style="color:{_TEXT};font-size:13px;margin-top:6px;">{market_msg}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    already_running = sel_ticker.upper() in all_agents
    if already_running:
        _info_box(f"⚠️ Un agent {sel_ticker} tourne déjà — le redémarrer remplacera l'instance en cours.", color=_ORANGE)

    _info_box(
        f"Paper trading uniquement · Confiance min : {AGENT_MIN_CONFIDENCE:.0%} · Drawdown max : {AGENT_MAX_DRAWDOWN:.0%}",
        color=_ORANGE,
    )

    if st.button("▶ Demarrer l agent", type="primary", use_container_width=True,
                 disabled=not market_open):
        ok, msg = start_agent(sel_ticker, interval)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    _section("Reentrainer les modeles ML")

    _info_box(
        "Telecharge les donnees recentes, reentrainee le RandomForest, "
        "compare avec l ancien modele et selectionne la meilleure strategie. 1-3 minutes par ticker.",
        color=_BLUE,
    )

    retrain_tickers = st.multiselect(
        "Tickers a reentrainer",
        options=list(dict.fromkeys(AGENT_ALLOWED_TICKERS + ["BTC-USD", "ETH-USD", "AAPL", "MSFT", "SPY", "QQQ", "TSLA"])),
        default=[],
        key="ctrl_retrain_tickers",
    )

    # Versions actuelles des modèles + historique
    if retrain_tickers:
        import sqlite3
        import pandas as _pd
        _db = str(_Path(__file__).resolve().parents[2] / "agent" / "memory_store" / "agent_memory.db")

        for t in retrain_tickers:
            try:
                con = sqlite3.connect(_db, timeout=5, isolation_level=None)
                con.execute("PRAGMA wal_checkpoint(FULL)")
                v = con.execute("SELECT COUNT(*) FROM model_history WHERE ticker=?", (t,)).fetchone()[0]
                rows = con.execute(
                    "SELECT id, ts, accuracy FROM model_history WHERE ticker=? ORDER BY ts ASC", (t,)
                ).fetchall()
                last_acc = rows[-1][2] if rows else 0.0
                con.close()
                last_ts = "jamais"
                history_rows = []
                for idx, (rid, rts, racc) in enumerate(rows, 1):
                    local_ts = _pd.to_datetime(rts, format="mixed", utc=True).tz_localize(None) + _pd.Timedelta(hours=2)
                    label = local_ts.strftime("%Y-%m-%d %H:%M")
                    if idx == len(rows):
                        last_ts = label
                        last_acc = racc or 0.0
                    history_rows.append((idx, label, racc or 0.0))
            except Exception:
                v, last_ts, history_rows, last_acc = 0, "—", [], 0.0

            acc_color = _GREEN if last_acc >= 0.57 else _ORANGE if last_acc >= 0.53 else _MUTED
            acc_str = f"{last_acc:.1%}" if last_acc > 0 else "—"
            st.markdown(
                f'<div style="background:#131722;border:1px solid #1e2433;border-radius:8px;'
                f'padding:10px 16px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="color:#2962ff;font-size:18px;font-weight:700;">{t} — v{v}</span>'
                f'<span style="color:{acc_color};font-weight:600;">Accuracy : {acc_str}</span>'
                f'<span style="color:#787b86;font-size:11px;">Dernier : {last_ts}</span>'
                f'</div>', unsafe_allow_html=True
            )

            if history_rows:
                st.markdown(
                    f'<div style="background:#0f1724;border:1px solid #1e2433;border-radius:8px;'
                    f'padding:8px 14px;margin-bottom:10px;">'
                    f'<div style="display:grid;grid-template-columns:40px 1fr 80px;gap:4px;">'
                    f'<span style="color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Ver.</span>'
                    f'<span style="color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Date</span>'
                    f'<span style="color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Accuracy</span>'
                    + "".join(
                        f'<span style="color:#3b82f6;font-weight:700;font-size:12px;">v{num}</span>'
                        f'<span style="color:#e2e8f0;font-size:12px;">{ts_label}</span>'
                        f'<span style="color:{"#10b981" if racc>=0.57 else "#f59e0b" if racc>=0.53 else "#64748b"};font-size:12px;font-weight:600;">{racc:.1%}</span>'
                        for num, ts_label, racc in reversed(history_rows)
                    )
                    + f'</div></div>',
                    unsafe_allow_html=True
                )

            if rows and st.button(f"Supprimer la dernière version (v{v})", key=f"del_v_{t}",
                                   type="secondary", use_container_width=False):
                try:
                    last_id = rows[-1][0]
                    con2 = sqlite3.connect(_db, timeout=5)
                    con2.execute("DELETE FROM model_history WHERE id=?", (last_id,))
                    con2.commit()
                    con2.close()
                    # Supprime aussi le fichier modèle si c'est la seule version
                    from config.settings import MODEL_STORE_DIR
                    model_file = MODEL_STORE_DIR / f"{t}_rf_model.joblib"
                    if len(rows) == 1 and model_file.exists():
                        model_file.unlink()
                        st.success(f"v{v} supprimée — modèle réinitialisé.")
                    else:
                        st.success(f"v{v} supprimée de l'historique.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    if st.button("Lancer le reentrainement", use_container_width=True, disabled=not retrain_tickers):
        progress_ph = st.empty()
        progress_ph.info("Preparation des donnees et selection des features...")
        with st.spinner(f"Reentrainement en cours pour {retrain_tickers}... (2-5 min)"):
            ok, output = run_retrain(retrain_tickers)
        progress_ph.empty()
        if ok:
            # Relis la nouvelle version depuis la DB pour affichage immédiat
            try:
                con_r = sqlite3.connect(_db, timeout=5)
                new_rows = con_r.execute(
                    "SELECT COUNT(*), MAX(accuracy), MAX(ts) FROM model_history WHERE ticker=?",
                    (retrain_tickers[0],)
                ).fetchone()
                con_r.close()
                new_v, new_acc, new_ts = new_rows
                import pandas as _pd2
                new_ts_loc = _pd2.to_datetime(new_ts, format="mixed", utc=True).tz_localize(None) + _pd2.Timedelta(hours=2)
                st.success(
                    f"Reentrainement termine ! "
                    f"Nouvelle version : **v{new_v}** | Accuracy : **{new_acc:.1%}** | {new_ts_loc.strftime('%Y-%m-%d %H:%M')}"
                )
            except Exception:
                st.success("Reentrainement termine avec succes !")
        else:
            st.warning("Reentrainement termine — verification recommandee")
            if output:
                st.code(output[-2000:], language=None)
        st.rerun()

    _section("Historique des sessions")
    _render_session_history(ticker)

    _section("Maintenance")

    m1, m2 = st.columns(2)
    with m1:
        if st.button("Vider le cache Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache vide !")
    with m2:
        if st.button("🗑 Effacer la mémoire SQLite", use_container_width=True, type="secondary"):
            st.session_state["_confirm_reset_db"] = True
        if st.session_state.get("_confirm_reset_db"):
            st.warning("⚠️ Cette action supprime **tout** l'historique (trades, décisions, snapshots). Irréversible.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Confirmer — tout effacer", type="primary", use_container_width=True):
                    try:
                        db = _ROOT / "agent" / "memory_store" / "agent_memory.db"
                        if db.exists():
                            db.unlink()
                        st.session_state["_confirm_reset_db"] = False
                        st.success("Mémoire effacée.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with col_no:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["_confirm_reset_db"] = False
                    st.rerun()

    _section("Guide de demarrage rapide")

    st.markdown(
        f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:16px 20px;">'
        f'<ol style="color:{_TEXT};font-size:13px;line-height:2.2;margin:0;padding-left:20px;">'
        f'<li>Clique <b style="color:{_BLUE};">Reentrainer</b> pour entrainer les modeles (premiere fois)</li>'
        f'<li>Choisis ton ticker et l intervalle de decision</li>'
        f'<li>Clique <b style="color:{_GREEN};">Demarrer l agent</b></li>'
        f'<li>Va sur la page <b>Accueil</b> pour voir les decisions en temps reel</li>'
        f'<li>L agent peut trader a partir de 60% de confiance (seuil actuel)</li>'
        f'</ol></div>',
        unsafe_allow_html=True,
    )
