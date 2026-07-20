"""
Gestion du risque : valide chaque ordre avant exécution.
"""


from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from config.settings import MAX_POSITION_SIZE, RISK_PER_TRADE, STOP_LOSS_PCT


@dataclass
class OrderRequest:
    """Représente une demande d'ordre à valider.

    Attributes:
        ticker: Symbole boursier.
        side: "buy" ou "sell".
        price: Prix unitaire de l'action.
        quantity: Nombre d'actions souhaitées.
        portfolio_value: Valeur totale du portefeuille.
        cash: Cash disponible.
    """
    ticker: str
    side: str
    price: float
    quantity: float
    portfolio_value: float
    cash: float


class RiskManager:
    """Valide les ordres selon les règles de gestion du risque.

    Règles appliquées :
    - Risque max par trade : RISK_PER_TRADE % du capital.
    - Taille max d'une position : MAX_POSITION_SIZE % du portefeuille.
    - Stop loss simulé : STOP_LOSS_PCT % en dessous du prix d'achat.
    """

    def __init__(
        self,
        risk_per_trade: float = RISK_PER_TRADE,
        max_position_size: float = MAX_POSITION_SIZE,
        stop_loss_pct: float = STOP_LOSS_PCT,
    ) -> None:
        self.risk_per_trade = risk_per_trade
        self.max_position_size = max_position_size
        self.stop_loss_pct = stop_loss_pct

    def validate(self, order: OrderRequest) -> tuple[bool, str]:
        """Vérifie si un ordre respecte les règles de risque.

        Args:
            order: L'ordre à valider.

        Returns:
            (True, "") si l'ordre est valide, (False, raison) sinon.
        """
        if order.side == "buy":
            return self._validate_buy(order)
        if order.side in ("sell", "cover"):
            return True, ""
        if order.side == "short":
            return self._validate_short(order)
        return False, f"Sens d'ordre inconnu : {order.side}"

    def _validate_short(self, order: OrderRequest) -> tuple[bool, str]:
        """Mêmes règles que buy — taille et risque identiques."""
        order_value = order.price * order.quantity
        max_pos = order.portfolio_value * self.max_position_size
        if order_value > max_pos + 0.05:
            reason = (
                f"[{order.ticker}] Short trop grand : {order_value:.2f} $ "
                f"> limite {max_pos:.2f} $ ({self.max_position_size:.0%} du portefeuille)."
            )
            logger.warning(reason)
            return False, reason
        max_risk = order.portfolio_value * self.risk_per_trade
        potential_loss = order_value * self.stop_loss_pct
        if potential_loss > max_risk:
            reason = (
                f"[{order.ticker}] Risque short trop élevé : {potential_loss:.2f} $ "
                f"> limite {max_risk:.2f} $ ({self.risk_per_trade:.0%} du capital)."
            )
            logger.warning(reason)
            return False, reason
        return True, ""

    def _validate_buy(self, order: OrderRequest) -> tuple[bool, str]:
        order_value = order.price * order.quantity

        # 1. Vérification de la taille max de position (en premier — règle la plus large)
        max_position_value = order.portfolio_value * self.max_position_size
        if order_value > max_position_value + 0.05:  # tolérance 5 centimes (précision flottante)
            reason = (
                f"[{order.ticker}] Position trop grande : {order_value:.2f} € "
                f"> limite {max_position_value:.2f} € ({self.max_position_size:.0%} du portefeuille)."
            )
            logger.warning(reason)
            return False, reason

        # 2. Vérification du cash disponible
        if order_value > order.cash:
            reason = (
                f"[{order.ticker}] Cash insuffisant : besoin {order_value:.2f} €, "
                f"disponible {order.cash:.2f} €."
            )
            logger.warning(reason)
            return False, reason

        # 3. Vérification du risque max par trade
        max_risk_amount = order.portfolio_value * self.risk_per_trade
        potential_loss = order_value * self.stop_loss_pct
        if potential_loss > max_risk_amount:
            reason = (
                f"[{order.ticker}] Risque trop élevé : perte potentielle {potential_loss:.2f} € "
                f"> limite {max_risk_amount:.2f} € ({self.risk_per_trade:.0%} du capital)."
            )
            logger.warning(reason)
            return False, reason

        return True, ""

    def compute_position_size(self, price: float, portfolio_value: float,
                              available_cash: float | None = None) -> float:
        """Calcule la taille de position — supporte les fractions (crypto).

        Utilise MAX_POSITION_SIZE % du portefeuille, plafonné au cash disponible.
        """
        if price <= 0:
            return 0.0
        max_invest = portfolio_value * self.max_position_size
        if available_cash is not None:
            max_invest = min(max_invest, available_cash)
        qty = max_invest / price
        return round(max(qty, 0.0), 6)

    def check_stop_loss(self, entry_price: float, current_price: float) -> bool:
        """Vérifie si le stop loss est déclenché.

        Args:
            entry_price: Prix d'achat initial.
            current_price: Prix actuel.

        Returns:
            True si le stop loss est atteint.
        """
        return current_price <= entry_price * (1 - self.stop_loss_pct)
