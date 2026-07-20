"""
Feature engineering — 100+ features multi-sources :
- Indicateurs techniques (momentum, MA, RSI, MACD, Bollinger, ATR, Stoch, OBV)
- Fear & Greed Index (sentiment crypto)
- Macro : DXY, SP500, Gold (risk-on/risk-off)
- Régimes de marché, niveaux clés, autocorrélation
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def compute_stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> tuple[pd.Series, pd.Series]:
    low_min  = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    stoch_k  = 100 * (df["Close"] - low_min) / (high_max - low_min + 1e-9)
    stoch_d  = stoch_k.rolling(d).mean()
    return stoch_k, stoch_d


def _merge_daily_to_ohlcv(df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Merge données journalières dans un OHLCV (horaire ou journalier) par date."""
    idx_date = df.index.normalize() if hasattr(df.index, "normalize") else pd.to_datetime(df.index).normalize()
    result = pd.DataFrame(index=df.index)
    for col in daily.columns:
        s = daily[col].reindex(idx_date.unique()).sort_index()
        # Forward-fill : la valeur du jour est connue à l'ouverture
        s_ff = s.reindex(idx_date).ffill().values
        result[col] = s_ff
    return result


def build_features(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    feat  = pd.DataFrame(index=df.index)
    close  = df["Close"]
    volume = df["Volume"]
    high   = df.get("High", close)
    low    = df.get("Low",  close)

    # ── 1. MOMENTUM multi-période ─────────────────────────────────────────────
    for n in [1, 2, 3, 5, 7, 10, 14, 21, 30]:
        feat[f"ret_{n}d"] = close.pct_change(n)
    feat["mom_accel"]  = feat["ret_3d"] - feat["ret_5d"]
    feat["mom_accel2"] = feat["ret_5d"] - feat["ret_10d"]
    feat["mom_accel3"] = feat["ret_10d"] - feat["ret_21d"]

    # ── 2. MOYENNES MOBILES ───────────────────────────────────────────────────
    for w in [5, 10, 20, 50, 100, 200]:
        ma = close.rolling(w).mean()
        feat[f"price_vs_ma{w}"] = close / ma - 1
    feat["ma5_vs_ma20"]   = close.rolling(5).mean()  / close.rolling(20).mean()  - 1
    feat["ma20_vs_ma50"]  = close.rolling(20).mean() / close.rolling(50).mean()  - 1
    feat["ma50_vs_ma200"] = close.rolling(50).mean() / close.rolling(200).mean() - 1

    ema9  = close.ewm(span=9,  adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200= close.ewm(span=200,adjust=False).mean()
    feat["ema9_vs_ema21"]   = ema9  / ema21  - 1
    feat["ema21_vs_ema50"]  = ema21 / ema50  - 1
    feat["price_vs_ema9"]   = close / ema9   - 1
    feat["price_vs_ema200"] = close / ema200 - 1
    feat["ema_golden_cross"] = (ema50 > ema200).astype(int)

    # ── 3. RSI multi-période ──────────────────────────────────────────────────
    for w in [7, 14, 21, 28]:
        rsi = compute_rsi(close, w)
        feat[f"rsi_{w}"]           = rsi / 100
        feat[f"rsi_{w}_oversold"]  = (rsi < 30).astype(int)
        feat[f"rsi_{w}_overbought"]= (rsi > 70).astype(int)
    feat["rsi14_change"] = feat["rsi_14"].diff(3)
    feat["rsi14_change5"]= feat["rsi_14"].diff(5)

    # ── 4. MACD ───────────────────────────────────────────────────────────────
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd   = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    feat["macd_hist"]      = (macd - signal) / (close + 1e-9)
    feat["macd_cross"]     = (macd > signal).astype(int)
    feat["macd_cross_chg"] = feat["macd_cross"].diff().fillna(0)
    feat["macd_slope"]     = feat["macd_hist"].diff(3)
    feat["macd_norm"]      = (macd - macd.rolling(50).mean()) / (macd.rolling(50).std() + 1e-9)

    # ── 5. BOLLINGER BANDS ────────────────────────────────────────────────────
    for w in [10, 20, 50]:
        ma_w  = close.rolling(w).mean()
        std_w = close.rolling(w).std()
        bb_up = ma_w + 2 * std_w
        bb_lo = ma_w - 2 * std_w
        feat[f"bb_pos_{w}"]   = (close - bb_lo) / (bb_up - bb_lo + 1e-9)
        feat[f"bb_width_{w}"] = (bb_up - bb_lo) / (ma_w + 1e-9)
    feat["bb_squeeze"]     = (feat["bb_width_20"] < feat["bb_width_20"].rolling(50).quantile(0.2)).astype(int)
    feat["bb_breakout_up"] = (close > close.rolling(20).mean() + 2 * close.rolling(20).std()).astype(int)
    feat["bb_breakout_dn"] = (close < close.rolling(20).mean() - 2 * close.rolling(20).std()).astype(int)

    # ── 6. ATR & VOLATILITÉ ───────────────────────────────────────────────────
    atr14 = compute_atr(df, 14)
    atr7  = compute_atr(df, 7)
    atr28 = compute_atr(df, 28)
    feat["atr14_norm"]    = atr14 / close
    feat["atr7_vs_atr14"] = atr7 / (atr14 + 1e-9)
    feat["atr14_vs_atr28"]= atr14 / (atr28 + 1e-9)
    feat["volatility_5d"] = close.pct_change().rolling(5).std()
    feat["volatility_20d"]= close.pct_change().rolling(20).std()
    feat["volatility_60d"]= close.pct_change().rolling(60).std()
    feat["vol_ratio"]     = feat["volatility_5d"] / (feat["volatility_20d"] + 1e-9)
    feat["vol_regime"]    = (feat["volatility_5d"] > feat["volatility_20d"]).astype(int)

    # ── 7. STOCHASTIQUE ──────────────────────────────────────────────────────
    stoch_k, stoch_d = compute_stoch(df)
    feat["stoch_k"]        = stoch_k / 100
    feat["stoch_d"]        = stoch_d / 100
    feat["stoch_kd_cross"] = (stoch_k > stoch_d).astype(int)
    feat["stoch_oversold"] = (stoch_k < 20).astype(int)
    feat["stoch_overbought"]=(stoch_k > 80).astype(int)

    # ── 8. OBV ────────────────────────────────────────────────────────────────
    obv = compute_obv(close, volume)
    feat["obv_slope"]   = obv.pct_change(5)
    feat["obv_vs_ma"]   = obv / obv.rolling(20).mean() - 1
    feat["obv_slope3"]  = obv.pct_change(3)
    feat["obv_diverge"] = (feat["ret_5d"] > 0).astype(int) - (feat["obv_slope"] > 0).astype(int)

    # ── 9. VOLUME ─────────────────────────────────────────────────────────────
    feat["volume_ratio"]  = volume / (volume.rolling(20).mean() + 1e-9)
    feat["volume_ratio5"] = volume / (volume.rolling(5).mean()  + 1e-9)
    feat["volume_spike"]  = (feat["volume_ratio"] > 2).astype(int)
    feat["volume_trend"]  = volume.rolling(5).mean() / (volume.rolling(20).mean() + 1e-9)
    feat["volume_dry"]    = (feat["volume_ratio"] < 0.5).astype(int)

    # ── 10. RANGE & STRUCTURE DE PRIX ────────────────────────────────────────
    daily_range = (high - low) / (close + 1e-9)
    feat["daily_range"]     = daily_range
    feat["range_vs_avg"]    = daily_range / (daily_range.rolling(14).mean() + 1e-9)
    open_price = df.get("Open", close)
    feat["candle_body"]     = (close - open_price).abs() / (daily_range * close + 1e-9)
    feat["upper_shadow"]    = (high - pd.concat([close, open_price], axis=1).max(axis=1)) / (close + 1e-9)
    feat["lower_shadow"]    = (pd.concat([close, open_price], axis=1).min(axis=1) - low) / (close + 1e-9)
    feat["bullish_candle"]  = (close > open_price).astype(int)

    # ── 11. NIVEAUX CLÉS ─────────────────────────────────────────────────────
    for w in [10, 20, 52]:
        feat[f"dist_high{w}"] = close / (close.rolling(w).max()  + 1e-9) - 1
        feat[f"dist_low{w}"]  = close / (close.rolling(w).min()  + 1e-9) - 1

    # ── 12. AUTOCORRÉLATION & LAGS ───────────────────────────────────────────
    ret1 = close.pct_change()
    for lag in [1, 2, 3, 5, 7]:
        feat[f"ret_lag{lag}"] = ret1.shift(lag)

    # ── 13. RÉGIMES DE MARCHÉ ────────────────────────────────────────────────
    feat["trend_score"] = (
        (close > close.rolling(20).mean()).astype(int) +
        (close > close.rolling(50).mean()).astype(int) +
        (close.rolling(20).mean() > close.rolling(50).mean()).astype(int)
    ) / 3
    feat["high_vol_regime"] = (feat["volatility_20d"] > feat["volatility_20d"].rolling(60).quantile(0.75)).astype(int)
    feat["strong_uptrend"]  = (
        (close > close.rolling(50).mean()) &
        (close.rolling(20).mean() > close.rolling(50).mean()) &
        (feat["rsi_14"] > 0.5)
    ).astype(int)
    feat["strong_downtrend"]= (
        (close < close.rolling(50).mean()) &
        (close.rolling(20).mean() < close.rolling(50).mean()) &
        (feat["rsi_14"] < 0.5)
    ).astype(int)

    # ── 14. FEAR & GREED INDEX ───────────────────────────────────────────────
    _CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"}
    if ticker in _CRYPTO or not ticker:
        try:
            from data.fear_greed import get_fear_greed
            fg_raw = get_fear_greed(limit=1000)
            if not fg_raw.empty:
                fg_merged = _merge_daily_to_ohlcv(df, fg_raw)
                fg = fg_merged["fear_greed"]
                feat["fear_greed"]         = fg / 100              # 0-1
                feat["fear_greed_extreme_fear"]  = (fg < 25).astype(int)
                feat["fear_greed_fear"]     = (fg < 40).astype(int)
                feat["fear_greed_greed"]    = (fg > 60).astype(int)
                feat["fear_greed_extreme_greed"]= (fg > 75).astype(int)
                feat["fear_greed_change3d"] = feat["fear_greed"].diff(3)
                feat["fear_greed_change7d"] = feat["fear_greed"].diff(7)
                # MA du F&G
                feat["fear_greed_vs_ma14"]  = feat["fear_greed"] - feat["fear_greed"].rolling(14).mean()
                feat["fear_greed_vs_ma30"]  = feat["fear_greed"] - feat["fear_greed"].rolling(30).mean()
        except Exception as exc:
            pass  # F&G indisponible — on continue sans

    # ── 15. DONNÉES MACRO (DXY, SP500, GOLD) ─────────────────────────────────
    if ticker in _CRYPTO or not ticker:
        try:
            from data.macro_data import get_macro_daily
            macro = get_macro_daily()
            if not macro.empty:
                macro_merged = _merge_daily_to_ohlcv(df, macro)
                for col in macro_merged.columns:
                    feat[f"macro_{col}"] = macro_merged[col]
                # Corrélation glissante BTC vs SP500 (20 barres)
                if "macro_sp500_ret1d" in feat.columns:
                    feat["btc_sp500_corr20"] = (
                        feat["ret_1d"].rolling(20).corr(feat["macro_sp500_ret1d"])
                    )
                    feat["btc_dxy_corr20"] = (
                        feat["ret_1d"].rolling(20).corr(feat["macro_dxy_ret1d"])
                    ) if "macro_dxy_ret1d" in feat.columns else np.nan
        except Exception:
            pass  # Macro indisponible — on continue sans

    return feat


def build_target(df: pd.DataFrame, ticker: str = "") -> pd.Series:
    """Target adaptatif selon la fréquence des données.
    - Horaire  (>2000 barres) : horizon 6h, seuil 0.3%
    - Journalier              : horizon 3j, seuil 0.5%
    """
    if len(df) > 2000:
        h, thr = 6, 0.003
    else:
        h, thr = 3, 0.005
    future_return = df["Close"].shift(-h) / df["Close"] - 1
    return (future_return > thr).astype(int)
