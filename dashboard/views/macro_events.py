"""
Page dashboard — Événements Macro & Trading Gold (XAUUSD).
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT / "data" / "trading_memory.db"

_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_GOLD   = "#f59e0b"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"


def _importance_stars(n: int) -> str:
    return "★" * n + "☆" * (3 - n)


def _reaction_badge(reaction: str | None) -> str:
    if reaction == "buy":
        return f'<span style="background:rgba(16,185,129,0.15);color:{_GREEN};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">▲ GOLD UP</span>'
    if reaction == "sell":
        return f'<span style="background:rgba(244,63,94,0.15);color:{_RED};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">▼ GOLD DOWN</span>'
    return f'<span style="background:rgba(100,116,139,0.15);color:{_MUTED};padding:2px 8px;border-radius:12px;font-size:11px;">— EN ATTENTE</span>'


def _load_events() -> list[dict]:
    try:
        con = sqlite3.connect(str(_DB_PATH))
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT * FROM economic_events
            ORDER BY ts DESC LIMIT 50
        """).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _load_gold_trades() -> list[dict]:
    try:
        con = sqlite3.connect(str(_DB_PATH))
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT ts, action, confidence, price, reason
            FROM decisions
            WHERE ticker='XAUUSD' AND action NOT IN ('HOLD')
            ORDER BY ts DESC LIMIT 20
        """).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _agent_running() -> bool:
    try:
        import json
        proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
        data = json.loads(proc_file.read_text())
        info = data.get("agents", {}).get("XAUUSD-NEWS", {})
        if not info.get("running"):
            return False
        import psutil
        p = psutil.Process(info["pid"])
        return p.is_running() and p.status() != "zombie"
    except Exception:
        return False


def _read_log_tail(n: int = 40) -> list[str]:
    log_path = _ROOT / "logs" / "news_agent.log"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _log_level_color(line: str) -> str:
    if "SUCCESS" in line or "filled" in line.upper():
        return _GREEN
    if "ERROR" in line or "REFUS" in line:
        return _RED
    if "WARNING" in line:
        return _GOLD
    if "BUY" in line or "SELL" in line:
        return _BLUE
    return _MUTED


def _load_swing_trades() -> list[dict]:
    try:
        con = sqlite3.connect(str(_DB_PATH))
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT ts, action, confidence, price, reason
            FROM decisions WHERE ticker='XAUUSD' AND strategy='GoldSwing'
            ORDER BY ts DESC LIMIT 20
        """).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _get_swing_signal() -> dict:
    try:
        sys.path.insert(0, str(_ROOT))
        from strategies.gold_swing_strategy import GoldSwingStrategy
        sig = GoldSwingStrategy().analyze()
        return {
            "action": sig.action, "confidence": sig.confidence,
            "price": sig.price, "sl": sig.sl, "tp": sig.tp,
            "atr": sig.atr, "daily_trend": sig.daily_trend,
            "rsi_4h": sig.rsi_4h, "ema20_4h": sig.ema20_4h,
            "reason": sig.reason,
        }
    except Exception as e:
        return {"action": "ERREUR", "reason": str(e), "daily_trend": "?",
                "rsi_4h": 0, "ema20_4h": 0, "price": 0, "confidence": 0,
                "sl": 0, "tp": 0, "atr": 0}


def _swing_agent_running() -> bool:
    try:
        import json, psutil
        proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
        data = json.loads(proc_file.read_text())
        info = data.get("agents", {}).get("XAUUSD-SWING", {})
        if not info.get("running"):
            return False
        p = psutil.Process(info["pid"])
        return p.is_running() and p.status() != "zombie"
    except Exception:
        return False


