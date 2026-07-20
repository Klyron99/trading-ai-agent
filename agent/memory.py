"""
Mémoire persistante de l'agent via SQLite.
Stocke les décisions, signaux, performances de stratégie et historique des modèles.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# Chemin calculé directement pour éviter les imports circulaires au hot-reload
_MEMORY_DIR = Path(__file__).resolve().parent / "memory_store"
_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _MEMORY_DIR / "agent_memory.db"


@contextmanager
def _conn():
    con = sqlite3.connect(_DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                ticker      TEXT NOT NULL,
                action      TEXT NOT NULL,   -- BUY / SELL / HOLD
                confidence  REAL NOT NULL,
                strategy    TEXT NOT NULL,
                price       REAL,
                ml_prob     REAL,
                reason      TEXT
            );

            CREATE TABLE IF NOT EXISTS strategy_performance (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                strategy        TEXT NOT NULL,
                sharpe          REAL,
                perf_pct        REAL,
                drawdown_pct    REAL,
                win_rate_pct    REAL,
                n_trades        INTEGER,
                score           REAL
            );

            CREATE TABLE IF NOT EXISTS model_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                model_type      TEXT NOT NULL,
                accuracy        REAL,
                replaced        INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                cash            REAL NOT NULL,
                positions_value REAL NOT NULL,
                total_value     REAL NOT NULL,
                action          TEXT
            );

            CREATE TABLE IF NOT EXISTS broker_state (
                ticker      TEXT PRIMARY KEY,
                cash        REAL NOT NULL,
                positions   TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_outcomes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT NOT NULL,
                entry_ts     TEXT NOT NULL,
                exit_ts      TEXT,
                entry_price  REAL NOT NULL,
                exit_price   REAL,
                side         TEXT NOT NULL,
                ml_prob      REAL,
                pnl_pct      REAL,
                win          INTEGER,
                features_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_ticker_ts
                ON decisions(ticker, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_portfolio_ticker_ts
                ON portfolio_snapshots(ticker, ts ASC);
            CREATE INDEX IF NOT EXISTS idx_strategy_ticker_ts
                ON strategy_performance(ticker, ts DESC);
        """)
    logger.debug(f"[Memory] DB initialisée : {_DB_PATH}")


def log_decision(
    ticker: str,
    action: str,
    confidence: float,
    strategy: str,
    price: float | None = None,
    ml_prob: float | None = None,
    reason: str = "",
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO decisions (ts, ticker, action, confidence, strategy, price, ml_prob, reason)
               VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), ticker, action, confidence, strategy, price, ml_prob, reason),
        )


def log_strategy_performance(
    ticker: str,
    strategy: str,
    sharpe: float,
    perf_pct: float,
    drawdown_pct: float,
    win_rate_pct: float,
    n_trades: int,
    score: float,
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO strategy_performance
               (ts, ticker, strategy, sharpe, perf_pct, drawdown_pct, win_rate_pct, n_trades, score)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(), ticker, strategy,
                sharpe, perf_pct, drawdown_pct, win_rate_pct, n_trades, score,
            ),
        )


def log_model(ticker: str, model_type: str, accuracy: float, replaced: bool = False) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO model_history (ts, ticker, model_type, accuracy, replaced)
               VALUES (?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), ticker, model_type, accuracy, int(replaced)),
        )


def clear_decisions(ticker: str) -> int:
    """Supprime toutes les décisions pour un ticker. Retourne le nombre de lignes supprimées."""
    with _conn() as con:
        cur = con.execute("DELETE FROM decisions WHERE ticker=?", (ticker,))
        return cur.rowcount


