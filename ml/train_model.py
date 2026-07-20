"""
Entraînement avec sélection de features, calibration des probabilités,
et optimisation ciblée sur la précision à haute confiance.
Le but : avoir raison le plus souvent possible quand on trade, pas forcément tout le temps.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib
from loguru import logger

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score
from sklearn.model_selection import TimeSeriesSplit

from config.settings import MODEL_STORE_DIR, ML_RANDOM_STATE, ML_TEST_SIZE
from ml.feature_engineering import build_features, build_target

_GB_PARAMS = [
    dict(n_estimators=300, max_depth=3, learning_rate=0.03, min_samples_leaf=30, subsample=0.7),
    dict(n_estimators=200, max_depth=4, learning_rate=0.05, min_samples_leaf=25, subsample=0.8),
    dict(n_estimators=400, max_depth=3, learning_rate=0.02, min_samples_leaf=40, subsample=0.75),
    dict(n_estimators=200, max_depth=5, learning_rate=0.05, min_samples_leaf=20, subsample=0.85),
    dict(n_estimators=500, max_depth=3, learning_rate=0.01, min_samples_leaf=50, subsample=0.7),
]

_RF_PARAMS = [
    dict(n_estimators=300, max_depth=8,  min_samples_leaf=20, max_features="sqrt"),
    dict(n_estimators=500, max_depth=10, min_samples_leaf=15, max_features="sqrt"),
    dict(n_estimators=200, max_depth=6,  min_samples_leaf=30, max_features=0.7),
]

# Seuil de confiance pour trader : ne trade que quand le modèle est sûr
CONFIDENCE_THRESHOLD = 0.55


_PRIORITY_FEATURES = [
    # Fear & Greed — forçage prioritaire : signal externe non capturé par les techniques
    "fear_greed", "fear_greed_extreme_fear", "fear_greed_extreme_greed",
    "fear_greed_change3d", "fear_greed_change7d", "fear_greed_vs_ma14",
    # Macro
    "macro_sp500_ret1d", "macro_sp500_ret5d", "macro_dxy_ret1d",
    "btc_sp500_corr20", "btc_dxy_corr20",
]


def _select_features(X_train: pd.DataFrame, y_train: pd.Series,
                     X_test: pd.DataFrame, k: int = 35) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sélection par importance — features prioritaires (F&G, macro) toujours incluses."""
    from sklearn.ensemble import GradientBoostingClassifier as _GBC
    _sel = _GBC(n_estimators=50, max_depth=3, random_state=ML_RANDOM_STATE)
    _sel.fit(X_train, y_train)
    importances = pd.Series(_sel.feature_importances_, index=X_train.columns)

    # Features prioritaires présentes dans les données
    forced = [c for c in _PRIORITY_FEATURES if c in X_train.columns]
    # Compléter avec les meilleures features techniques jusqu'à k total
    remaining = importances.drop(labels=[c for c in forced if c in importances.index])
    n_fill = max(0, k - len(forced))
    top_tech = remaining.nlargest(n_fill).index.tolist()
    top_cols = forced + [c for c in top_tech if c not in forced]

    logger.info(f"  Forced: {len(forced)} externes | Tech: {len(top_tech)} | Total: {len(top_cols)}")
    logger.info(f"  Top features: {', '.join(top_cols[:8])}...")
    return X_train[top_cols], X_test[top_cols]


def _precision_at_confidence(model, X_test: pd.DataFrame, y_test: pd.Series,
                              threshold: float = CONFIDENCE_THRESHOLD) -> float:
    """Précision uniquement sur les prédictions à haute confiance."""
    proba = model.predict_proba(X_test)[:, 1]
    mask  = proba >= threshold
    if mask.sum() < 5:
        return 0.0
    precision = precision_score(y_test[mask], (proba[mask] >= 0.5).astype(int), zero_division=0)
    coverage  = mask.mean()
    logger.info(f"    Precision@{threshold:.0%}: {precision:.4f}  coverage={coverage:.1%}  n={mask.sum()}")
    return precision