def _launch_swing_agent(login: str, password: str, server: str) -> None:
    import json, os, time
    script = _ROOT / "run_swing_agent.py"
    log    = _ROOT / "logs" / "swing_agent.log"
    log.parent.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if login:    env["MT5_LOGIN"]    = login
    if password: env["MT5_PASSWORD"] = password
    if server:   env["MT5_SERVER"]   = server
    with open(log, "a") as fout:
        proc = subprocess.Popen(
            [sys.executable, str(script)], cwd=str(_ROOT),
            stdout=fout, stderr=fout, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=env,
        )
    proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
    try:
        data = json.loads(proc_file.read_text())
    except Exception:
        data = {"agents": {}}
    data["agents"]["XAUUSD-SWING"] = {"running": True, "pid": proc.pid, "started_at": time.time()}
    proc_file.write_text(json.dumps(data))


def _stop_swing_agent() -> None:
    import json, psutil
    proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
    try:
        data = json.loads(proc_file.read_text())
        pid = data.get("agents", {}).get("XAUUSD-SWING", {}).get("pid")
        if pid:
            psutil.Process(pid).kill()
        data["agents"]["XAUUSD-SWING"] = {"running": False, "pid": None}
        proc_file.write_text(json.dumps(data))
    except Exception:
        pass


def _reaction_html(reaction):
    if reaction == "buy":
        return f'<span style="background:rgba(16,185,129,0.15);color:{_GREEN};padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap;">▲ GOLD UP</span>'
    if reaction == "sell":
        return f'<span style="background:rgba(244,63,94,0.15);color:{_RED};padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap;">▼ GOLD DOWN</span>'
    return f'<span style="background:rgba(100,116,139,0.1);color:{_MUTED};padding:2px 8px;border-radius:10px;font-size:10px;white-space:nowrap;">En attente</span>'


