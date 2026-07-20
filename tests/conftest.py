"""Fixtures partagées entre tous les tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Permet l'import depuis la racine du projet
sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Génère un DataFrame OHLCV synthétique de 100 barres."""
    rng = np.random.default_rng(42)
    n = 100
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=dates,
    )
    df.index.name = "Date"
    return df
