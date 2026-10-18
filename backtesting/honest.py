"""
Banc de backtest « honnête ».

Différences avec backtesting/backtester.py :
  - Pas de look-ahead : le signal calculé à la clôture de la bougie t est
    exécuté à l'OUVERTURE de la bougie t+1.
  - Frais + glissement facturés à chaque changement de position
    (en fraction du notionnel échangé, par côté).
  - Walk-forward : les paramètres / modèles sont choisis uniquement sur le
    passé, puis appliqués sur la période suivante jamais vue.

Convention : une stratégie produit une Series « target » de positions
désirées (-1 short, 0 cash, +1 long, valeurs intermédiaires permises),
calculée avec les données disponibles à la clôture de chaque bougie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    """Coûts par côté, en fraction du notionnel (0.0005 = 0,05 %)."""
    fee: float = 0.0
    slippage: float = 0.0

    @property
    def per_side(self) -> float:
        return self.fee + self.slippage


def simulate(df: pd.DataFrame, target: pd.Series, costs: Costs) -> pd.DataFrame:
    """Simule une série de positions cibles avec exécution à l'ouverture suivante.

    Rendement de la bougie t :
        (1 + pos_{t-1} * gap_t) * (1 + pos_t * intra_t) - 1 - coût_t
    où gap_t = Open_t / Close_{t-1} - 1, intra_t = Close_t / Open_t - 1,
    pos_t = target_{t-1} (décidé à la clôture précédente).
    """
    target = target.reindex(df.index).fillna(0.0).astype(float)
    pos = target.shift(1).fillna(0.0)          # exécution à l'open suivant
    prev_pos = pos.shift(1).fillna(0.0)

    gap = (df["Open"] / df["Close"].shift(1) - 1).fillna(0.0)
    intra = df["Close"] / df["Open"] - 1

    turnover = (pos - prev_pos).abs()
    cost = turnover * costs.per_side
    gross = (1 + prev_pos * gap) * (1 + pos * intra) - 1
    net = gross - cost

    out = pd.DataFrame({
        "position": pos,
        "gross_ret": gross,
        "cost": cost,
        "ret": net,
        "turnover": turnover,
    }, index=df.index)
    out["equity"] = (1 + out["ret"]).cumprod()
    return out


def _bars_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 252.0
    span_days = (index[-1] - index[0]).total_seconds() / 86400
    return len(index) / max(span_days / 365.25, 1e-9)


def _trades(sim: pd.DataFrame) -> list[float]:
    """Rendement net de chaque trade (séquence de position non nulle de même signe)."""
    pos = np.sign(sim["position"].values)
    rets = sim["ret"].values
    trades, cur, sign = [], None, 0
    for p, r in zip(pos, rets):
        if p != sign:
            if cur is not None:
                trades.append(cur - 1)
            cur, sign = (1 + r, p) if p != 0 else (None, 0)
        elif cur is not None:
            cur *= 1 + r
    if cur is not None:
        trades.append(cur - 1)
    return trades


def metrics(sim: pd.DataFrame) -> dict:
    ret = sim["ret"]
    n = len(ret)
    bpy = _bars_per_year(sim.index)
    years = n / bpy
    eq = sim["equity"]
    total = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else -1.0
    vol = ret.std() * np.sqrt(bpy)
    sharpe = ret.mean() / ret.std() * np.sqrt(bpy) if ret.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    trades = _trades(sim)
    return {
        "periode": f"{sim.index[0].date()} → {sim.index[-1].date()}",
        "total_%": round(total * 100, 1),
        "cagr_%": round(cagr * 100, 2),
        "vol_%": round(vol * 100, 1),
        "sharpe": round(sharpe, 2),
        # t-stat du rendement moyen : < 2 → pas distinguable du hasard
        "t_stat": round(sharpe * np.sqrt(years), 2),
        "max_dd_%": round(dd * 100, 1),
        "expo_%": round((sim["position"] != 0).mean() * 100, 0),
        "trades": len(trades),
        "win_%": round(np.mean([t > 0 for t in trades]) * 100, 0) if trades else 0,
        "trade_moy_%": round(np.mean(trades) * 100, 3) if trades else 0,
        "frais_tot_%": round(sim["cost"].sum() * 100, 1),
    }


# ── Walk-forward pour stratégies paramétriques ──────────────────────────────

SignalFn = Callable[..., pd.Series]


def walk_forward_params(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    grid: Iterable[dict],
    costs: Costs,
    train_years: int = 5,
    test_years: int = 1,
    score: str = "sharpe",
) -> tuple[pd.Series, list[dict]]:
    """Choisit les paramètres sur les `train_years` passés, applique sur `test_years`.

    Les signaux sont calculés sur tout l'historique (indicateurs causaux), mais
    le choix des paramètres n'utilise que la fenêtre d'entraînement.
    Retourne la série target OOS recollée et le journal des choix.
    """
    grid = list(grid)
    all_targets = {i: signal_fn(df, **p) for i, p in enumerate(grid)}
    start = df.index[0] + pd.DateOffset(years=train_years)
    oos = pd.Series(np.nan, index=df.index)
    log = []
    t0 = start
    while t0 < df.index[-1]:
        t1 = t0 + pd.DateOffset(years=test_years)
        train = df.loc[t0 - pd.DateOffset(years=train_years): t0 - pd.Timedelta(seconds=1)]
        best_i, best_s = 0, -np.inf
        for i, tgt in all_targets.items():
            s = metrics(simulate(train, tgt.loc[train.index], costs))[score]
            if s > best_s:
                best_i, best_s = i, s
        mask = (df.index >= t0) & (df.index < t1)
        oos[mask] = all_targets[best_i][mask]
        log.append({"debut_test": t0.date(), "params": grid[best_i], f"{score}_train": best_s})
        t0 = t1
    return oos.dropna(), log


# ── Walk-forward pour modèles ML ────────────────────────────────────────────

def walk_forward_ml(
    features: pd.DataFrame,
    target: pd.Series,
    make_model: Callable[[], object],
    train_bars: int,
    step_bars: int,
    purge_bars: int,
    expanding: bool = False,
) -> pd.Series:
    """Ré-entraîne tous les `step_bars`, prédit les `step_bars` suivantes.

    `purge_bars` (= horizon du target) supprime la fin de la fenêtre
    d'entraînement dont l'étiquette dépend de prix futurs non encore connus.
    Retourne la probabilité OOS de la classe 1.
    """
    X = features.replace([np.inf, -np.inf], np.nan)
    proba = pd.Series(np.nan, index=X.index)
    i = train_bars + purge_bars
    while i < len(X):
        tr_end = i - purge_bars
        tr_start = 0 if expanding else max(0, tr_end - train_bars)
        Xtr, ytr = X.iloc[tr_start:tr_end], target.iloc[tr_start:tr_end]
        ok = Xtr.notna().all(axis=1) & ytr.notna()
        Xte = X.iloc[i:i + step_bars]
        if ok.sum() > 200 and len(Xte):
            m = make_model()
            m.fit(Xtr[ok], ytr[ok].astype(int))
            te_ok = Xte.notna().all(axis=1)
            if te_ok.any():
                proba.loc[Xte.index[te_ok]] = m.predict_proba(Xte[te_ok])[:, 1]
        i += step_bars
    return proba