def render(_ticker: str = "XAUUSD") -> None:
    st.markdown(f"""
        <div style="margin-bottom:20px;">
            <div style="font-size:22px;font-weight:800;color:{_TEXT};letter-spacing:-0.5px;">
                📰 Événements Macro — XAUUSD
            </div>
            <div style="color:{_MUTED};font-size:13px;margin-top:4px;">
                Trading automatique sur annonces économiques · MT5 DEMO
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ── Widget principal : Trades + Calendrier (refresh 30s) ──────────────────
    @st.fragment(run_every=30)
    def _main_widget():
        from datetime import datetime, timezone, timedelta

        _PARIS_OFFSET = timedelta(hours=2)  # UTC+2 (heure d'été Paris)
        now_utc = datetime.now(timezone.utc)
        now_paris = now_utc + _PARIS_OFFSET
        now_str = now_utc.strftime("%Y-%m-%dT%H:%M")  # comparaison interne en UTC

        # --- Trades XAUUSD ---
        trades = _load_swing_trades()
        all_trades = _load_gold_trades()
        seen = set()
        combined = []
        for t in sorted(trades + all_trades, key=lambda x: x["ts"], reverse=True):
            key = t["ts"] + t["action"]
            if key not in seen:
                seen.add(key)
                combined.append(t)
        combined = combined[:10]

        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};'
            f'letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Trades XAUUSD</div>',
            unsafe_allow_html=True
        )

        header = (
            f'<div style="display:grid;grid-template-columns:110px 60px 85px 55px 75px 85px 85px 1fr;'
            f'gap:4px;padding:6px 12px;background:{_GRID};border-radius:8px 8px 0 0;'
            f'font-size:10px;color:{_MUTED};font-weight:700;text-transform:uppercase;">'
            f'<span>Heure</span><span>Signal</span><span>Prix</span><span>Lots</span>'
            f'<span>Capital</span><span>SL</span><span>TP</span><span>Statut</span></div>'
        )

        rows_html = ""
        for t in combined:
            a = t["action"]
            c = _GREEN if a == "BUY" else _RED if a == "SELL" else _MUTED
            tag_bg = "rgba(16,185,129,0.15)" if a == "BUY" else "rgba(244,63,94,0.12)" if a == "SELL" else "rgba(100,116,139,0.1)"
            p = float(t["price"] or 0)
            reason = t.get("reason", "") or ""
            sl_str = tp_str = "—"
            if "SL=" in reason:
                try: sl_str = "$" + reason.split("SL=")[1].split(" ")[0].split("|")[0]
                except: pass
            if "TP=" in reason:
                try: tp_str = "$" + reason.split("TP=")[1].split(" ")[0].split("|")[0]
                except: pass
            lots = "0.01" if a in ("BUY", "SELL") else "—"
            capital = f"~${p * 0.01:.0f}" if a in ("BUY", "SELL") and p else "—"
            ts_short = t["ts"][5:16].replace("T", " ")
            statut = "Simulation — MT5 non connecté" if a in ("BUY", "SELL") else reason[:60]
            rows_html += (
                f'<div style="display:grid;grid-template-columns:110px 60px 85px 55px 75px 85px 85px 1fr;'
                f'gap:4px;padding:8px 12px;border-bottom:1px solid {_GRID};font-size:12px;align-items:center;">'
                f'<span style="color:{_MUTED};font-size:11px;">{ts_short}</span>'
                f'<span><span style="background:{tag_bg};color:{c};padding:2px 8px;border-radius:6px;'
                f'font-size:11px;font-weight:700;">{a}</span></span>'
                f'<span style="color:{_TEXT};font-weight:600;">${p:,.2f}</span>'
                f'<span style="color:{_TEXT};">{lots}</span>'
                f'<span style="color:{_TEXT};">{capital}</span>'
                f'<span style="color:{_RED};font-size:11px;">{sl_str}</span>'
                f'<span style="color:{_GREEN};font-size:11px;">{tp_str}</span>'
                f'<span style="color:{_MUTED};font-size:10px;">{statut}</span></div>'
            )

        if not combined:
            rows_html = f'<div style="padding:16px;color:{_MUTED};font-size:12px;">Aucun trade XAUUSD pour l\'instant.</div>'

        st.markdown(
            f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;'
            f'overflow:hidden;margin-bottom:20px;">{header}{rows_html}</div>',
            unsafe_allow_html=True
        )

        # --- Calendrier trié par heure croissante ---
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};letter-spacing:1px;'
            f'text-transform:uppercase;margin-bottom:8px;">'
            f'Calendrier économique — {now_paris.strftime("%d %b %Y")} '
            f'<span style="font-weight:400;text-transform:none;font-size:10px;">'
            f'(heure Paris UTC+2)</span></div>',
            unsafe_allow_html=True
        )

        events = sorted(_load_events(), key=lambda e: e.get("ts", ""))
        now_line_shown = False
        cal_rows = []

        for e in events:
            imp = e.get("importance", 1)
            ts = e.get("ts", "")
            is_past = ts < now_str
            # Convertir l'heure UTC → Paris pour affichage
            if len(ts) >= 16:
                from datetime import datetime as _dt
                try:
                    _ts_utc = _dt.strptime(ts[:16], "%Y-%m-%dT%H:%M")
                    _ts_paris = _ts_utc + _PARIS_OFFSET
                    time_str = _ts_paris.strftime("%H:%M")
                except Exception:
                    time_str = ts[11:16]
            actual = e.get("actual")
            forecast = e.get("forecast")
            previous = e.get("previous")
            reaction = e.get("gold_reaction")

            if imp == 3:
                border = "#E24B4A"
                bg_past = "rgba(244,63,94,0.04)"
                bg_fut  = "rgba(244,63,94,0.08)"
            elif imp == 2:
                border = "#EF9F27"
                bg_past = "rgba(245,158,11,0.04)"
                bg_fut  = "rgba(245,158,11,0.08)"
            else:
                border = _GRID
                bg_past = _CARD
                bg_fut  = _CARD

            bg = bg_past if is_past else bg_fut
            opacity = "opacity:0.55;" if is_past else ""
            stars = "★" * imp + "☆" * (3 - imp)
            stars_color = "#E24B4A" if imp == 3 else "#EF9F27" if imp == 2 else _MUTED

            actual_str   = str(actual)   if actual   is not None else "—"
            forecast_str = str(forecast) if forecast is not None else "—"
            prev_str     = str(previous) if previous is not None else "—"

            if actual is not None and forecast is not None and reaction:
                actual_color = _GREEN if reaction == "buy" else _RED
            else:
                actual_color = _MUTED

            # Impact gold pour les événements passés avec résultats
            if is_past and actual is not None and forecast is not None and reaction:
                impact_label = "▲ GOLD UP" if reaction == "buy" else "▼ GOLD DOWN"
                impact_color = _GREEN if reaction == "buy" else _RED
                impact_bg    = "rgba(16,185,129,0.15)" if reaction == "buy" else "rgba(244,63,94,0.15)"
                reaction_cell = (
                    f'<span style="background:{impact_bg};color:{impact_color};'
                    f'padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">'
                    f'{impact_label}</span>'
                )
            elif not is_past:
                reaction_cell = _reaction_html(reaction)
            else:
                reaction_cell = f'<span style="color:{_MUTED};font-size:10px;">—</span>'

            # Séparateur "maintenant"
            if not now_line_shown and not is_past:
                now_line_shown = True
                cal_rows.append(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0;">'
                    f'<span style="font-size:10px;color:{_BLUE};font-weight:700;white-space:nowrap;">▶ MAINTENANT</span>'
                    f'<div style="flex:1;border-top:1.5px dashed rgba(59,130,246,0.4);"></div></div>'
                )

            cal_rows.append(
                f'<div style="{opacity}background:{bg};border-left:3px solid {border};'
                f'border-radius:0 8px 8px 0;padding:8px 12px;'
                f'display:grid;grid-template-columns:52px 20px 1fr 65px 65px 75px 105px;'
                f'gap:8px;align-items:center;margin-bottom:3px;">'
                f'<span style="font-size:11px;color:{_MUTED};font-variant-numeric:tabular-nums;'
                f'font-weight:600;">{time_str}</span>'
                f'<span style="font-size:10px;color:{stars_color};">{stars}</span>'
                f'<span style="font-size:12px;font-weight:600;color:{_TEXT};">{e["name"]}</span>'
                f'<span style="font-size:11px;color:{_MUTED};text-align:right;">Préc.&nbsp;{prev_str}</span>'
                f'<span style="font-size:11px;color:{_MUTED};text-align:right;">Prévu&nbsp;{forecast_str}</span>'
                f'<span style="font-size:11px;color:{actual_color};font-weight:600;'
                f'text-align:right;">Actuel&nbsp;{actual_str}</span>'
                f'<span style="text-align:right;">{reaction_cell}</span></div>'
            )

        st.markdown(
            f'<div style="display:flex;flex-direction:column;">{"".join(cal_rows)}</div>',
            unsafe_allow_html=True
        )

    _main_widget()

    # ── Status agent ──────────────────────────────────────────────────────────
    running = _agent_running()
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if running:
            st.markdown(f"""
                <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);
                border-radius:10px;padding:12px 16px;display:flex;align-items:center;gap:10px;">
                    <span style="color:{_GREEN};font-size:10px;">●</span>
                    <span style="color:{_GREEN};font-weight:700;font-size:13px;">AGENT NEWS ACTIF</span>
                    <span style="color:{_MUTED};font-size:11px;margin-left:auto;">XAUUSD · MT5 DEMO</span>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style="background:rgba(100,116,139,0.08);border:1px solid rgba(100,116,139,0.2);
                border-radius:10px;padding:12px 16px;display:flex;align-items:center;gap:10px;">
                    <span style="color:{_MUTED};font-size:10px;">●</span>
                    <span style="color:{_MUTED};font-weight:700;font-size:13px;">AGENT NEWS INACTIF</span>
                </div>
            """, unsafe_allow_html=True)

    with col2:
        mt5_login    = st.text_input("Login MT5", placeholder="12345678", key="mt5_login", type="default")
        mt5_password = st.text_input("Mot de passe", placeholder="••••••", key="mt5_pw", type="password")
        mt5_server   = st.text_input("Serveur", placeholder="Vantage-Demo", key="mt5_srv")

    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if not running:
            if st.button("▶ Lancer Agent Gold", type="primary", use_container_width=True):
                _launch_news_agent(mt5_login, mt5_password, mt5_server)
                st.toast("Agent Gold démarré !")
                st.rerun()
        else:
            if st.button("⏹ Arrêter", type="secondary", use_container_width=True):
                _stop_news_agent()
                st.toast("Agent Gold arrêté")
                st.rerun()

        if st.button("🔄 Rafraîchir calendrier", use_container_width=True):
            try:
                sys.path.insert(0, str(_ROOT))
                from data.economic_calendar import fetch_upcoming_events
                n = fetch_upcoming_events(days_ahead=7)
                st.toast(f"{len(n)} événements récupérés")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:20px 0;">', unsafe_allow_html=True)

    # ── Live feed ─────────────────────────────────────────────────────────────
    @st.fragment(run_every=5)
    def _live_feed():
        log_lines = _read_log_tail(50)
        mt5_ok    = any("Connecté" in l for l in log_lines)
        finnhub_ok = any("événements gold" in l for l in log_lines)
        sim_mode  = any("mode simulation" in l.lower() for l in log_lines)

        # Statut connexions
        c1, c2, c3 = st.columns(3)
        with c1:
            color = _GREEN if mt5_ok else _GOLD
            label = "MT5 CONNECTÉ" if mt5_ok else "MT5 SIMULATION"
            st.markdown(f'<div style="background:rgba(0,0,0,0.2);border:1px solid {_GRID};border-radius:8px;padding:10px 14px;text-align:center;"><span style="color:{color};font-size:11px;font-weight:700;">{label}</span></div>', unsafe_allow_html=True)
        with c2:
            color = _GREEN if finnhub_ok else _GOLD
            label = "FINNHUB OK" if finnhub_ok else "FINNHUB MANQUANT"
            st.markdown(f'<div style="background:rgba(0,0,0,0.2);border:1px solid {_GRID};border-radius:8px;padding:10px 14px;text-align:center;"><span style="color:{color};font-size:11px;font-weight:700;">{label}</span></div>', unsafe_allow_html=True)
        with c3:
            color = _GOLD if sim_mode else _GREEN
            label = "MODE SIMULATION" if sim_mode else "MODE DEMO REEL"
            st.markdown(f'<div style="background:rgba(0,0,0,0.2);border:1px solid {_GRID};border-radius:8px;padding:10px 14px;text-align:center;"><span style="color:{color};font-size:11px;font-weight:700;">{label}</span></div>', unsafe_allow_html=True)

        st.markdown(f'<div style="font-size:11px;font-weight:700;color:{_MUTED};letter-spacing:1px;text-transform:uppercase;margin:14px 0 8px;">Activité en direct</div>', unsafe_allow_html=True)

        if not log_lines:
            st.markdown(f'<div style="color:{_MUTED};font-size:12px;padding:12px;">Aucun log — agent non démarré.</div>', unsafe_allow_html=True)
        else:
            lines_html = ""
            for line in reversed(log_lines[-25:]):
                color = _log_level_color(line)
                # Extrait heure + message
                parts = line.split("|")
                ts_part = parts[0].strip()[11:19] if len(parts) > 0 else ""
                msg = " | ".join(p.strip() for p in parts[2:]) if len(parts) > 2 else line
                lines_html += f'<div style="display:flex;gap:8px;padding:3px 0;border-bottom:1px solid rgba(26,34,53,0.5);"><span style="color:{_MUTED};font-size:10px;min-width:55px;font-family:monospace;">{ts_part}</span><span style="color:{color};font-size:11px;font-family:monospace;">{msg[:120]}</span></div>'

            st.markdown(f"""
                <div style="background:#060b12;border:1px solid {_GRID};border-radius:10px;
                padding:12px 14px;max-height:280px;overflow-y:auto;font-family:monospace;">
                    {lines_html}
                </div>
            """, unsafe_allow_html=True)

    _live_feed()

    # ── Swing Trading Section ─────────────────────────────────────────────────
    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:24px 0;">', unsafe_allow_html=True)
    st.markdown(f"""
        <div style="margin-bottom:16px;">
            <div style="font-size:18px;font-weight:800;color:{_GOLD};letter-spacing:-0.5px;">
                📈 Gold Swing Strategy — Multi-Timeframe
            </div>
            <div style="color:{_MUTED};font-size:12px;margin-top:3px;">
                Tendance Daily (EMA 20/50/200) · Entrée 4H pullback vers EMA20 · Stop/TP ATR
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Contrôles agent swing
    swing_running = _swing_agent_running()
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        color_sw = _GREEN if swing_running else _MUTED
        label_sw = "SWING AGENT ACTIF — vérifie toutes les 4H" if swing_running else "SWING AGENT INACTIF"
        st.markdown(f"""
            <div style="background:rgba(0,0,0,0.2);border:1px solid {_GRID};border-radius:10px;
            padding:12px 16px;display:flex;align-items:center;gap:10px;">
                <span style="color:{color_sw};font-size:10px;">●</span>
                <span style="color:{color_sw};font-weight:700;font-size:13px;">{label_sw}</span>
            </div>
        """, unsafe_allow_html=True)
    with sc2:
        if not swing_running:
            if st.button("▶ Lancer Swing Agent", type="primary", use_container_width=True, key="swing_start"):
                _launch_swing_agent(
                    st.session_state.get("mt5_login", ""),
                    st.session_state.get("mt5_pw", ""),
                    st.session_state.get("mt5_srv", ""),
                )
                st.toast("Swing Agent démarré !")
                st.rerun()
        else:
            if st.button("⏹ Arrêter Swing", type="secondary", use_container_width=True, key="swing_stop"):
                _stop_swing_agent()
                st.toast("Swing Agent arrêté")
                st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Signal en temps réel
    @st.fragment(run_every=300)   # rafraîchit toutes les 5 min
    def _swing_signal_panel():
        sig = _get_swing_signal()
        action = sig["action"]
        conf   = sig["confidence"]
        trend  = sig["daily_trend"]
        price  = sig["price"]
        rsi    = sig["rsi_4h"]
        ema20  = sig["ema20_4h"]
        atr    = sig["atr"]
        sl, tp = sig["sl"], sig["tp"]

        # Couleurs
        if action == "BUY":
            act_color, act_bg = _GREEN, "rgba(16,185,129,0.08)"
        elif action == "SELL":
            act_color, act_bg = _RED, "rgba(244,63,94,0.08)"
        else:
            act_color, act_bg = _MUTED, "rgba(0,0,0,0.1)"

        if trend == "HAUSSIER":
            trend_color, trend_arrow = _GREEN, "▲"
        elif trend == "BAISSIER":
            trend_color, trend_arrow = _RED, "▼"
        else:
            trend_color, trend_arrow = _MUTED, "—"

        dist_pct = abs(price - ema20) / ema20 * 100 if ema20 else 0
        rr = round(tp / atr * (1 / 1.5), 1) if atr else 0  # approx R:R

        st.markdown(f"""
            <div style="background:{act_bg};border:1px solid {act_color}33;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
                <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
                    <div style="text-align:center;">
                        <div style="font-size:26px;font-weight:900;color:{act_color};">{action}</div>
                        <div style="font-size:10px;color:{_MUTED};">SIGNAL</div>
                    </div>
                    <div style="width:1px;height:40px;background:{_GRID};"></div>
                    <div>
                        <div style="font-size:13px;font-weight:700;color:{_TEXT};">Prix actuel</div>
                        <div style="font-size:18px;font-weight:800;color:{_GOLD};">${price:,.2f}</div>
                    </div>
                    <div>
                        <div style="font-size:12px;color:{_MUTED};">Tendance Daily</div>
                        <div style="font-size:14px;font-weight:700;color:{trend_color};">{trend_arrow} {trend}</div>
                    </div>
                    <div>
                        <div style="font-size:12px;color:{_MUTED};">RSI (4H)</div>
                        <div style="font-size:14px;font-weight:700;color:{_TEXT};">{rsi}</div>
                    </div>
                    <div>
                        <div style="font-size:12px;color:{_MUTED};">EMA20 (4H)</div>
                        <div style="font-size:14px;font-weight:700;color:{_TEXT};">${ema20:,.2f}</div>
                        <div style="font-size:10px;color:{_MUTED};">écart {dist_pct:.2f}%</div>
                    </div>
                    <div>
                        <div style="font-size:12px;color:{_MUTED};">ATR (4H)</div>
                        <div style="font-size:14px;font-weight:700;color:{_TEXT};">${atr:.2f}</div>
                    </div>
                    {'<div><div style="font-size:12px;color:' + _MUTED + ';">SL / TP</div><div style="font-size:12px;font-weight:700;color:' + _RED + ';">$' + f"{sl:.2f}" + '</div><div style="font-size:12px;font-weight:700;color:' + _GREEN + ';">$' + f"{tp:.2f}" + '</div></div>' if action != "HOLD" else ""}
                    <div style="margin-left:auto;text-align:right;">
                        <div style="font-size:10px;color:{_MUTED};">Confiance</div>
                        <div style="font-size:20px;font-weight:900;color:{act_color};">{conf:.0%}</div>
                    </div>
                </div>
                <div style="margin-top:12px;padding-top:10px;border-top:1px solid {_GRID};
                color:{_MUTED};font-size:11px;">{sig['reason']}</div>
            </div>
        """, unsafe_allow_html=True)

    _swing_signal_panel()

    # Historique trades swing
    swing_trades = _load_swing_trades()
    if swing_trades:
        st.markdown(f'<div style="font-size:11px;font-weight:700;color:{_MUTED};letter-spacing:1px;text-transform:uppercase;margin:12px 0 8px;">Historique trades swing</div>', unsafe_allow_html=True)
        for t in swing_trades:
            color = _GREEN if t["action"] == "BUY" else _RED if t["action"] == "SELL" else _MUTED
            reason_short = (t.get("reason") or "")[:100]
            st.markdown(f"""
                <div style="background:{_CARD};border:1px solid {_GRID};border-left:3px solid {color};
                border-radius:8px;padding:10px 14px;margin-bottom:6px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="color:{color};font-weight:800;font-size:13px;">{t['action']}</span>
                        <span style="color:{_TEXT};font-size:12px;">${float(t['price']):.2f}</span>
                        <span style="color:{_MUTED};font-size:11px;">{t['ts'][5:16]}</span>
                        <span style="color:{_MUTED};font-size:10px;margin-left:auto;">conf={float(t['confidence']):.0%}</span>
                    </div>
                    <div style="color:{_MUTED};font-size:11px;margin-top:4px;">{reason_short}</div>
                </div>
            """, unsafe_allow_html=True)


