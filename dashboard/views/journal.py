"""
Journal de Trading Personnel — NEXORA
Deux onglets : Entraînement (paper) + Fond Propre (real capital).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_JOURNAL_DB = _ROOT / "data" / "journal.db"
_MACRO_DB   = _ROOT / "data" / "trading_memory.db"

_CARD  = "#0f1724"
_GRID  = "#1a2235"
_TEXT  = "#e2e8f0"
_MUTED = "#64748b"
_GREEN = "#10b981"
_RED   = "#f43f5e"
_GOLD  = "#f59e0b"
_BLUE  = "#3b82f6"
_PARIS = timedelta(hours=2)


# ── DB ────────────────────────────────────────────────────────────────────────

def _init_db():
    con = sqlite3.connect(str(_JOURNAL_DB))
    con.execute("""
        CREATE TABLE IF NOT EXISTS personal_trades (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT    NOT NULL,
            trade_type TEXT    NOT NULL DEFAULT 'paper',
            asset      TEXT    NOT NULL,
            direction  TEXT    NOT NULL,
            entry      REAL    NOT NULL,
            exit       REAL,
            lots       REAL    NOT NULL DEFAULT 0.01,
            sl         REAL,
            tp         REAL,
            result     REAL,
            pips       REAL,
            session    TEXT,
            setup      TEXT,
            notes      TEXT,
            status     TEXT    DEFAULT 'open'
        )
    """)
    # Migration : ajoute trade_type si absente (DB existante)
    try:
        con.execute("ALTER TABLE personal_trades ADD COLUMN trade_type TEXT NOT NULL DEFAULT 'paper'")
    except Exception:
        pass
    # Table capital fond propre
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_capital (
            id                  INTEGER PRIMARY KEY,
            initial_capital     REAL    NOT NULL DEFAULT 0,
            current_capital     REAL    NOT NULL DEFAULT 0,
            withdrawable_profit REAL    NOT NULL DEFAULT 0,
            updated_at          TEXT
        )
    """)
    try:
        con.execute("ALTER TABLE trading_capital ADD COLUMN withdrawable_profit REAL NOT NULL DEFAULT 0")
    except Exception:
        pass
    # Initialise une ligne si vide
    if not con.execute("SELECT id FROM trading_capital LIMIT 1").fetchone():
        con.execute("INSERT INTO trading_capital (id, initial_capital, current_capital, withdrawable_profit, updated_at) VALUES (1, 0, 0, 0, ?)",
                    (datetime.now(timezone.utc).isoformat(),))
    con.commit()
    con.close()


