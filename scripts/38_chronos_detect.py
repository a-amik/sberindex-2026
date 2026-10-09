"""Детектор на интервале Chronos-2 — седьмой метод полусинтетического стенда.

Идея из решения другого участника конкурса. В месяце t Chronos-2 с
кросс-обучением прогнозирует на шаг вперёд отклонение МО от фактора группы
по истории до t−1. Балл — расстояние факта от медианы в долях полуширины
интервала 0,05—0,95, то есть онлайн, по данным до t. Выборки, порог по F1
настроечной выборки и оценка — те же, что у 05_detect.py; рядом стоят
z-оценка, коридор прогноза и согласие с z-оценкой.

    python scripts/38_chronos_detect.py
Выход — results/metrics/detect_chronos.csv; баллы кэшируются
в results/signal_value/chronos_detect_<выборка>.npy.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, config, detect  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

CACHE = ROOT / "results/signal_value"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def chronos_scores(d: np.ndarray, pipe, start: int, batch: int = 256) -> np.ndarray:
    from sbi.models import foundation
    n, T = d.shape
    out = np.zeros((n, T))
    for t in range(start, T):
        t0 = time.time()
        mid, lo, hi = foundation._median(pipe, [d[i, :t] for i in range(n)], 1, True, batch)
        half = np.maximum((hi[:, 0] - lo[:, 0]) / 2, 1e-4)
        out[:, t] = np.abs(d[:, t] - mid[:, 0]) / half
        print(f"  месяц {t}: {time.time() - t0:.0f} с", flush=True)
    return out


def main():
    cfg = config.load()
    dc = cfg["detect"]
    P = cfg.path("processed")
    det = load("05_detect")
    panel = backtest.load_panel(P, "full")
    mo = pd.read_parquet(P / "mo.parquet")
    groups = panel_models.groups(panel.index, mo, "type")
    nb_rows = det.neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))
    pipe = None
    draws = {}
    for tag, seed in (("tune", dc["seed_tune"]), ("test", dc["seed_test"])):
        rng = np.random.default_rng(seed)
        y2, truth = detect.inject(panel.y, rng, dc["share"], dc["sizes"], dc["kinds"], dc["first"], dc["last"])
        d = detect.signal(y2, groups)
        f = CACHE / f"chronos_detect_{tag}.npy"
        if f.exists():
            sc_c = np.load(f)
        else:
            if pipe is None:
                from sbi.models import foundation
                pipe = foundation.load()
            sc_c = chronos_scores(d, pipe, detect.MIN_HIST)
            np.save(f, sc_c)
        sc = {m: detect.run_online(d, groups, nb_rows, m) for m in ("zscore", "forecast")}
        sc["chronos"] = sc_c
        draws[tag] = (truth, sc)
    (t_tune, s_tune), (t_test, s_test) = draws["tune"], draws["test"]
    rows, chosen = [], {}
    ev = lambda a: detect.evaluate(a, t_test, dc["first"], dc["max_delay"])
    for m in ("zscore", "forecast", "chronos"):
        f1, th = max((detect.evaluate(s_tune[m] > th, t_tune, dc["first"], dc["max_delay"])["f1"], th)
                     for th in det.thresholds(s_tune[m], dc["first"]))
        chosen[m] = th
        rows.append({"method": m, "threshold": th, "f1_tune": f1, **ev(s_test[m] > th)})
    for a, b in (("zscore", "chronos"), ("forecast", "chronos")):
        rows.append({"method": f"{a}&{b}", **ev(detect.agree(s_test[a] > chosen[a], s_test[b] > chosen[b]))})
    tab = pd.DataFrame(rows).drop(columns=["recall_by"])
    tab.to_csv(ROOT / "results/metrics/detect_chronos.csv", index=False)
    pd.set_option("display.width", 220)
    cols = ["method", "recall", "precision", "f1", "fa_per_100", "delay_mean", "recall_over_random"]
    print(tab[[c for c in cols if c in tab]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
