"""
Gold Swing Strategy — Multi-Timeframe Trend Following

Logique :
  1. Tendance Daily   : EMA20 > EMA50 > EMA200 → haussier
                        EMA20 < EMA50 < EMA200 → baissier
  2. Entrée 4H        : Pullback vers EMA20 (price dans ±0.8%)
                        + RSI(14) entre 35-55 pour BUY, 45-65 pour SELL
                        + Bougie de confirmation (close > open pour BUY)
  3. Stop / TP ATR    : SL = 1.5 × ATR14(4H) / TP = 2.5 × ATR14(4H)
                        Risk/Reward minimum 1:1.5

Données : yfinance (GC=F gold futures) — pas besoin de MT5 connecté
Fréquence : vérification toutes les 4H
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

TICKER_YF = "GC=F"   # Gold Futures (proxy XAUUSD)


@dataclass
class SwingSignal:
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    price: float
    sl: float
    tp: float
    atr: float
    reason: str
    daily_trend: str
    rsi_4h: float
    ema20_4h: float


class GoldSwingStrategy:
    """Stratégie swing multi-timeframe sur XAUUSD/GC=F."""

    def __init__(
        self,
        ema_fast: int = 20,
        ema_mid: int = 50,
        ema_slow: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        pullback_pct: float = 0.008,   # Pullback toléré vers EMA20 : ±0.8%
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
    ) -> None:
        self.ema_fast = ema_fast
        self.ema_mid = ema_mid
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.pullback_pct = pullback_pct
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    # ------------------------------------------------------------------
    # Indicateurs
    # ------------------------------------------------------------------

    def _ema(self, series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def _rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high, low, close = df["High"], df["Low"], df["Close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    # ------------------------------------------------------------------
    # Fetch données
    # ------------------------------------------------------------------

    def _fetch(self, interval: str, period: str) -> pd.DataFrame:
        df = yf.download(TICKER_YF, interval=interval, period=period,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        return df

    # ------------------------------------------------------------------
    # Analyse principale
    # ------------------------------------------------------------------

    def analyze(self) -> SwingSignal:
        """Retourne le signal swing actuel sur XAUUSD."""

        # --- Données daily pour tendance ---
        df_d = self._fetch("1d", "2y")
        if len(df_d) < self.ema_slow + 5:
            return SwingSignal("HOLD", 0.0, 0.0, 0.0, 0.0, 0.0,
                               "Pas assez de données daily", "inconnu", 0.0, 0.0)

        df_d["ema20"] = self._ema(df_d["Close"], self.ema_fast)
        df_d["ema50"] = self._ema(df_d["Close"], self.ema_mid)
        df_d["ema200"] = self._ema(df_d["Close"], self.ema_slow)

        last_d = df_d.iloc[-1]
        price_d = float(last_d["Close"])
        ema20_d = float(last_d["ema20"])
        ema50_d = float(last_d["ema50"])
        ema200_d = float(last_d["ema200"])

        # Tendance daily
        if ema20_d > ema50_d and ema50_d > ema200_d and price_d > ema200_d:
            daily_trend = "HAUSSIER"
        elif ema20_d < ema50_d and ema50_d < ema200_d and price_d < ema200_d:
            daily_trend = "BAISSIER"
        else:
            daily_trend = "NEUTRE"

        # --- Données 4H pour entrée ---
        df_4h = self._fetch("4h", "60d")
        if len(df_4h) < self.ema_fast + self.atr_period + 5:
            return SwingSignal("HOLD", 0.0, price_d, 0.0, 0.0, 0.0,
                               "Pas assez de données 4H", daily_trend, 0.0, 0.0)

        df_4h["ema20"] = self._ema(df_4h["Close"], self.ema_fast)
        df_4h["rsi"]   = self._rsi(df_4h["Close"], self.rsi_period)
        df_4h["atr"]   = self._atr(df_4h, self.atr_period)

        last   = df_4h.iloc[-1]
        prev   = df_4h.iloc[-2]
        price  = float(last["Close"])
        ema20  = float(last["ema20"])
        rsi    = float(last["rsi"])
        atr    = float(last["atr"])

        # Distance entre prix et EMA20 (4H)
        dist_pct = abs(price - ema20) / ema20

        # Bougie 4H de confirmation
        bullish_candle = float(last["Close"]) > float(last["Open"])
        bearish_candle = float(last["Close"]) < float(last["Open"])

        # RSI : momentum neutre / pas extrême
        rsi_ok_buy  = 35 < rsi < 58   # pas survendu ni surachaté, biaisé haussier
        rsi_ok_sell = 42 < rsi < 65   # pas survendu ni surachaté, biaisé baissier

        # Pullback vers EMA20
        near_ema20 = dist_pct <= self.pullback_pct

        # --- Décision ---
        action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
        confidence = 0.0
        reasons = []

        if daily_trend == "HAUSSIER":
            reasons.append(f"Tendance daily HAUSSIERE (EMA20>{ema20_d:.0f} EMA50>{ema50_d:.0f} EMA200>{ema200_d:.0f})")
            if near_ema20:
                reasons.append(f"Pullback 4H vers EMA20 ({dist_pct:.2%} écart)")
                if rsi_ok_buy:
                    reasons.append(f"RSI(14)={rsi:.1f} zone neutre haussière")
                    if bullish_candle:
                        reasons.append("Bougie 4H haussière de confirmation")
                        action = "BUY"
                        # Score de confiance
                        confidence = 0.65
                        if rsi < 50:   confidence += 0.05   # sous 50 = momentum frais
                        if dist_pct < 0.003: confidence += 0.05  # très proche EMA = pullback net
                        if atr > 0 and (price - prev["Close"]) / atr < -0.3:
                            confidence += 0.05  # bougie de rejet haussière

        elif daily_trend == "BAISSIER":
            reasons.append(f"Tendance daily BAISSIERE (EMA20<{ema20_d:.0f} EMA50<{ema50_d:.0f} EMA200<{ema200_d:.0f})")
            if near_ema20:
                reasons.append(f"Pullback 4H vers EMA20 ({dist_pct:.2%} écart)")
                if rsi_ok_sell:
                    reasons.append(f"RSI(14)={rsi:.1f} zone neutre baissière")
                    if bearish_candle:
                        reasons.append("Bougie 4H baissière de confirmation")
                        action = "SELL"
                        confidence = 0.65
                        if rsi > 50:   confidence += 0.05
                        if dist_pct < 0.003: confidence += 0.05
                        if atr > 0 and (float(prev["Close"]) - price) / atr < -0.3:
                            confidence += 0.05
        else:
            reasons.append(f"Tendance daily NEUTRE — pas de trade (EMA alignement insuffisant)")

        # SL / TP basés sur ATR
        if action == "BUY":
            sl = round(price - self.sl_atr_mult * atr, 2)
            tp = round(price + self.tp_atr_mult * atr, 2)
        elif action == "SELL":
            sl = round(price + self.sl_atr_mult * atr, 2)
            tp = round(price - self.tp_atr_mult * atr, 2)
        else:
            sl = tp = 0.0

        reason_str = " | ".join(reasons) if reasons else f"Tendance {daily_trend} — conditions non réunies"

        logger.info(
            f"[GoldSwing] {action} | Prix={price:.2f} | EMA20(4H)={ema20:.2f} | "
            f"RSI={rsi:.1f} | ATR={atr:.2f} | Tendance={daily_trend} | Conf={confidence:.0%}"
        )

        return SwingSignal(
            action=action,
            confidence=round(confidence, 3),
            price=price,
            sl=sl,
            tp=tp,
            atr=round(atr, 2),
            reason=reason_str,
            daily_trend=daily_trend,
            rsi_4h=round(rsi, 1),
            ema20_4h=round(ema20, 2),
        )