def _load_trades(trade_type: str) -> list[dict]:
    try:
        con = sqlite3.connect(str(_JOURNAL_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM personal_trades WHERE trade_type=? ORDER BY ts DESC LIMIT 200",
            (trade_type,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _add_trade(trade_type, asset, direction, entry, exit_price, lots, sl, tp,
               result, pips, session, setup, notes, status):
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    con.execute("""
        INSERT INTO personal_trades
        (ts, trade_type, asset, direction, entry, exit, lots, sl, tp, result, pips, session, setup, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ts, trade_type, asset, direction, entry, exit_price, lots, sl, tp,
          result, pips, session, setup, notes, status))
    # Si trade réel fermé avec résultat → maj capital
    if trade_type == "real" and status == "closed" and result is not None:
        con.execute("""
            UPDATE trading_capital
            SET current_capital = current_capital + ?,
                updated_at = ?
            WHERE id = 1
        """, (result, ts))
    con.commit()
    con.close()


def _update_trade_exit(trade_id: int, exit_price: float, result: float, pips: float, trade_type: str):
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    con.execute("""
        UPDATE personal_trades
        SET exit=?, result=?, pips=?, status='closed'
        WHERE id=?
    """, (exit_price, result, pips, trade_id))
    if trade_type == "real":
        con.execute("""
            UPDATE trading_capital
            SET current_capital = current_capital + ?,
                updated_at = ?
            WHERE id = 1
        """, (result, ts))
    con.commit()
    con.close()


def _update_trade_full(trade_id: int, asset, direction, entry, exit_price, lots,
                       sl, tp, result, pips, session, setup, notes, status, trade_type):
    """Mise à jour complète d'un trade (édition)."""
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    # Ancienne valeur du résultat pour ajuster le capital
    old = con.execute("SELECT result, status FROM personal_trades WHERE id=?", (trade_id,)).fetchone()
    con.execute("""
        UPDATE personal_trades
        SET asset=?, direction=?, entry=?, exit=?, lots=?, sl=?, tp=?,
            result=?, pips=?, session=?, setup=?, notes=?, status=?
        WHERE id=?
    """, (asset, direction, entry, exit_price, lots, sl, tp,
          result, pips, session, setup, notes, status, trade_id))
    # Ajuste le capital si trade réel : annule l'ancien, applique le nouveau
    if trade_type == "real":
        old_result = float(old[0] or 0) if old and old[1] == "closed" else 0
        new_result = float(result or 0) if status == "closed" else 0
        delta = new_result - old_result
        if delta != 0:
            con.execute("UPDATE trading_capital SET current_capital=current_capital+?, updated_at=? WHERE id=1",
                        (delta, ts))
    con.commit()
    con.close()


def _delete_trade(trade_id: int, trade_type: str):
    """Supprime un trade et annule son impact sur le capital."""
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    old = con.execute("SELECT result, status FROM personal_trades WHERE id=?", (trade_id,)).fetchone()
    con.execute("DELETE FROM personal_trades WHERE id=?", (trade_id,))
    if trade_type == "real" and old and old[1] == "closed" and old[0]:
        con.execute("UPDATE trading_capital SET current_capital=current_capital-?, updated_at=? WHERE id=1",
                    (float(old[0]), ts))
    con.commit()
    con.close()


def _calc_trade(direction: str, entry: float, exit_price: float, lots: float, asset: str) -> tuple[float, float]:
    """Calcule pips et résultat en $ selon l'actif."""
    if not entry or not exit_price or not lots:
        return 0.0, 0.0
    move = exit_price - entry if direction == "BUY" else entry - exit_price
    # Pip size selon l'actif
    pip_size = 0.01 if asset in ("XAUUSD",) else \
               0.25  if asset in ("NQ", "US30") else \
               0.0001
    pips = round(move / pip_size, 1)
    # Valeur en $ : pour XAU 1 lot std = 100 oz → $1 move = $100/lot
    if asset == "XAUUSD":
        result = round(move * lots * 100, 2)
    elif asset in ("NQ", "US30"):
        result = round(move * lots * 20, 2)   # NQ: $20/point/contrat
    else:
        result = round(move * lots * 100000, 2)  # Forex: 100k unités/lot
    return pips, result


def _get_capital() -> dict:
    try:
        con = sqlite3.connect(str(_JOURNAL_DB))
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM trading_capital WHERE id=1").fetchone()
        con.close()
        return dict(row) if row else {"initial_capital": 0, "current_capital": 0}
    except Exception:
        return {"initial_capital": 0, "current_capital": 0}


def _set_withdrawable(amount: float):
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    con.execute("UPDATE trading_capital SET withdrawable_profit=?, updated_at=? WHERE id=1", (amount, ts))
    con.commit()
    con.close()


def _set_capital(initial: float):
    con = sqlite3.connect(str(_JOURNAL_DB))
    ts = datetime.now(timezone.utc).isoformat()
    # Recalcule current = initial + somme des trades réels fermés
    row = con.execute("""
        SELECT COALESCE(SUM(result), 0) as total
        FROM personal_trades
        WHERE trade_type='real' AND status='closed' AND result IS NOT NULL
    """).fetchone()
    total_pnl = float(row[0]) if row else 0.0
    current = initial + total_pnl
    con.execute("""
        UPDATE trading_capital
        SET initial_capital=?, current_capital=?, updated_at=?
        WHERE id=1
    """, (initial, current, ts))
    con.commit()
    con.close()


# ── Calendrier ────────────────────────────────────────────────────────────────

def _load_events() -> list[dict]:
    try:
        con = sqlite3.connect(str(_MACRO_DB))
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM economic_events ORDER BY ts").fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Signal Swing ──────────────────────────────────────────────────────────────

def _get_swing_trend() -> dict:
    try:
        from strategies.gold_swing_strategy import GoldSwingStrategy
        sig = GoldSwingStrategy().analyze()
        return {"trend": sig.daily_trend, "price": sig.price, "rsi": sig.rsi_4h,
                "action": sig.action, "confidence": sig.confidence}
    except Exception:
        return {"trend": "—", "price": 0.0, "rsi": 0, "action": "—", "confidence": 0.0}


# ── Coach IA ─────────────────────────────────────────────────────────────────

def _coach_analysis(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    closed = [t for t in trades if t["status"] == "closed" and t["result"] is not None]
    if len(closed) < 3:
        return [{"type": "info", "msg": "Enregistre au moins 3 trades fermés pour recevoir une analyse."}]

    tips = []
    results  = [float(t["result"]) for t in closed]
    winners  = [r for r in results if r > 0]
    losers   = [r for r in results if r <= 0]
    win_rate = len(winners) / len(results) if results else 0
    avg_win  = sum(winners) / len(winners) if winners else 0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 0
    rr_actual = avg_win / avg_loss if avg_loss > 0 else 0
    total_pnl = sum(results)

    if win_rate < 0.4:
        tips.append({"type": "warning", "msg": f"Win rate {win_rate:.0%} — assure-toi d'avoir un RR ≥ 1:2.5 pour rester profitable."})
    elif win_rate > 0.65:
        tips.append({"type": "success", "msg": f"Excellent win rate {win_rate:.0%}. Attention à ne pas prendre des TP trop proches."})
    else:
        tips.append({"type": "success", "msg": f"Win rate {win_rate:.0%} — correct. L'important c'est le RR."})

    if rr_actual < 1.0 and avg_loss > 0:
        tips.append({"type": "danger", "msg": f"RR réel {rr_actual:.1f}:1 — tu gagnes moins que tu perds. Laisse courir tes profits."})
    elif rr_actual >= 2.0:
        tips.append({"type": "success", "msg": f"Bon RR réel {rr_actual:.1f}:1. Continue à laisser courir tes gagnants."})

    streak = max_streak = 0
    for r in results:
        streak = streak + 1 if r <= 0 else 0
        max_streak = max(max_streak, streak)
    if max_streak >= 3:
        tips.append({"type": "warning", "msg": f"{max_streak} pertes consécutives détectées. Règle : après 2 pertes, stop pour la journée."})

    sess_res: dict[str, list] = {}
    for t in closed:
        s = t.get("session") or "Non définie"
        sess_res.setdefault(s, []).append(float(t["result"] or 0))
    if len(sess_res) > 1:
        worst = min(sess_res, key=lambda s: sum(sess_res[s]))
        best  = max(sess_res, key=lambda s: sum(sess_res[s]))
        if sum(sess_res[worst]) < 0:
            tips.append({"type": "warning", "msg": f"Session {worst} négative. Concentre-toi sur {best}."})

    setup_res: dict[str, list] = {}
    for t in closed:
        s = t.get("setup") or "Non défini"
        setup_res.setdefault(s, []).append(float(t["result"] or 0))
    if len(setup_res) > 1:
        worst = min(setup_res, key=lambda s: sum(setup_res[s]))
        best  = max(setup_res, key=lambda s: sum(setup_res[s]))
        if sum(setup_res[worst]) < 0:
            tips.append({"type": "info", "msg": f"Setup '{worst}' négatif. Ton meilleur setup : '{best}'."})

    if total_pnl > 0:
        tips.append({"type": "success", "msg": f"PnL total +${total_pnl:.2f} — protège ton capital, ne sur-trade pas."})
    else:
        tips.append({"type": "danger", "msg": f"PnL total ${total_pnl:.2f} — reviens aux setups A+ uniquement."})

    return tips


# ── Widget trades partagé ─────────────────────────────────────────────────────

def _trade_section(trade_type: str, label: str):
    trades = _load_trades(trade_type)
    closed = [t for t in trades if t["status"] == "closed" and t["result"] is not None]
    open_t = [t for t in trades if t["status"] == "open"]
    results  = [float(t["result"]) for t in closed]
    winners  = [r for r in results if r > 0]
    losers   = [r for r in results if r <= 0]
    win_rate = len(winners) / len(results) * 100 if results else 0
    total_pnl = sum(results)
    avg_rr   = (sum(winners)/len(winners)) / (abs(sum(losers)/len(losers))) if winners and losers else 0

    # Session state pour l'édition
    edit_key = f"_edit_trade_{trade_type}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = None

    col_left, col_right = st.columns([3, 2])

    with col_left:

        # Stats
        pnl_color = _GREEN if total_pnl >= 0 else _RED
        wr_color  = _GREEN if win_rate >= 50 else _RED
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:9px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">Trades</div>
                <div style="font-size:22px;font-weight:800;color:{_TEXT};">{len(trades)}</div>
            </div>
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:9px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">Win Rate</div>
                <div style="font-size:22px;font-weight:800;color:{wr_color};">{win_rate:.0f}%</div>
            </div>
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:9px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">PnL Total</div>
                <div style="font-size:22px;font-weight:800;color:{pnl_color};">{"+" if total_pnl>=0 else ""}${total_pnl:.2f}</div>
            </div>
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:9px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">RR Réel</div>
                <div style="font-size:22px;font-weight:800;color:{_TEXT};">{avg_rr:.1f}:1</div>
            </div>
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:9px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">En cours</div>
                <div style="font-size:22px;font-weight:800;color:{_GOLD};">{len(open_t)}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Fond propre — capital widget
        if trade_type == "real":
            cap = _get_capital()
            init_cap    = float(cap["initial_capital"])
            curr_cap    = float(cap["current_capital"])
            withdraw    = float(cap.get("withdrawable_profit", 0))
            pnl_cap     = curr_cap - init_cap
            pnl_cap_pct = pnl_cap / init_cap * 100 if init_cap > 0 else 0
            cap_color   = _GREEN if pnl_cap >= 0 else _RED

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,rgba(245,158,11,0.08),rgba(245,158,11,0.02));
            border:1px solid rgba(245,158,11,0.3);border-radius:12px;padding:16px 20px;margin-bottom:14px;">
                <div style="font-size:10px;color:{_GOLD};font-weight:700;text-transform:uppercase;
                letter-spacing:1px;margin-bottom:10px;">💰 Fond Propre</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;">
                    <div>
                        <div style="font-size:10px;color:{_MUTED};">Capital initial</div>
                        <div style="font-size:18px;font-weight:800;color:{_TEXT};">${init_cap:,.2f}</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:{_MUTED};">Capital actuel</div>
                        <div style="font-size:18px;font-weight:800;color:{_GOLD};">${curr_cap:,.2f}</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:{_MUTED};">Gain / Perte</div>
                        <div style="font-size:18px;font-weight:800;color:{cap_color};">
                            {"+" if pnl_cap>=0 else ""}${pnl_cap:.2f}
                        </div>
                        <div style="font-size:11px;color:{cap_color};">{pnl_cap_pct:+.1f}%</div>
                    </div>
                    <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);
                    border-radius:8px;padding:8px 10px;">
                        <div style="font-size:10px;color:{_GREEN};font-weight:700;">💸 Retirable</div>
                        <div style="font-size:18px;font-weight:800;color:{_GREEN};">€{withdraw:,.2f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("⚙️ Modifier le capital / profit retirable"):
                new_cap = st.number_input("Capital initial ($)", value=init_cap,
                                          min_value=0.0, step=100.0, format="%.2f",
                                          key=f"cap_input_{trade_type}")
                new_withdraw = st.number_input("Profit retirable (€)", value=withdraw,
                                               min_value=0.0, step=1.0, format="%.2f",
                                               key=f"cap_withdraw_{trade_type}")
                if st.button("Enregistrer", key=f"cap_save_{trade_type}"):
                    _set_capital(new_cap)
                    _set_withdrawable(new_withdraw)
                    st.toast(f"Mis à jour — Retirable : €{new_withdraw:,.2f}")
                    st.rerun()

        # ── Formulaire édition (si un trade est sélectionné) ──────────────────
        edit_t = st.session_state[edit_key]
        if edit_t is not None:
            with st.expander(f"✏️ Modifier le trade #{edit_t['id']}", expanded=True):
                _assets = ["XAUUSD","NQ","US30","EURUSD","GBPUSD","SPY","BTC"]
                _setups = ["London Raid","FVG","Order Block","OTE Fibonacci","BOS/CHoCH","Autre"]
                _sess   = ["London","New York","Asie","Overlap"]

                e1, e2 = st.columns(2)
                with e1:
                    e_asset = st.selectbox("Actif", _assets,
                        index=_assets.index(edit_t["asset"]) if edit_t["asset"] in _assets else 0,
                        key=f"e_asset_{trade_type}")
                    e_dir   = st.radio("Direction", ["BUY","SELL"], horizontal=True,
                        index=0 if edit_t["direction"]=="BUY" else 1,
                        key=f"e_dir_{trade_type}")
                    e_entry = st.number_input("Entrée", value=float(edit_t["entry"] or 0),
                        step=0.01, format="%.2f", key=f"e_entry_{trade_type}")
                    e_lots  = st.number_input("Lots", value=float(edit_t["lots"] or 0.01),
                        min_value=0.01, step=0.01, format="%.2f", key=f"e_lots_{trade_type}")
                with e2:
                    e_setup = st.selectbox("Setup", _setups,
                        index=_setups.index(edit_t["setup"]) if edit_t.get("setup") in _setups else 5,
                        key=f"e_setup_{trade_type}")
                    e_sess  = st.selectbox("Session", _sess,
                        index=_sess.index(edit_t["session"]) if edit_t.get("session") in _sess else 0,
                        key=f"e_sess_{trade_type}")
                    e_sl = st.number_input("Stop Loss", value=float(edit_t["sl"] or 0),
                        step=0.01, format="%.2f", key=f"e_sl_{trade_type}")
                    e_tp = st.number_input("Take Profit", value=float(edit_t["tp"] or 0),
                        step=0.01, format="%.2f", key=f"e_tp_{trade_type}")

                e_notes = st.text_area("Notes", value=edit_t.get("notes") or "",
                    height=50, key=f"e_notes_{trade_type}")
                e_status_closed = st.checkbox("Trade fermé",
                    value=edit_t["status"]=="closed", key=f"e_status_{trade_type}")
                e_exit = e_result = 0.0
                if e_status_closed:
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        e_exit = st.number_input("Prix de sortie",
                            value=float(edit_t["exit"] or 0),
                            step=0.01, format="%.2f", key=f"e_exit_{trade_type}")
                    with ec2:
                        e_result = st.number_input("Résultat ($)",
                            value=float(edit_t["result"] or 0),
                            step=0.01, format="%.2f", key=f"e_result_{trade_type}")
                    if e_entry > 0 and e_exit > 0:
                        auto_pips_e, _ = _calc_trade(e_dir, e_entry, e_exit, e_lots, e_asset)
                        st.caption(f"📐 Pips : **{auto_pips_e:+.1f}**")

                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if st.button("💾 Sauvegarder", type="primary", use_container_width=True, key=f"e_save_{trade_type}"):
                        e_status = "closed" if e_status_closed else "open"
                        e_pips, e_res = _calc_trade(e_dir, e_entry, e_exit, e_lots, e_asset) if e_status_closed and e_exit > 0 else (None, e_result)
                        _update_trade_full(edit_t["id"], e_asset, e_dir, e_entry,
                                           e_exit if e_status_closed else None, e_lots,
                                           e_sl or None, e_tp or None,
                                           e_result if e_status_closed else None,
                                           e_pips if e_status_closed and e_exit > 0 else None,
                                           e_sess, e_setup, e_notes, e_status, trade_type)
                        st.session_state[edit_key] = None
                        st.toast("✅ Trade mis à jour !")
                        st.rerun()
                with btn_c2:
                    if st.button("Annuler", use_container_width=True, key=f"e_cancel_{trade_type}"):
                        st.session_state[edit_key] = None
                        st.rerun()

        # ── Formulaire ajout trade ─────────────────────────────────────────────
        with st.expander(f"➕ Enregistrer un trade {label}", expanded=len(trades) == 0):
            _assets = ["XAUUSD","NQ","US30","EURUSD","GBPUSD","SPY","BTC"]
            _setups = ["London Raid","FVG","Order Block","OTE Fibonacci","BOS/CHoCH","Autre"]
            _sess   = ["London","New York","Asie","Overlap"]
            f1, f2 = st.columns(2)
            with f1:
                asset     = st.selectbox("Actif", _assets, key=f"j_asset_{trade_type}")
                direction = st.radio("Direction", ["BUY","SELL"], horizontal=True, key=f"j_dir_{trade_type}")
                entry     = st.number_input("Entrée", value=0.0, step=0.01, format="%.2f", key=f"j_entry_{trade_type}")
                lots      = st.number_input("Lots", value=0.01, step=0.01, min_value=0.01, format="%.2f", key=f"j_lots_{trade_type}")
            with f2:
                setup   = st.selectbox("Setup", _setups, key=f"j_setup_{trade_type}")
                session = st.selectbox("Session", _sess, key=f"j_session_{trade_type}")
                sl      = st.number_input("Stop Loss", value=0.0, step=0.01, format="%.2f", key=f"j_sl_{trade_type}")
                tp      = st.number_input("Take Profit", value=0.0, step=0.01, format="%.2f", key=f"j_tp_{trade_type}")

            notes     = st.text_area("Notes", height=50, key=f"j_notes_{trade_type}")
            is_closed = st.checkbox("Trade déjà fermé", key=f"j_closed_{trade_type}")
            exit_price = 0.0
            result = 0.0
            status = "open"
            pips_auto = 0.0
            if is_closed:
                c1, c2 = st.columns(2)
                with c1:
                    exit_price = st.number_input("Prix de sortie", value=0.0, step=0.01,
                                                 format="%.2f", key=f"j_exit_{trade_type}")
                with c2:
                    result = st.number_input("Résultat ($)", value=0.0, step=0.01,
                                             format="%.2f", key=f"j_result_{trade_type}")
                if entry > 0 and exit_price > 0:
                    pips_auto, _ = _calc_trade(direction, entry, exit_price, lots, asset)
                    st.caption(f"📐 Pips : **{pips_auto:+.1f}**")
                status = "closed"

            if st.button("💾 Enregistrer", type="primary", use_container_width=True, key=f"j_save_{trade_type}"):
                if entry > 0:
                    final_pips = pips_auto if is_closed and exit_price > 0 else None
                    final_result = result if is_closed else None
                    _add_trade(trade_type, asset, direction, entry,
                               exit_price if is_closed else None, lots,
                               sl or None, tp or None,
                               final_result, final_pips,
                               session, setup, notes, status)
                    st.toast("✅ Trade enregistré !")
                    st.rerun()
                else:
                    st.error("Remplis au moins le prix d'entrée.")

        # ── Historique complet ─────────────────────────────────────────────────
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};'
            f'letter-spacing:1px;text-transform:uppercase;margin:12px 0 8px;">Historique</div>',
            unsafe_allow_html=True
        )

        if not trades:
            st.info(f"Aucun trade {label} pour l'instant.")
        else:
            # Tableau HTML scrollable avec toutes les colonnes
            cols_def = "80px 60px 48px 72px 72px 50px 55px 62px 75px 70px 80px 1fr"
            header_html = (
                f'<div style="display:grid;grid-template-columns:{cols_def};gap:4px;'
                f'padding:6px 10px;background:{_GRID};border-radius:8px 8px 0 0;'
                f'font-size:9px;color:{_MUTED};font-weight:700;text-transform:uppercase;'
                f'position:sticky;top:0;">'
                f'<span>Date</span><span>Actif</span><span>Dir</span>'
                f'<span>Entrée</span><span>Sortie</span><span>Lots</span>'
                f'<span>Pips</span><span>P&L $</span><span>Setup</span>'
                f'<span>Session</span><span>Statut</span><span>Notes</span></div>'
            )
            rows_html = ""
            for t in trades:
                d   = t["direction"]
                dc  = _GREEN if d == "BUY" else _RED
                res = float(t["result"]) if t["result"] is not None else None
                rc  = _GREEN if (res or 0) >= 0 else _RED
                res_str  = f'{"+" if (res or 0)>=0 else ""}${res:.2f}' if res is not None else "—"
                # Pips : affiche seulement si exit renseigné
                if t["pips"] is not None:
                    pips_str = f'{float(t["pips"]):+.1f}'
                elif t["exit"] and float(t["exit"]) > 0 and t["entry"]:
                    _p, _ = _calc_trade(d, float(t["entry"]), float(t["exit"]), float(t["lots"]), t["asset"])
                    pips_str = f'{_p:+.1f}'
                else:
                    pips_str = "—"
                exit_str = f'${float(t["exit"]):.2f}' if t["exit"] else "—"
                ts_short = t["ts"][5:16].replace("T", " ")
                status_badge = (
                    f'<span style="background:rgba(16,185,129,0.12);color:{_GREEN};'
                    f'font-size:9px;font-weight:700;padding:2px 6px;border-radius:20px;">FERMÉ</span>'
                    if t["status"] == "closed" else
                    f'<span style="background:rgba(245,158,11,0.12);color:{_GOLD};'
                    f'font-size:9px;font-weight:700;padding:2px 6px;border-radius:20px;">OUVERT</span>'
                )
                notes_val = (t.get("notes") or "—")[:30]
                rows_html += (
                    f'<div style="display:grid;grid-template-columns:{cols_def};'
                    f'gap:4px;padding:7px 10px;border-bottom:1px solid {_GRID};font-size:11px;align-items:center;">'
                    f'<span style="color:{_MUTED};font-size:9px;">{ts_short}</span>'
                    f'<span style="color:{_TEXT};font-weight:600;">{t["asset"]}</span>'
                    f'<span style="color:{dc};font-weight:700;">{d}</span>'
                    f'<span style="color:{_TEXT};">${float(t["entry"]):.2f}</span>'
                    f'<span style="color:{_MUTED};">{exit_str}</span>'
                    f'<span style="color:{_TEXT};">{float(t["lots"]):.2f}</span>'
                    f'<span style="color:{rc if pips_str != "—" else _MUTED};">{pips_str}</span>'
                    f'<span style="color:{rc};font-weight:700;">{res_str}</span>'
                    f'<span style="color:{_MUTED};font-size:10px;">{t.get("setup","") or "—"}</span>'
                    f'<span style="color:{_MUTED};font-size:10px;">{t.get("session","") or "—"}</span>'
                    f'<span>{status_badge}</span>'
                    f'<span style="color:{_MUTED};font-size:10px;">{notes_val}</span>'
                    f'</div>'
                )

            # Boutons d'édition séparés (Streamlit ne peut pas être dans un HTML statique)
            st.markdown(
                f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;'
                f'overflow-x:auto;max-height:420px;overflow-y:auto;">'
                f'{header_html}{rows_html}</div>',
                unsafe_allow_html=True
            )

            # Boutons ✏️ / 🗑 par trade
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:10px;color:{_MUTED};margin-bottom:4px;">Sélectionne un trade à modifier ou supprimer :</div>',
                unsafe_allow_html=True
            )
            btn_cols = st.columns(min(len(trades), 6))
            for idx, t in enumerate(trades):
                with btn_cols[idx % len(btn_cols)]:
                    short_label = f"#{t['id']} {t['asset']}"
                    if st.button(f"✏️ {short_label}", key=f"edit_{trade_type}_{t['id']}", use_container_width=True):
                        st.session_state[edit_key] = t
                        st.rerun()

            # Supprimer un trade
            with st.expander("🗑 Supprimer un trade"):
                del_opts = {f"#{t['id']} {t['asset']} {t['direction']} @ {t['entry']}": t for t in trades}
                del_sel = st.selectbox("Trade à supprimer", list(del_opts.keys()), key=f"j_del_sel_{trade_type}")
                if st.button("Supprimer définitivement", type="secondary", key=f"j_del_btn_{trade_type}"):
                    _delete_trade(del_opts[del_sel]["id"], trade_type)
                    st.toast("Trade supprimé.")
                    st.rerun()

            # Fermer un trade ouvert
            if open_t:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                with st.expander(f"Fermer un trade ({len(open_t)} en cours)"):
                    opts = {f"#{t['id']} {t['asset']} {t['direction']} @ {t['entry']}": t for t in open_t}
                    sel_label = st.selectbox("Trade", list(opts.keys()), key=f"j_close_sel_{trade_type}")
                    sel_t = opts[sel_label]
                    c1, c2 = st.columns(2)
                    with c1:
                        exit_p = st.number_input("Sortie", value=float(sel_t["entry"]),
                            step=0.01, format="%.2f", key=f"j_close_exit_{trade_type}")
                    with c2:
                        close_res = st.number_input("Résultat ($)", value=0.0,
                            step=0.01, format="%.2f", key=f"j_close_res_{trade_type}")
                    entry_p = float(sel_t["entry"])
                    close_pips_v = 0.0
                    if exit_p > 0 and entry_p > 0:
                        close_pips_v, _ = _calc_trade(
                            sel_t["direction"], entry_p, exit_p,
                            float(sel_t["lots"]), sel_t["asset"]
                        )
                        st.caption(f"📐 Pips : **{close_pips_v:+.1f}**")
                    if st.button("Fermer ce trade", type="primary", key=f"j_close_btn_{trade_type}"):
                        _update_trade_exit(sel_t["id"], exit_p, close_res, close_pips_v, trade_type)
                        st.toast("Trade fermé !")
                        st.rerun()

    with col_right:
        # Coach IA
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};'
            f'letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Coach IA</div>',
            unsafe_allow_html=True
        )
        tips = _coach_analysis(trades)
        _tip_styles = {
            "success": (_GREEN, "rgba(16,185,129,0.08)", "✅"),
            "warning": (_GOLD,  "rgba(245,158,11,0.08)", "⚠️"),
            "danger":  (_RED,   "rgba(244,63,94,0.07)",  "🚨"),
            "info":    (_BLUE,  "rgba(59,130,246,0.07)", "💡"),
        }
        if not tips:
            st.markdown(f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:10px;padding:14px;color:{_MUTED};font-size:12px;">Enregistre des trades pour recevoir une analyse.</div>', unsafe_allow_html=True)
        else:
            html = ""
            for tip in tips:
                col, bg, icon = _tip_styles.get(tip["type"], (_MUTED, _CARD, "ℹ️"))
                html += (f'<div style="background:{bg};border-left:3px solid {col};border-radius:0 8px 8px 0;'
                         f'padding:10px 12px;margin-bottom:8px;font-size:12px;color:{_TEXT};">'
                         f'<span style="margin-right:6px;">{icon}</span>{tip["msg"]}</div>')
            st.markdown(html, unsafe_allow_html=True)


# ── Render ────────────────────────────────────────────────────────────────────

def render(_ticker: str = "XAUUSD") -> None:
    _init_db()

    now_utc   = datetime.now(timezone.utc)
    now_paris = now_utc + _PARIS

    st.markdown(f"""
        <div style="margin-bottom:20px;">
            <div style="font-size:22px;font-weight:800;color:{_TEXT};letter-spacing:-0.5px;">
                📓 Journal de Trading Personnel
            </div>
            <div style="color:{_MUTED};font-size:13px;margin-top:4px;">
                Enregistre tes trades · Analyse ta performance · Coach IA
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ── Cours live + graphique Gold (colonne droite partagée entre les deux tabs) ─
    col_main, col_side = st.columns([3, 2])

    with col_side:
        # Cours live + graphique
        @st.fragment(run_every=10)
        def _gold_widget():
            import yfinance as yf
            import plotly.graph_objects as go

            tf_opts = {"5min": ("5m", "1d"), "15min": ("15m", "5d"), "1H": ("1h", "30d"), "4H": ("4h", "60d")}
            tf_sel = st.radio("Timeframe", list(tf_opts.keys()), horizontal=True, index=1, key="j_tf")
            interval, period = tf_opts[tf_sel]

            try:
                ticker = yf.Ticker("GC=F")

                # Prix live via fast_info (moins de délai que history)
                try:
                    fi = ticker.fast_info
                    price = float(fi.last_price)
                    prev  = float(fi.previous_close) if hasattr(fi, "previous_close") else price
                except Exception:
                    price = prev = 0.0

                # Historique pour le graphique
                df = ticker.history(period=period, interval=interval, auto_adjust=True)
                if hasattr(df.columns, "levels"):
                    df.columns = df.columns.get_level_values(0)
                df = df.dropna()
                if df.empty:
                    st.warning("Données Gold indisponibles.")
                    return

                # Si fast_info n'a pas donné de prix, fallback sur la dernière bougie
                if price == 0.0:
                    price = float(df["Close"].iloc[-1])
                    prev  = float(df["Close"].iloc[-2]) if len(df) > 1 else price

                chg     = price - prev
                chg_pct = chg / prev * 100 if prev else 0
                chg_col = _GREEN if chg >= 0 else _RED
                arrow   = "▲" if chg >= 0 else "▼"
                now_paris = datetime.now(timezone.utc) + _PARIS

                st.markdown(f"""
                <div style="background:{_CARD};border:1px solid {_GRID};border-radius:12px;
                padding:12px 16px;margin-bottom:10px;">
                    <div style="display:flex;align-items:center;gap:16px;">
                        <div>
                            <div style="font-size:10px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;">Gold XAU/USD</div>
                            <div style="font-size:26px;font-weight:900;color:{_GOLD};font-variant-numeric:tabular-nums;">${price:,.2f}</div>
                        </div>
                        <div style="margin-left:auto;text-align:right;">
                            <div style="font-size:16px;font-weight:700;color:{chg_col};">{arrow} {abs(chg):.2f}</div>
                            <div style="font-size:13px;color:{chg_col};">{chg_pct:+.2f}%</div>
                        </div>
                        <div style="background:rgba(244,63,94,0.12);color:#f43f5e;font-size:9px;font-weight:700;
                        padding:2px 8px;border-radius:20px;align-self:flex-start;">● LIVE</div>
                    </div>
                    <div style="margin-top:6px;font-size:9px;color:{_MUTED};">
                        Mis à jour à {now_paris.strftime("%H:%M:%S")} FR · Bougies ~15min de délai (source yfinance)
                    </div>
                </div>
                """, unsafe_allow_html=True)

                keep = min(120, len(df))
                df_plot = df.tail(keep).copy()
                try:
                    if df_plot.index.tz is not None:
                        df_plot.index = df_plot.index.tz_convert("Europe/Paris")
                    else:
                        df_plot.index = df_plot.index.tz_localize("UTC").tz_convert("Europe/Paris")
                except Exception:
                    pass

                df_plot["EMA20"] = df_plot["Close"].ewm(span=20).mean()

                fig = go.Figure(data=[go.Candlestick(
                    x=df_plot.index,
                    open=df_plot["Open"], high=df_plot["High"],
                    low=df_plot["Low"],   close=df_plot["Close"],
                    increasing_line_color=_GREEN, decreasing_line_color=_RED,
                    increasing_fillcolor=_GREEN,  decreasing_fillcolor=_RED,
                    line=dict(width=1),
                )])
                fig.add_trace(go.Scatter(
                    x=df_plot.index, y=df_plot["EMA20"],
                    mode="lines", name="EMA20",
                    line=dict(color=_BLUE, width=1.2, dash="dot"),
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#080c14",
                    margin=dict(l=0, r=0, t=8, b=0), height=270,
                    xaxis=dict(showgrid=True, gridcolor="#1a2235", rangeslider=dict(visible=False),
                               color="#64748b", tickfont=dict(size=10)),
                    yaxis=dict(showgrid=True, gridcolor="#1a2235", color="#64748b",
                               tickfont=dict(size=10), side="right"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                                font=dict(size=10, color="#64748b"), bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            except Exception as exc:
                st.warning(f"Graphique indisponible : {exc}")

        _gold_widget()

        # Signal swing
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};'
            f'letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Tendance Gold (Swing)</div>',
            unsafe_allow_html=True
        )

        @st.fragment(run_every=300)
        def _swing_widget():
            sig   = _get_swing_trend()
            trend = sig["trend"]
            price = sig["price"]
            rsi   = sig["rsi"]
            action = sig["action"]
            conf   = sig["confidence"]
            tc = _GREEN if trend == "HAUSSIER" else _RED if trend == "BAISSIER" else _MUTED
            ta = "▲" if trend == "HAUSSIER" else "▼" if trend == "BAISSIER" else "—"
            tbg = "rgba(16,185,129,0.08)" if trend == "HAUSSIER" else "rgba(244,63,94,0.07)" if trend == "BAISSIER" else _CARD
            ac = _GREEN if action == "BUY" else _RED if action == "SELL" else _MUTED
            st.markdown(f"""
            <div style="background:{tbg};border:1px solid {tc}33;border-radius:12px;padding:14px 16px;">
                <div style="display:flex;align-items:center;gap:14px;">
                    <div>
                        <div style="font-size:10px;color:{_MUTED};">Tendance Daily</div>
                        <div style="font-size:20px;font-weight:900;color:{tc};">{ta} {trend}</div>
                    </div>
                    <div style="margin-left:auto;text-align:right;">
                        <div style="font-size:10px;color:{_MUTED};">Signal 4H</div>
                        <div style="font-size:17px;font-weight:800;color:{ac};">{action}</div>
                        <div style="font-size:10px;color:{_MUTED};">{conf:.0%}</div>
                    </div>
                </div>
                <div style="display:flex;gap:20px;margin-top:8px;padding-top:8px;border-top:1px solid {_GRID};">
                    <div><div style="font-size:9px;color:{_MUTED};">Prix Gold</div>
                    <div style="font-size:13px;font-weight:700;color:{_GOLD};">${price:,.2f}</div></div>
                    <div><div style="font-size:9px;color:{_MUTED};">RSI 4H</div>
                    <div style="font-size:13px;font-weight:700;color:{_TEXT};">{rsi}</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        _swing_widget()

    with col_main:
        # Onglets : Entraînement / Fond Propre
        tab_paper, tab_real = st.tabs(["🎯  Entraînement (Paper)", "💰  Fond Propre"])

        with tab_paper:
            _trade_section("paper", "d'entraînement")

        with tab_real:
            _trade_section("real", "réel")

    # ── Calendrier économique ─────────────────────────────────────────────────
    st.markdown(f'<hr style="border:none;border-top:1px solid {_GRID};margin:24px 0 16px;">', unsafe_allow_html=True)

    @st.fragment(run_every=60)
    def _calendar_widget():
        now_utc   = datetime.now(timezone.utc)
        now_paris = now_utc + _PARIS
        now_str   = now_utc.strftime("%Y-%m-%dT%H:%M")

        # Re-fetch Forex Factory toutes les 30 minutes
        _last = st.session_state.get("_cal_last_fetch", 0)
        if now_utc.timestamp() - _last > 1800:
            try:
                from data.economic_calendar import fetch_upcoming_events
                fetch_upcoming_events()
                st.session_state["_cal_last_fetch"] = now_utc.timestamp()
            except Exception:
                pass

        _last_fetch = st.session_state.get("_cal_last_fetch", 0)
        _mins_ago = int((now_utc.timestamp() - _last_fetch) / 60) if _last_fetch else None
        _fetch_str = f"mis à jour il y a {_mins_ago} min" if _mins_ago is not None else "en attente"

        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{_MUTED};letter-spacing:1px;'
            f'text-transform:uppercase;margin-bottom:8px;">'
            f'Calendrier économique — {now_paris.strftime("%d %b %Y")} '
            f'<span style="font-weight:400;text-transform:none;font-size:10px;color:{_MUTED};">'
            f'🇫🇷 heure française (UTC+2) · {_fetch_str})</span></div>',
            unsafe_allow_html=True
        )

        events = sorted(_load_events(), key=lambda e: e.get("ts", ""))
        today  = now_utc.strftime("%Y-%m-%d")
        events = [e for e in events if e.get("ts", "").startswith(today)]

        if not events:
            st.info("Aucun événement aujourd'hui.")
            return

        now_line_shown = False
        cal_rows = []

        for e in events:
            imp      = e.get("importance", 1)
            ts       = e.get("ts", "")
            is_past  = ts < now_str
            actual   = e.get("actual")
            forecast = e.get("forecast")
            previous = e.get("previous")
            reaction = e.get("gold_reaction")

            try:
                from datetime import datetime as _dt
                time_str = (_dt.strptime(ts[:16], "%Y-%m-%dT%H:%M") + _PARIS).strftime("%H:%M")
            except Exception:
                time_str = ts[11:16] if len(ts) > 11 else "—"

            border = "#E24B4A" if imp == 3 else "#EF9F27" if imp == 2 else _GRID
            bg     = ("rgba(244,63,94,0.04)" if imp == 3 else "rgba(245,158,11,0.04)" if imp == 2 else _CARD) if is_past else \
                     ("rgba(244,63,94,0.08)" if imp == 3 else "rgba(245,158,11,0.08)" if imp == 2 else _CARD)
            opacity    = "opacity:0.55;" if is_past else ""
            stars      = "★" * imp + "☆" * (3 - imp)
            stars_color = "#E24B4A" if imp == 3 else "#EF9F27" if imp == 2 else _MUTED

            actual_str   = str(actual)   if actual   is not None else "—"
            forecast_str = str(forecast) if forecast is not None else "—"
            prev_str     = str(previous) if previous is not None else "—"
            actual_color = (_GREEN if reaction == "buy" else _RED) if (actual is not None and reaction) else _MUTED

            if is_past and actual is not None and forecast is not None and reaction:
                impact = "▲ GOLD UP" if reaction == "buy" else "▼ GOLD DOWN"
                ic = _GREEN if reaction == "buy" else _RED
                ibg = "rgba(16,185,129,0.15)" if reaction == "buy" else "rgba(244,63,94,0.15)"
                reaction_cell = f'<span style="background:{ibg};color:{ic};padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">{impact}</span>'
            elif not is_past:
                if reaction == "buy":
                    reaction_cell = f'<span style="background:rgba(16,185,129,0.1);color:{_GREEN};padding:2px 8px;border-radius:10px;font-size:10px;">▲ probable</span>'
                elif reaction == "sell":
                    reaction_cell = f'<span style="background:rgba(244,63,94,0.1);color:{_RED};padding:2px 8px;border-radius:10px;font-size:10px;">▼ probable</span>'
                else:
                    reaction_cell = f'<span style="color:{_MUTED};font-size:10px;">En attente</span>'
            else:
                reaction_cell = f'<span style="color:{_MUTED};font-size:10px;">—</span>'

            if not now_line_shown and not is_past:
                now_line_shown = True
                cal_rows.append(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0;">'
                    f'<span style="font-size:10px;color:{_BLUE};font-weight:700;white-space:nowrap;">'
                    f'▶ MAINTENANT — {now_paris.strftime("%H:%M")}</span>'
                    f'<div style="flex:1;border-top:1.5px dashed rgba(59,130,246,0.4);"></div></div>'
                )

            cal_rows.append(
                f'<div style="{opacity}background:{bg};border-left:3px solid {border};'
                f'border-radius:0 8px 8px 0;padding:8px 12px;'
                f'display:grid;grid-template-columns:48px 20px 1fr 62px 62px 70px 110px;'
                f'gap:8px;align-items:center;margin-bottom:3px;">'
                f'<span style="font-size:11px;color:{_TEXT};font-variant-numeric:tabular-nums;font-weight:700;">{time_str}<span style="font-size:9px;color:{_MUTED};font-weight:400;margin-left:2px;">FR</span></span>'
                f'<span style="font-size:10px;color:{stars_color};">{stars}</span>'
                f'<span style="font-size:12px;font-weight:600;color:{_TEXT};">{e["name"]}</span>'
                f'<span style="font-size:11px;color:{_MUTED};text-align:right;">Préc.&nbsp;{prev_str}</span>'
                f'<span style="font-size:11px;color:{_MUTED};text-align:right;">Prévu&nbsp;{forecast_str}</span>'
                f'<span style="font-size:11px;color:{actual_color};font-weight:600;text-align:right;">Actuel&nbsp;{actual_str}</span>'
                f'<span style="text-align:right;">{reaction_cell}</span></div>'
            )

        st.markdown(f'<div style="display:flex;flex-direction:column;">{"".join(cal_rows)}</div>',
                    unsafe_allow_html=True)

    _calendar_widget()
