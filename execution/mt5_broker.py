"""
Adaptateur MetaTrader 5 — DEMO uniquement.

Garde-fous :
- Vérifie que le compte est DEMO avant tout ordre
- Refuse tout compte REAL
- XAUUSD uniquement (extensible)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    _MT5_AVAILABLE = False
    logger.warning("[MT5] MetaTrader5 non installé — mode simulation activé")


@dataclass
class MT5OrderResult:
    order_id: int
    ticker: str
    side: str
    qty: float
    price: float
    status: str
    comment: str
    demo: bool = True


class MT5DemoBroker:
    """
    Broker MetaTrader 5 en mode DEMO uniquement.
    Refuse de fonctionner sur un compte REAL.
    """

    SUPPORTED_TICKERS = {"XAUUSD"}

    def __init__(self, login: int | None = None, password: str | None = None,
                 server: str | None = None) -> None:
        self._connected = False
        self._login = login
        self._password = password
        self._server = server
        self._sim_mode = not _MT5_AVAILABLE
        self._sim_price: dict[str, float] = {}
        self._sim_positions: dict[str, dict] = {}
        self._sim_cash = 10_000.0

        if not self._sim_mode:
            self._connect()

    # ── Connexion ─────────────────────────────────────────────────────────────

    _TERMINAL_PATH = r"C:\Program Files\Vantage Markets MT5 Terminal\terminal64.exe"

    def _connect(self) -> bool:
        import os
        path = self._TERMINAL_PATH if os.path.exists(self._TERMINAL_PATH) else None
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            logger.warning(f"[MT5] Terminal non disponible ({mt5.last_error()}) — mode simulation")
            self._sim_mode = True
            return False

        if self._login and self._password and self._server:
            ok = mt5.login(self._login, password=self._password, server=self._server)
            if not ok:
                logger.error(f"[MT5] Connexion échouée : {mt5.last_error()}")
                self._sim_mode = True
                return False

        info = mt5.account_info()
        if info is None:
            logger.warning("[MT5] Aucun compte connecté — mode simulation")
            self._sim_mode = True
            return False

        # GARDE-FOU CRITIQUE — refuse tout compte réel
        if info.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            mt5.shutdown()
            raise EnvironmentError(
                f"[MT5] REFUS — compte '{info.name}' est un compte RÉEL. "
                "Seuls les comptes DEMO sont autorisés."
            )

        self._connected = True
        logger.success(
            f"[MT5] Connecté — DEMO | {info.name} | "
            f"Balance: {info.balance:.2f} {info.currency} | Broker: {info.company}"
        )
        return True

    def is_connected(self) -> bool:
        if self._sim_mode:
            return True
        return self._connected and mt5.terminal_info() is not None

    def get_account(self) -> dict:
        if self._sim_mode:
            return {"balance": self._sim_cash, "currency": "USD", "demo": True}
        info = mt5.account_info()
        if info is None:
            return {"balance": 0.0, "currency": "USD", "demo": True}
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin_free": info.margin_free,
            "currency": info.currency,
            "demo": info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
        }

    # ── Prix ──────────────────────────────────────────────────────────────────

    def get_price(self, ticker: str) -> float | None:
        if self._sim_mode:
            if ticker in self._sim_price:
                return self._sim_price[ticker]
            # Fallback yfinance GC=F
            try:
                import yfinance as yf
                import pandas as pd
                df = yf.download("GC=F", period="1d", interval="1m",
                                 progress=False, auto_adjust=False, threads=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                p = float(df["Close"].dropna().iloc[-1])
                self._sim_price[ticker] = p
                return p
            except Exception:
                return None

        tick = mt5.symbol_info_tick(ticker)
        if tick is None:
            return None
        return (tick.bid + tick.ask) / 2

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None:
        if self._sim_mode:
            p = self.get_price(ticker)
            if p is None:
                return None
            spread = p * 0.0002  # ~20 pips simulés
            return p - spread / 2, p + spread / 2
        tick = mt5.symbol_info_tick(ticker)
        if tick is None:
            return None
        return tick.bid, tick.ask

    # ── Positions ─────────────────────────────────────────────────────────────

    def get_positions(self, ticker: str | None = None) -> list[dict]:
        if self._sim_mode:
            if ticker:
                p = self._sim_positions.get(ticker)
                return [p] if p else []
            return list(self._sim_positions.values())

        positions = mt5.positions_get(symbol=ticker) if ticker else mt5.positions_get()
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket,
                "ticker": p.symbol,
                "side": "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell",
                "qty": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "pnl": p.profit,
                "sl": p.sl,
                "tp": p.tp,
            }
            for p in positions
        ]

    # ── Ordres ────────────────────────────────────────────────────────────────

    def submit_market_order(self, ticker: str, side: str, qty: float,
                            sl_pct: float = 0.005, tp_pct: float = 0.015,
                            comment: str = "NexoraAgent") -> MT5OrderResult:
        """
        Soumet un ordre marché BUY ou SELL sur ticker (DEMO uniquement).

        Args:
            ticker: Symbole MT5 (ex: "XAUUSD")
            side: "buy" ou "sell"
            qty: Volume en lots (0.01 = 1 micro-lot gold = 1 oz)
            sl_pct: Stop-loss en % du prix (défaut 0.5%)
            tp_pct: Take-profit en % du prix (défaut 1.5%)
        """
        if ticker not in self.SUPPORTED_TICKERS:
            raise ValueError(f"[MT5] Ticker non supporté : {ticker}. Autorisés : {self.SUPPORTED_TICKERS}")

        price = self.get_price(ticker)
        if price is None:
            raise RuntimeError(f"[MT5] Prix indisponible pour {ticker}")

        if self._sim_mode:
            return self._sim_order(ticker, side, qty, price, sl_pct, tp_pct, comment)

        return self._live_demo_order(ticker, side, qty, price, sl_pct, tp_pct, comment)

    def _sim_order(self, ticker: str, side: str, qty: float, price: float,
                   sl_pct: float, tp_pct: float, comment: str) -> MT5OrderResult:
        sl = price * (1 - sl_pct) if side == "buy" else price * (1 + sl_pct)
        tp = price * (1 + tp_pct) if side == "buy" else price * (1 - tp_pct)

        self._sim_positions[ticker] = {
            "ticker": ticker, "side": side, "qty": qty,
            "open_price": price, "sl": sl, "tp": tp,
        }
        logger.info(f"[MT5-SIM] {side.upper()} {qty} {ticker} @ {price:.2f} | SL={sl:.2f} TP={tp:.2f}")
        return MT5OrderResult(
            order_id=int(time.time()),
            ticker=ticker, side=side, qty=qty, price=price,
            status="filled", comment=comment, demo=True,
        )

    def _live_demo_order(self, ticker: str, side: str, qty: float, price: float,
                         sl_pct: float, tp_pct: float, comment: str) -> MT5OrderResult:
        ba = self.get_bid_ask(ticker)
        exec_price = ba[1] if side == "buy" else ba[0]  # ask pour buy, bid pour sell

        sl = exec_price * (1 - sl_pct) if side == "buy" else exec_price * (1 + sl_pct)
        tp = exec_price * (1 + tp_pct) if side == "buy" else exec_price * (1 - tp_pct)

        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        filling = mt5.symbol_info(ticker).filling_mode

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": ticker,
            "volume": float(qty),
            "type": order_type,
            "price": exec_price,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "deviation": 20,
            "magic": 20260701,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = mt5.last_error() if result is None else result.comment
            raise RuntimeError(f"[MT5] Ordre refusé : {err}")

        logger.success(
            f"[MT5-DEMO] {side.upper()} {qty} {ticker} @ {result.price:.2f} "
            f"| SL={sl:.2f} TP={tp:.2f} | ticket={result.order}"
        )
        return MT5OrderResult(
            order_id=result.order,
            ticker=ticker, side=side, qty=qty, price=result.price,
            status="filled", comment=comment, demo=True,
        )

    def close_position(self, ticker: str) -> MT5OrderResult | None:
        positions = self.get_positions(ticker)
        if not positions:
            logger.warning(f"[MT5] Aucune position ouverte sur {ticker}")
            return None

        pos = positions[0]
        close_side = "sell" if pos["side"] == "buy" else "buy"
        return self.submit_market_order(ticker, close_side, pos["qty"],
                                        sl_pct=0, tp_pct=0, comment="ManualClose")

    def shutdown(self) -> None:
        if not self._sim_mode and _MT5_AVAILABLE:
            mt5.shutdown()
            logger.info("[MT5] Déconnecté.")