def _launch_news_agent(login: str, password: str, server: str) -> None:
    import json, os
    script = _ROOT / "run_news_agent.py"
    log    = _ROOT / "logs" / "news_agent.log"
    log.parent.mkdir(exist_ok=True)

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if login:    env["MT5_LOGIN"]    = login
    if password: env["MT5_PASSWORD"] = password
    if server:   env["MT5_SERVER"]   = server

    with open(log, "a") as fout:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(_ROOT),
            stdout=fout, stderr=fout,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=env,
        )

    proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
    try:
        data = json.loads(proc_file.read_text())
    except Exception:
        data = {"agents": {}}
    import time
    data["agents"]["XAUUSD-NEWS"] = {"running": True, "pid": proc.pid, "started_at": time.time()}
    proc_file.write_text(json.dumps(data))


def _stop_news_agent() -> None:
    import json
    proc_file = _ROOT / "agent" / "memory_store" / "agent_process.json"
    try:
        data = json.loads(proc_file.read_text())
        pid = data.get("agents", {}).get("XAUUSD-NEWS", {}).get("pid")
        if pid:
            import psutil
            psutil.Process(pid).kill()
        data["agents"]["XAUUSD-NEWS"] = {"running": False, "pid": None}
        proc_file.write_text(json.dumps(data))
    except Exception:
        pass
