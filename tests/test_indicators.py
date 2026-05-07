import pandas as pd
import numpy as np
from config.settings import settings
from src.indicators.technical import compute_indicators, directional_bias
from src.indicators.patterns import detect_patterns


def _fake_df(n=200, trend=0.0, seed=42):
    rng = np.random.default_rng(seed)
    base = 1.1000 + np.cumsum(rng.normal(trend, 0.0008, n))
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
        "open": base, "high": base + 0.0005,
        "low": base - 0.0005, "close": base + rng.normal(0, 0.0001, n),
        "volume": rng.integers(50, 200, n),
    })
    return df


def test_indicators_run():
    df = _fake_df()
    snap = compute_indicators(df, "EURUSD", 5, settings.indicators)
    assert snap is not None
    assert 0 <= snap.rsi <= 100


def test_uptrend_bias():
    df = _fake_df(trend=0.0003, seed=1)
    snap = compute_indicators(df, "EURUSD", 5, settings.indicators)
    direction, _ = directional_bias(snap)
    assert direction in ("CALL", "PUT", "NEUTRAL")


def test_patterns_no_crash():
    df = _fake_df()
    detect_patterns(df)
