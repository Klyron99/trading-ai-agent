# Backtest honnête — phase 1

Exécution à l'ouverture suivante, frais + glissement par côté, paramètres choisis en walk-forward (5 ans d'entraînement → 1 an de test).

## SPY daily — OOS 1998-01-29 → 2026-10-16

Coûts : 5 bps frais + 5 bps glissement par côté (colonnes `_2x` : doublés).

| stratégie                    |   cagr_% |   sharpe |   t_stat |   max_dd_% |   expo_% |   trades |   win_% |   frais_tot_% |   cagr_2x_frais_% |   sharpe_2x |
|:-----------------------------|---------:|---------:|---------:|-----------:|---------:|---------:|--------:|--------------:|------------------:|------------:|
| Buy & hold                   |     9.24 |     0.55 |     2.97 |      -55.2 |      100 |        1 |     100 |           0.1 |              9.24 |        0.55 |
| SMA trend (WF)               |     5.12 |     0.48 |     2.57 |      -32.7 |       75 |      120 |      29 |          23.9 |              4.25 |        0.41 |
| Momentum (WF)                |     7.54 |     0.62 |     3.34 |      -29.7 |       78 |       66 |      35 |          13.1 |              7.05 |        0.59 |
| RSI2 reversion (WF)          |     1.86 |     0.25 |     1.33 |      -25.8 |       38 |      538 |      65 |         107.5 |             -1.89 |       -0.16 |
| IBS (WF)                     |    -2.1  |    -0.46 |    -2.49 |      -54.3 |        9 |      550 |      49 |         110   |             -5.78 |       -1.32 |
| ML actuelle long/short       |    -8.75 |    -0.61 |    -3.29 |      -92.9 |       55 |      787 |      52 |         157.4 |            -13.62 |       -1.02 |
| ML actuelle long only        |    -0.61 |    -0.02 |    -0.1  |      -37.2 |       10 |      235 |      55 |          47   |             -2.22 |       -0.19 |
| Buy & hold (même période ML) |     9.24 |     0.56 |     2.97 |      -55.2 |      100 |        1 |     100 |           0.1 |              9.24 |        0.55 |

ML : précision OOS **0.547** vs taux de base (toujours prédire la classe majoritaire) **0.570**.

Paramètres choisis par le walk-forward (dernière fenêtre) : SMA trend → {'n': 150}, Momentum → {'months': 9}, RSI2 reversion → {'entry': 25, 'exit_': 70}, IBS → {'thr': 0.1}

## QQQ daily — OOS 2004-03-10 → 2026-10-16

Coûts : 5 bps frais + 5 bps glissement par côté (colonnes `_2x` : doublés).

| stratégie                    |   cagr_% |   sharpe |   t_stat |   max_dd_% |   expo_% |   trades |   win_% |   frais_tot_% |   cagr_2x_frais_% |   sharpe_2x |
|:-----------------------------|---------:|---------:|---------:|-----------:|---------:|---------:|--------:|--------------:|------------------:|------------:|
| Buy & hold                   |    15.1  |     0.76 |     3.63 |      -53.4 |      100 |        1 |     100 |           0.1 |             15.1  |        0.76 |
| SMA trend (WF)               |     9.61 |     0.69 |     3.28 |      -26.7 |       76 |       92 |      29 |          18.3 |              8.73 |        0.64 |
| Momentum (WF)                |    10.18 |     0.69 |     3.27 |      -31.5 |       81 |       81 |      40 |          16.1 |              9.4  |        0.64 |
| RSI2 reversion (WF)          |     1.27 |     0.17 |     0.79 |      -42.7 |       40 |      393 |      65 |          78.5 |             -2.19 |       -0.12 |
| IBS (WF)                     |    -1.63 |    -0.22 |    -1.06 |      -46.5 |       10 |      492 |      53 |          98.4 |             -5.82 |       -0.89 |
| ML actuelle long/short       |    -9.64 |    -0.6  |    -2.86 |      -90.1 |       52 |      643 |      51 |         128.5 |            -14.65 |       -0.98 |
| ML actuelle long only        |     0.17 |     0.06 |     0.3  |      -30.9 |       12 |      219 |      58 |          43.7 |             -1.75 |       -0.17 |
| Buy & hold (même période ML) |    15.1  |     0.76 |     3.62 |      -53.4 |      100 |        1 |     100 |           0.1 |             15.1  |        0.76 |

ML : précision OOS **0.521** vs taux de base (toujours prédire la classe majoritaire) **0.542**.

Paramètres choisis par le walk-forward (dernière fenêtre) : SMA trend → {'n': 150}, Momentum → {'months': 6}, RSI2 reversion → {'entry': 5, 'exit_': 50}, IBS → {'thr': 0.1}

## BTC-USD 1h — OOS 2025-04-30 → 2026-10-16

Coûts : 10 bps frais + 5 bps glissement par côté.

| stratégie                 |   cagr_% |   sharpe |   t_stat |   max_dd_% |   expo_% |   trades |   win_% |   frais_tot_% |   cagr_2x_frais_% |   sharpe_2x |
|:--------------------------|---------:|---------:|---------:|-----------:|---------:|---------:|--------:|--------------:|------------------:|------------:|
| Buy & hold                |   -10.12 |    -0.05 |    -0.07 |      -54   |      100 |        1 |       0 |           0.2 |            -10.21 |       -0.06 |
| ML actuelle long/short    |   -25.83 |    -0.65 |    -0.79 |      -46.2 |       77 |      273 |      59 |          81.8 |            -57.63 |       -2.18 |
| ML actuelle long only     |    -1.14 |    -0.41 |    -0.5  |       -3.1 |        0 |        8 |      50 |           2.4 |             -2.75 |       -0.98 |
| ML sans frais (référence) |    29.71 |     0.9  |     1.09 |      -28.8 |       77 |      273 |      64 |           0   |             29.71 |        0.9  |

ML : précision OOS **0.632** vs taux de base **0.638**.