def get_recent_decisions(ticker: str, limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM decisions WHERE ticker=? ORDER BY ts DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_best_strategy(ticker: str) -> str | None:
    """Retourne la stratégie avec le meilleur score parmi la dernière session de backtest."""
    with _conn() as con:
        # Trouve le timestamp de la dernière session (toutes les strats sont évaluées ensemble)
        last_ts = con.execute(
            "SELECT ts FROM strategy_performance WHERE ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not last_ts:
            return None
        # Prend la meilleure stratégie parmi toutes celles évaluées à cette même session (~5s)
        row = con.execute(
            """SELECT strategy FROM strategy_performance
               WHERE ticker=?
                 AND ts >= datetime(?, '-10 seconds')
               ORDER BY score DESC
               LIMIT 1""",
            (ticker, last_ts["ts"]),
        ).fetchone()
    return row["strategy"] if row else None


def get_strategy_comparison(ticker: str) -> list[dict[str, Any]]:
    """Retourne la dernière évaluation de chaque stratégie pour ce ticker."""
    with _conn() as con:
        rows = con.execute(
            """SELECT strategy, sharpe, perf_pct, drawdown_pct, win_rate_pct, n_trades, score, ts
               FROM strategy_performance
               WHERE ticker=?
               GROUP BY strategy
               HAVING ts = MAX(ts)
               ORDER BY score DESC""",
            (ticker,),
        ).fetchall()
    return [dict(r) for r in rows]


def log_portfolio_snapshot(
    ticker: str,
    cash: float,
    positions_value: float,
    action: str = "",
) -> None:
    total = cash + positions_value
    with _conn() as con:
        con.execute(
            """INSERT INTO portfolio_snapshots (ts, ticker, cash, positions_value, total_value, action)
               VALUES (?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), ticker, cash, positions_value, total, action),
        )


def get_portfolio_history(ticker: str, limit: int = 500) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            """SELECT ts, cash, positions_value, total_value, action
               FROM portfolio_snapshots WHERE ticker=?
               ORDER BY ts ASC LIMIT ?""",
            (ticker, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_model(ticker: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM model_history WHERE ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    return dict(row) if row else None


def get_model_version(ticker: str) -> int:
    """Retourne le nombre total de réentraînements pour ce ticker."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM model_history WHERE ticker=?", (ticker,)
        ).fetchone()
    return row[0] if row else 0


def save_broker_state(ticker: str, cash: float, positions: dict,
                      short_positions: dict | None = None) -> None:
    """Persiste le solde, positions longues et shorts du broker en DB."""
    import json
    with _conn() as con:
        con.execute(
            """INSERT INTO broker_state (ticker, cash, positions, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET
                   cash=excluded.cash,
                   positions=excluded.positions,
                   updated_at=excluded.updated_at""",
            (
                ticker, cash,
                json.dumps({"long": positions, "short": short_positions or {}}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def load_broker_state(ticker: str) -> dict | None:
    """Charge le dernier état connu du broker pour ce ticker."""
    import json
    with _conn() as con:
        row = con.execute(
            "SELECT cash, positions FROM broker_state WHERE ticker=?", (ticker,)
        ).fetchone()
    if not row:
        return None
    raw = json.loads(row["positions"])
    # Rétrocompatibilité : ancien format {"ticker": {...}} sans clés "long"/"short"
    if "long" in raw:
        return {"cash": row["cash"], "positions": raw["long"], "short_positions": raw["short"]}
    return {"cash": row["cash"], "positions": raw, "short_positions": {}}


def log_trade_entry(ticker: str, entry_price: float, side: str,
                    ml_prob: float | None = None, features_json: str | None = None) -> int:
    """Enregistre l'entrée en position. Retourne l'id du trade."""
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO trade_outcomes (ticker, entry_ts, entry_price, side, ml_prob, features_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticker, datetime.now(timezone.utc).isoformat(),
             entry_price, side, ml_prob, features_json),
        )
        return cur.lastrowid


def log_trade_exit(trade_id: int, exit_price: float) -> None:
    """Enregistre la sortie de position et calcule P&L."""
    with _conn() as con:
        row = con.execute(
            "SELECT entry_price, side FROM trade_outcomes WHERE id=?", (trade_id,)
        ).fetchone()
        if not row:
            return
        entry_price, side = row["entry_price"], row["side"]
        if side == "long":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        win = 1 if pnl_pct > 0 else 0
        con.execute(
            """UPDATE trade_outcomes SET exit_ts=?, exit_price=?, pnl_pct=?, win=?
               WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), exit_price, pnl_pct, win, trade_id),
        )


def get_trade_outcomes(ticker: str, limit: int = 200) -> list[dict]:
    """Retourne les trades complétés pour analyse et auto-amélioration."""
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM trade_outcomes
               WHERE ticker=? AND exit_price IS NOT NULL
               ORDER BY entry_ts DESC LIMIT ?""",
            (ticker, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_win_rate(ticker: str, last_n: int = 50) -> float | None:
    """Win rate réel sur les N derniers trades complétés."""
    outcomes = get_trade_outcomes(ticker, limit=last_n)
    if not outcomes:
        return None
    return sum(1 for t in outcomes if t["win"]) / len(outcomes)
