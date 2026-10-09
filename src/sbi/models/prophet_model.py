"""Prophet по каждому ряду и каждой точке прогноза, параллельно по рядам."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd


def _quiet():
    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    logging.getLogger("prophet").setLevel(logging.ERROR)
    import warnings
    warnings.filterwarnings("ignore")


def _fit_rows(args):
    rows, periods, t0, steps, cfg = args
    _quiet()
    from prophet import Prophet
    cfg = dict(cfg)
    log = cfg.pop("log", False)
    ds = pd.to_datetime([p + "-01" for p in periods[: t0 + 1]])
    out = np.empty((len(rows), steps))
    for i, y in enumerate(rows):
        yy = np.log(y) if log else y
        df = pd.DataFrame({"ds": ds, "y": yy})
        m = Prophet(weekly_seasonality=False, daily_seasonality=False, **cfg)
        m.fit(df)
        fut = m.make_future_dataframe(steps, freq="MS", include_history=False)
        p = m.predict(fut).yhat.to_numpy()
        out[i] = np.exp(p) if log else p
    return out


def make(cfg: dict, periods: list[str], workers: int):
    def model(hist, t0, steps, ctx):
        chunks = np.array_split(np.arange(hist.shape[0]), workers * 4)
        tasks = [(hist[c], periods, t0, steps, cfg) for c in chunks if len(c)]
        with ProcessPoolExecutor(workers, initializer=_quiet) as ex:
            parts = list(ex.map(_fit_rows, tasks))
        return np.vstack(parts)
    return model
