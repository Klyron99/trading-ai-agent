# Stratégie gold — recherche sur tout l'historique

Exécution à l'ouverture suivante, 5 + 5 bps par côté. Paramètres en walk-forward (5 ans → 1 an). **dev** = OOS jusqu'à fin 2020 (sert au choix). **holdout** = 2021 → aujourd'hui (jamais utilisé pour choisir).

## GC=F — données 2000-08-30 → 2026-10-16

| stratégie                 |   dev_cagr_% |   dev_sharpe |   dev_max_dd_% |   holdout_cagr_% |   holdout_sharpe |   holdout_max_dd_% |   holdout_trades |   sharpe_2x_frais | derniers_params                                       |
|:--------------------------|-------------:|-------------:|---------------:|-----------------:|-----------------:|-------------------:|-----------------:|------------------:|:------------------------------------------------------|
| Buy & hold                |        10.13 |         0.61 |          -44.4 |            14.13 |             0.8  |              -24.9 |                1 |              0.67 | -                                                     |
| Buy & hold vol-ciblé 12 % |         7.57 |         0.65 |          -39.6 |            10.07 |             0.81 |              -17.8 |                1 |              0.66 | -                                                     |
| Tendance SMA (WF)         |         6.39 |         0.62 |          -37.5 |             8.34 |             0.61 |              -26.3 |               35 |              0.52 | {'n': 100, 'short': False, 'vt': 0.12}                |
| Croisement MM (WF)        |         5.25 |         0.54 |          -44.1 |            11.1  |             0.75 |              -19.4 |               10 |              0.55 | {'fast': 50, 'slow': 100, 'short': False, 'vt': 0.12} |
| Momentum (WF)             |         5.4  |         0.53 |          -37   |             8.67 |             0.63 |              -24.3 |               33 |              0.48 | {'months': 3, 'short': False, 'vt': 0.12}             |
| Breakout Donchian (WF)    |         4.8  |         0.56 |          -24.6 |             4.45 |             0.49 |              -20.4 |               16 |              0.47 | {'n': 100, 'short': False, 'vt': 0.12}                |
| RSI2 reversion (WF)       |         1.48 |         0.22 |          -31.2 |             1.05 |             0.16 |              -20.2 |               88 |             -0.1  | {'entry': 10, 'exit_': 50, 'vt': 0.12}                |

## GLD — données 2004-11-18 → 2026-10-16

| stratégie                 |   dev_cagr_% |   dev_sharpe |   dev_max_dd_% |   holdout_cagr_% |   holdout_sharpe |   holdout_max_dd_% |   holdout_trades |   sharpe_2x_frais | derniers_params                                       |
|:--------------------------|-------------:|-------------:|---------------:|-----------------:|-----------------:|-------------------:|-----------------:|------------------:|:------------------------------------------------------|
| Buy & hold                |         4.28 |         0.34 |          -45.6 |            13.57 |             0.79 |              -26.4 |                1 |              0.52 | -                                                     |
| Buy & hold vol-ciblé 12 % |         2.82 |         0.29 |          -42.6 |            10.92 |             0.87 |              -18.9 |                1 |              0.47 | -                                                     |
| Tendance SMA (WF)         |         1.68 |         0.2  |          -40.5 |             4.28 |             0.44 |              -26.7 |               58 |              0.14 | {'n': 100, 'short': False, 'vt': 0.12}                |
| Croisement MM (WF)        |         0.87 |         0.13 |          -47.9 |            11.48 |             0.97 |              -16.8 |               10 |              0.38 | {'fast': 50, 'slow': 100, 'short': False, 'vt': 0.12} |
| Momentum (WF)             |         1.44 |         0.18 |          -39   |             8.69 |             0.77 |              -18.7 |               26 |              0.31 | {'months': 3, 'short': False, 'vt': 0.12}             |
| Breakout Donchian (WF)    |         0.14 |         0.06 |          -30.5 |            11.18 |             1.03 |              -14.1 |               12 |              0.34 | {'n': 100, 'short': False, 'vt': 0.12}                |
| RSI2 reversion (WF)       |         2.8  |         0.39 |          -23   |            -2.33 |            -0.34 |              -22.6 |               96 |             -0.12 | {'entry': 5, 'exit_': 70, 'vt': 0.12}                 |

**Famille retenue (meilleur Sharpe dev sur GC=F) : Tendance SMA (WF)**

## Conclusion honnête

- Aucune règle de timing (SMA, croisement MM, momentum, Donchian, RSI2) ne bat le buy & hold de l'or après frais.
  La famille choisie sur la période dev (SMA) fait moins bien que le buy & hold en hold-out (Sharpe 0,61 vs 0,80 sur GC=F).
- Retenu : `strategies/gold_vol_target_strategy.py`, long permanent, exposition = min(1, 12 % / vol 20 j), rebalancement si écart > 10 %.

| | CAGR 2005+ | Sharpe | Max DD | CAGR 2021+ | Sharpe | Max DD |
|---|---|---|---|---|---|---|
| GC=F buy & hold | 11,0 % | 0,66 | -44,4 % | 14,1 % | 0,80 | -24,9 % |
| GC=F vol-ciblé (bande) | 8,6 % | 0,72 | -37,7 % | 10,6 % | 0,85 | -17,8 % |
| GLD buy & hold | 10,6 % | 0,64 | -45,6 % | 13,6 % | 0,79 | -26,4 % |
| GLD vol-ciblé (bande) | 8,3 % | 0,70 | -41,9 % | 11,9 % | 0,95 | -18,3 % |

On échange du rendement contre moins de risque. Ce n'est pas un « alpha ». Le hold-out 2021+ correspond à un fort marché haussier de l'or et n'est pas représentatif d'une baisse longue comme 2011-2015.
