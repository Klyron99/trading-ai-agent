"""
Broker Alpaca Paper Trading.

Ce module communique exclusivement avec l'API Alpaca Paper Trading.
AUCUN ORDRE RÉEL N'EST JAMAIS ENVOYÉ PAR CE MODULE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger

from config.settings import (
    ALPACA_API_KEY,
    ALPACA_BASE_URL,
    ALPACA_PAPER_URL,
    ALPACA_SECRET_KEY,
    LIVE_TRADING,
)


def _assert_paper_environment() -> None:
    """Bloque tout environnement qui ne correspond pas au paper trading."""
    if LIVE_TRADING:
        raise EnvironmentError(
            "LIVE_TRADING=true détecté. Ce bot est conçu pour le PAPER TRADING uniquement."
        )

    normalized_url = ALPACA_BASE_URL.rstrip("/").lower()
    if "paper-api.alpaca.markets" not in normalized_url:
        raise EnvironmentError(
            f"URL Alpaca non autorisée : '{ALPACA_BASE_URL}'. "
            f"Seule l'URL paper trading est acceptée : '{ALPACA_PAPER_URL}'."
        )


@dataclass
class AlpacaAccountInfo:
    portfolio_value: float
    cash: float
    buying_power: float
    currency: str = "USD"


@dataclass
class AlpacaOrderResult:
    order_id: str
    ticker: str
    side: str
    qty: float
    status: str
    submitted_at: datetime
    simulated: bool = False


class AlpacaPaperBroker:
    """Interface sécurisée vers Alpaca Paper Trading ou simulation locale."""

    def __init__(self, simulation_capital: float = 100_000.0, persist: bool = True) -> None:
        _assert_paper_environment()

        self._simulation_mode: bool = not (ALPACA_API_KEY and ALPACA_SECRET_KEY)
        self._trading_client = None
        self._data_client = None

        self._persist: bool = persist
        self._sim_cash: float = simulation_capital
        self._sim_positions: dict[str, dict] = {}        # long positions
        self._sim_short_positions: dict[str, dict] = {}  # short positions
        self._sim_orders: list[AlpacaOrderResult] = []
        self._sim_order_counter: int = 0
        self._last_sim_price: dict[str, float] = {}
        self._initial_capital: float = simulation_capital

        if self._simulation_mode:
            logger.warning(
                "[AlpacaPaperBroker] Clés API absentes ou vides. "
                "Démarrage en MODE SIMULATION LOCALE."
            )
        else:
            self._init_alpaca_clients()

    def _init_alpaca_clients(self) -> None:
        """Initialise les clients Alpaca."""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient
        except ImportError as exc:
            raise ImportError(
                "Le package 'alpaca-py' est requis. Installez-le avec : pip install alpaca-py"
            ) from exc

        self._trading_client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=True,
        )
        self._data_client = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
        )
        logger.info(f"[AlpacaPaperBroker] Connecté à Alpaca Paper : {ALPACA_BASE_URL}")

    def get_account(self) -> AlpacaAccountInfo:
        """Retourne les informations du compte."""
        if self._simulation_mode:
            sim_positions_value = 0.0

            for ticker, pos in self._sim_positions.items():
                last_price = self._last_sim_price.get(ticker, pos["avg_price"])
                sim_positions_value += pos["qty"] * last_price

            total = self._sim_cash + sim_positions_value

            return AlpacaAccountInfo(
                portfolio_value=total,
                cash=self._sim_cash,
                buying_power=self._sim_cash,
            )

        account = self._trading_client.get_account()
        return AlpacaAccountInfo(
            portfolio_value=float(account.portfolio_value),
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            currency=account.currency,
        )

    def get_latest_price(self, ticker: str) -> float:
        """Récupère le dernier prix disponible."""
        if self._simulation_mode:
            return self._sim_get_price(ticker)

        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quote = self._data_client.get_stock_latest_quote(req)

            raw_price = quote[ticker].ask_price or quote[ticker].bid_price
            if raw_price is None:
                raise ValueError(f"Aucun bid/ask disponible pour {ticker}")

            price = float(raw_price)
            logger.debug(f"[Alpaca] Prix {ticker} : {price:.2f} $")
            return price

        except Exception as exc:
            raise RuntimeError(f"Impossible de récupérer le prix de {ticker} : {exc}") from exc

    def _sim_get_price(self, ticker: str) -> float:
        """Récupère le prix via yfinance en mode simulation locale."""
        try:
            import yfinance as yf

            data = yf.download(
                ticker,
                period="1d",
                interval="1m",
                prepost=True,
                progress=False,
                auto_adjust=False,
                group_by="column",
                threads=False,
            )

            if data is None or data.empty:
                raise ValueError("Pas de données yfinance.")

            close_data = data["Close"]

            # Cas normal : Series
            if hasattr(close_data, "dropna"):
                close_data = close_data.dropna()

            if close_data.empty:
                raise ValueError("Colonne Close vide.")

            last_close = close_data.iloc[-1]

            # Cas yfinance MultiIndex : last_close peut être une Series
            if hasattr(last_close, "iloc"):
                last_close = last_close.iloc[0]

            price = float(last_close)

            if price <= 0:
                raise ValueError(f"Prix invalide : {price}")

            self._last_sim_price[ticker] = price
            logger.debug(f"[Simulation] Prix {ticker} : {price:.2f} $")
            return price

        except Exception as exc:
            logger.error(f"[Simulation] Erreur yfinance pour {ticker} : {exc}")
            raise RuntimeError(f"Prix indisponible en simulation pour {ticker}.") from exc

    def get_portfolio_value(self, current_prices: dict | None = None) -> float:
        """Valeur totale du portefeuille (cash + longs - shorts à prix courant)."""
        if self._simulation_mode:
            total = self._sim_cash
            # Longs : valeur courante des positions achetées
            for t, pos in self._sim_positions.items():
                price = (current_prices or {}).get(t) or self._last_sim_price.get(t, pos.get("avg_price", 0))
                total += pos.get("qty", 0) * price
            # Shorts : le cash contient déjà les proceeds (avg_price * qty)
            # On soustrait ce qu'on doit racheter (current_price * qty)
            # Net = proceeds_in_cash - current_liability = (avg - current) * qty
            for t, pos in self._sim_short_positions.items():
                price = (current_prices or {}).get(t) or self._last_sim_price.get(t, pos.get("avg_price", 0))
                total -= price * pos["qty"]  # soustrait la valeur marchande courante de la dette
            return total
        try:
            acct = self.get_account()
            return acct.portfolio_value
        except Exception:
            return self._sim_cash

    def get_position(self, ticker: str) -> Optional[dict]:
        """Retourne la position longue ouverte sur un ticker, ou None."""
        if self._simulation_mode:
            return self._sim_positions.get(ticker)
        try:
            pos = self._trading_client.get_open_position(ticker)
            return {"qty": float(pos.qty), "avg_price": float(pos.avg_entry_price)}
        except Exception:
            return None

    def get_short_position(self, ticker: str) -> Optional[dict]:
        """Retourne la position short ouverte sur un ticker, ou None."""
        return self._sim_short_positions.get(ticker)

    def has_open_order(self, ticker: str) -> bool:
        """Vérifie si un ordre est déjà en attente."""
        if self._simulation_mode:
            return False

        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[ticker],
            )
            open_orders = self._trading_client.get_orders(req)
            return bool(open_orders)

        except Exception as exc:
            logger.error(f"[AlpacaPaperBroker] Erreur vérification ordres ouverts : {exc}")
            return True

    def submit_market_order(self, ticker: str, side: str, qty: float) -> AlpacaOrderResult:
        """Soumet un ordre market en paper trading ou simulation.

        side: "buy" (long ou cover short), "sell" (close long ou ouvrir short)
        """
        _assert_paper_environment()

        if qty <= 0:
            raise ValueError(f"Quantité invalide : {qty}")
        if side not in ("buy", "sell"):
            raise ValueError(f"Sens invalide : {side}")

        logger.info(f"[AlpacaPaperBroker] Ordre PAPER demandé : {side.upper()} {ticker} x{qty}")

        if self._simulation_mode:
            return self._sim_submit_order(ticker, side, qty)

        return self._alpaca_submit_order(ticker, side, qty)

    def _alpaca_submit_order(self, ticker: str, side: str, qty: float) -> AlpacaOrderResult:
        """Envoie l'ordre via l'API Alpaca Paper Trading."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

        req = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )

        order = self._trading_client.submit_order(req)

        result = AlpacaOrderResult(
            order_id=str(order.id),
            ticker=ticker,
            side=side,
            qty=qty,
            status=str(order.status),
            submitted_at=datetime.utcnow(),
            simulated=False,
        )

        logger.success(
            f"[AlpacaPaperBroker] Ordre PAPER accepté | "
            f"ID:{result.order_id} | {side.upper()} {ticker} x{qty}"
        )
        return result

    def _sim_submit_order(self, ticker: str, side: str, qty: float) -> AlpacaOrderResult:
        """Exécute un ordre localement en simulation.

        Logique complète long + short :
        - buy  + long ouvert  → renforce le long
        - buy  + short ouvert → couvre le short (rachat)
        - buy  + rien         → ouvre un long
        - sell + long ouvert  → ferme le long (prise de profit/stop)
        - sell + rien         → ouvre un short (emprunte l'actif)
        """
        price = self._last_sim_price.get(ticker) or self._sim_get_price(ticker)
        total = price * qty

        # Frais de transaction réalistes (appliqués des deux côtés — entrée ET sortie)
        _CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"}
        _fee_rate = 0.001 if ticker in _CRYPTO else 0.0003  # 0.10% crypto, 0.03% actions/ETF
        commission = round(total * _fee_rate, 4)

        self._sim_order_counter += 1
        order_id = f"SIM-{self._sim_order_counter:05d}"

        has_long  = bool(self._sim_positions.get(ticker))
        has_short = bool(self._sim_short_positions.get(ticker))

        if side == "buy":
            if has_short and not has_long:
                # ── Cover short (rachat pour fermer le short) ──────────────────
                short_pos = self._sim_short_positions[ticker]
                cover_qty = min(qty, short_pos["qty"])
                cost = price * cover_qty
                pnl = (short_pos["avg_price"] - price) * cover_qty - commission
                self._sim_cash -= cost + commission
                short_pos["qty"] -= cover_qty
                if short_pos["qty"] <= 1e-9:
                    del self._sim_short_positions[ticker]
                logger.info(
                    f"[PAPER COVER] {ticker} x{cover_qty:.6f} @ {price:.2f} "
                    f"| PnL short : {pnl:+.2f} $ | Frais : -{commission:.4f} $ | Cash : {self._sim_cash:.2f} $"
                )
            else:
                # ── Ouvre ou renforce un long ──────────────────────────────────
                if total > self._sim_cash:
                    raise ValueError(
                        f"[Simulation] Cash insuffisant : besoin {total:.2f} $, "
                        f"disponible {self._sim_cash:.2f} $."
                    )
                self._sim_cash -= total + commission
                if ticker in self._sim_positions:
                    pos = self._sim_positions[ticker]
                    new_qty = pos["qty"] + qty
                    pos["avg_price"] = (pos["qty"] * pos["avg_price"] + total) / new_qty
                    pos["qty"] = new_qty
                else:
                    self._sim_positions[ticker] = {"qty": qty, "avg_price": price}
                logger.info(
                    f"[PAPER BUY]  {ticker} x{qty:.6f} @ {price:.2f} "
                    f"| Frais : -{commission:.4f} $ | Cash restant : {self._sim_cash:.2f} $"
                )

        elif side == "sell":
            if has_long:
                # ── Ferme le long ──────────────────────────────────────────────
                pos = self._sim_positions[ticker]
                if pos["qty"] < qty - 1e-9:
                    raise ValueError(
                        f"[Simulation] Position longue insuffisante : {pos['qty']} < {qty}"
                    )
                pnl = (price - pos["avg_price"]) * qty - commission
                self._sim_cash += total - commission
                pos["qty"] -= qty
                if pos["qty"] <= 1e-9:
                    del self._sim_positions[ticker]
                logger.info(
                    f"[PAPER SELL] {ticker} x{qty:.6f} @ {price:.2f} "
                    f"| PnL : {pnl:+.2f} $ | Frais : -{commission:.4f} $ | Cash : {self._sim_cash:.2f} $"
                )
            else:
                # ── Ouvre un short (emprunte et vend à découvert) ──────────────
                # Les proceeds rentrent dans le cash (moins les frais)
                self._sim_cash += total - commission
                if ticker in self._sim_short_positions:
                    pos = self._sim_short_positions[ticker]
                    new_qty = pos["qty"] + qty
                    pos["avg_price"] = (pos["qty"] * pos["avg_price"] + total) / new_qty
                    pos["qty"] = new_qty
                else:
                    self._sim_short_positions[ticker] = {"qty": qty, "avg_price": price}
                logger.info(
                    f"[PAPER SHORT] {ticker} x{qty:.6f} @ {price:.2f} "
                    f"| Frais : -{commission:.4f} $ | Cash : {self._sim_cash:.2f} $ (proceeds inclus)"
                )

        result = AlpacaOrderResult(
            order_id=order_id,
            ticker=ticker,
            side=side,
            qty=qty,
            status="filled",
            submitted_at=datetime.utcnow(),
            simulated=True,
        )

        self._sim_orders.append(result)

        # Persiste l'état après chaque trade (seulement en production, pas en backtest/test)
        if self._persist:
            try:
                from agent.memory import save_broker_state
                save_broker_state(
                    ticker, self._sim_cash,
                    self._sim_positions,
                    self._sim_short_positions,
                )
            except Exception:
                pass

        logger.success(
            f"[Simulation] Ordre exécuté | ID:{order_id} | "
            f"{side.upper()} {ticker} x{qty} @ {price:.2f} $ | "
            f"Cash restant : {self._sim_cash:.2f} $"
        )

        return result

    def restore_state(self, ticker: str) -> bool:
        """Restaure le solde, positions longues et shorts depuis la DB."""
        try:
            from agent.memory import load_broker_state
            state = load_broker_state(ticker)
            if state:
                self._sim_cash = state["cash"]
                self._sim_positions = state.get("positions", {})
                self._sim_short_positions = state.get("short_positions", {})
                logger.info(
                    f"[AlpacaPaperBroker] État restauré — "
                    f"cash={self._sim_cash:.2f}$ longs={list(self._sim_positions.keys())} "
                    f"shorts={list(self._sim_short_positions.keys())}"
                )
                return True
        except Exception as e:
            logger.warning(f"[AlpacaPaperBroker] Impossible de restaurer l'état : {e}")
        return False

    def log_account_summary(self) -> None:
        """Affiche l'état actuel du compte."""
        try:
            info = self.get_account()
            mode = "SIMULATION" if self._simulation_mode else "ALPACA PAPER"

            logger.info(
                f"[{mode}] Compte — "
                f"Portefeuille : {info.portfolio_value:.2f} $ | "
                f"Cash : {info.cash:.2f} $ | "
                f"Buying power : {info.buying_power:.2f} $"
            )

        except Exception as exc:
            logger.error(f"Impossible de récupérer le compte : {exc}")