def _cv_score(model_cls, params: dict, X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> float:
    """CV temporelle — combine accuracy + précision haute confiance."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []
    for tr_i, va_i in tscv.split(X):
        X_tr, X_va = X.iloc[tr_i], X.iloc[va_i]
        y_tr, y_va = y.iloc[tr_i], y.iloc[va_i]
        m = model_cls(**params, random_state=ML_RANDOM_STATE)
        m.fit(X_tr, y_tr)
        pred  = m.predict(X_va)
        proba = m.predict_proba(X_va)[:, 1]
        acc   = accuracy_score(y_va, pred)
        # Précision sur signaux à haute confiance
        mask = proba >= CONFIDENCE_THRESHOLD
        prec_hc = precision_score(y_va[mask], pred[mask], zero_division=0) if mask.sum() >= 3 else acc
        scores.append(0.4 * acc + 0.6 * prec_hc)
    return float(np.mean(scores))


def _try_xgboost(X_train, y_train, X_test, y_test):
    try:
        from xgboost import XGBClassifier
        param_grid = [
            dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                 colsample_bytree=0.8, min_child_weight=5),
            dict(n_estimators=400, max_depth=3, learning_rate=0.03, subsample=0.75,
                 colsample_bytree=0.7, min_child_weight=10),
            dict(n_estimators=500, max_depth=3, learning_rate=0.02, subsample=0.75,
                 colsample_bytree=0.8, min_child_weight=8),
            dict(n_estimators=600, max_depth=4, learning_rate=0.02, subsample=0.8,
                 colsample_bytree=0.7, min_child_weight=12),
        ]
        tscv = TimeSeriesSplit(n_splits=5)
        best_p, best_s = None, -1
        for p in param_grid:
            scores = []
            for tr_i, va_i in tscv.split(X_train):
                m = XGBClassifier(**p, random_state=ML_RANDOM_STATE,
                                  eval_metric="logloss", verbosity=0)
                m.fit(X_train.iloc[tr_i], y_train.iloc[tr_i])
                pred  = m.predict(X_train.iloc[va_i])
                proba = m.predict_proba(X_train.iloc[va_i])[:, 1]
                acc   = accuracy_score(y_train.iloc[va_i], pred)
                mask  = proba >= CONFIDENCE_THRESHOLD
                prec  = precision_score(y_train.iloc[va_i][mask], pred[mask], zero_division=0) if mask.sum() >= 3 else acc
                scores.append(0.4 * acc + 0.6 * prec)
            s = float(np.mean(scores))
            if s > best_s:
                best_s, best_p = s, p

        from sklearn.utils.class_weight import compute_sample_weight
        sw = compute_sample_weight("balanced", y_train)
        final = XGBClassifier(**best_p, random_state=ML_RANDOM_STATE,
                               eval_metric="logloss", verbosity=0)
        final.fit(X_train, y_train, sample_weight=sw)
        acc  = accuracy_score(y_test, final.predict(X_test))
        prec = _precision_at_confidence(final, X_test, y_test)
        score = 0.4 * acc + 0.6 * prec
        logger.info(f"  XGBoost CV={best_s:.4f} test_acc={acc:.4f} prec_hc={prec:.4f} final={score:.4f}")
        return final, acc, prec, best_s, score, "XGBoost"
    except ImportError:
        logger.info("  XGBoost non installe — ignore")
        return None


def _try_lightgbm(X_train, y_train, X_test, y_test):
    try:
        import lightgbm as lgb
        param_grid = [
            dict(n_estimators=500, max_depth=5, learning_rate=0.03, num_leaves=31,
                 subsample=0.8, colsample_bytree=0.8, min_child_samples=20),
            dict(n_estimators=700, max_depth=4, learning_rate=0.02, num_leaves=25,
                 subsample=0.75, colsample_bytree=0.7, min_child_samples=30),
            dict(n_estimators=400, max_depth=6, learning_rate=0.05, num_leaves=50,
                 subsample=0.85, colsample_bytree=0.8, min_child_samples=15),
            dict(n_estimators=600, max_depth=5, learning_rate=0.02, num_leaves=40,
                 subsample=0.8, colsample_bytree=0.75, min_child_samples=25),
        ]
        tscv = TimeSeriesSplit(n_splits=5)
        best_p, best_s = None, -1
        for p in param_grid:
            scores = []
            for tr_i, va_i in tscv.split(X_train):
                m = lgb.LGBMClassifier(**p, random_state=ML_RANDOM_STATE,
                                       class_weight="balanced", verbose=-1)
                m.fit(X_train.iloc[tr_i], y_train.iloc[tr_i])
                pred  = m.predict(X_train.iloc[va_i])
                proba = m.predict_proba(X_train.iloc[va_i])[:, 1]
                acc   = accuracy_score(y_train.iloc[va_i], pred)
                mask  = proba >= CONFIDENCE_THRESHOLD
                prec  = precision_score(y_train.iloc[va_i][mask], pred[mask], zero_division=0) if mask.sum() >= 3 else acc
                scores.append(0.4 * acc + 0.6 * prec)
            s = float(np.mean(scores))
            if s > best_s:
                best_s, best_p = s, p

        final = lgb.LGBMClassifier(**best_p, random_state=ML_RANDOM_STATE,
                                    class_weight="balanced", verbose=-1)
        final.fit(X_train, y_train)
        acc  = accuracy_score(y_test, final.predict(X_test))
        prec = _precision_at_confidence(final, X_test, y_test)
        score = 0.4 * acc + 0.6 * prec
        logger.info(f"  LightGBM CV={best_s:.4f} test_acc={acc:.4f} prec_hc={prec:.4f} final={score:.4f}")
        return final, acc, prec, best_s, score, "LightGBM"
    except ImportError:
        logger.info("  LightGBM non installe — ignore")
        return None


def train(df: pd.DataFrame, ticker: str):
    """Entraîne et sélectionne le modèle maximisant la précision sur les trades à haute confiance."""
    features = build_features(df, ticker=ticker)
    target   = build_target(df, ticker=ticker)
    # Nettoyage : ffill externes, remplace inf, fill 0
    features = features.ffill().replace([np.inf, -np.inf], np.nan).fillna(0)
    combined = features.join(target.rename("target")).dropna(subset=["target"])
    X = combined.drop(columns=["target"])
    y = combined["target"]

    if len(X) < 200:
        raise ValueError(f"Donnees insuffisantes : {len(X)} lignes.")

    split_idx = int(len(X) * (1 - ML_TEST_SIZE))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"[{ticker}] Train={len(X_train)} Test={len(X_test)} | dist 0:{(y_train==0).sum()} 1:{(y_train==1).sum()}")

    # Sélection des 30 features les plus importantes
    X_train, X_test = _select_features(X_train, y_train, X_test, k=30)

    candidates = []  # (model, test_acc, prec_hc, cv_score, final_score, name)

    # ── GradientBoosting ──────────────────────────────────────────────────────
    logger.info(f"[{ticker}] GradientBoosting — {len(_GB_PARAMS)} configs...")
    gb_best_p, gb_best_cv = None, -1
    for p in _GB_PARAMS:
        cv = _cv_score(GradientBoostingClassifier, p, X_train, y_train)
        if cv > gb_best_cv:
            gb_best_cv, gb_best_p = cv, p

    # class_weight via sample_weight pour GradientBoosting (ne supporte pas class_weight nativement)
    from sklearn.utils.class_weight import compute_sample_weight
    _sw = compute_sample_weight("balanced", y_train)
    gb = GradientBoostingClassifier(**gb_best_p, random_state=ML_RANDOM_STATE)
    gb.fit(X_train, y_train, sample_weight=_sw)
    gb_acc  = accuracy_score(y_test, gb.predict(X_test))
    gb_prec = _precision_at_confidence(gb, X_test, y_test)
    gb_fs   = 0.4 * gb_acc + 0.6 * gb_prec
    logger.info(f"[{ticker}] GB: acc={gb_acc:.4f} prec_hc={gb_prec:.4f} cv={gb_best_cv:.4f} score={gb_fs:.4f}")
    candidates.append((gb, gb_acc, gb_prec, gb_best_cv, gb_fs, "GradientBoosting"))

    # ── RandomForest ──────────────────────────────────────────────────────────
    logger.info(f"[{ticker}] RandomForest — {len(_RF_PARAMS)} configs...")
    rf_best_p, rf_best_cv = None, -1
    for p in _RF_PARAMS:
        cv = _cv_score(RandomForestClassifier, p, X_train, y_train)
        if cv > rf_best_cv:
            rf_best_cv, rf_best_p = cv, p

    rf = RandomForestClassifier(**rf_best_p, random_state=ML_RANDOM_STATE,
                                 n_jobs=-1, class_weight="balanced")
    rf.fit(X_train, y_train)
    rf_acc  = accuracy_score(y_test, rf.predict(X_test))
    rf_prec = _precision_at_confidence(rf, X_test, y_test)
    rf_fs   = 0.4 * rf_acc + 0.6 * rf_prec
    logger.info(f"[{ticker}] RF: acc={rf_acc:.4f} prec_hc={rf_prec:.4f} cv={rf_best_cv:.4f} score={rf_fs:.4f}")
    candidates.append((rf, rf_acc, rf_prec, rf_best_cv, rf_fs, "RandomForest"))

    # ── XGBoost ───────────────────────────────────────────────────────────────
    xgb = _try_xgboost(X_train, y_train, X_test, y_test)
    if xgb:
        candidates.append(xgb)

    # ── LightGBM ──────────────────────────────────────────────────────────────
    lgbm = _try_lightgbm(X_train, y_train, X_test, y_test)
    if lgbm:
        candidates.append(lgbm)

    # Sélection par score final (40% acc + 60% précision haute confiance)
    candidates.sort(key=lambda c: c[4], reverse=True)
    best_model, best_acc, best_prec, best_cv, best_fs, best_name = candidates[0]

    logger.info(f"[{ticker}] === MEILLEUR : {best_name} ===")
    logger.info(f"[{ticker}]   acc={best_acc:.4f}  prec_hc={best_prec:.4f}  cv={best_cv:.4f}  score={best_fs:.4f}")

    # Assigner les métadonnées AVANT joblib.dump pour qu'elles soient sauvegardées
    best_model._nexora_accuracy    = best_acc
    best_model._nexora_prec_hc     = best_prec
    best_model._nexora_model_type  = best_name
    best_model._nexora_feature_cols = list(X_train.columns)

    model_path = MODEL_STORE_DIR / f"{ticker}_rf_model.joblib"
    joblib.dump(best_model, model_path)
    logger.success(f"[{ticker}] Sauvegarde {model_path} | {best_name} acc={best_acc:.4f} prec@{CONFIDENCE_THRESHOLD:.0%}={best_prec:.4f}")
    return best_model
