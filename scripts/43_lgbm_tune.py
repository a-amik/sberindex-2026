"""Подбор параметров LightGBM только на окне отбора.

    python scripts/43_lgbm_tune.py

Перебирает сетку models.lgbm.grid вокруг models.lgbm.params. Каждый вариант
считается на точках прогноза с декабря 2023 по апрель 2024 года, ошибка — по парам,
цель которых не позже мая 2024 года (то же окно, что у отбора ансамбля). Отчётное
окно в подборе не участвует. Таблица — results/metrics/lgbm_tuning.csv; лучший
вариант печатается, его переносят в configs/default.yaml руками.
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from sbi import backtest, config  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import gbm, panel as panel_models  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from importlib import import_module  # noqa: E402

bt_script = import_module("03_backtest")


def main():
    cfg, _ = config.cli(__doc__)
    bt = cfg["backtest"]
    last_target = cfg["ensemble"]["select_last_target"]
    panel = backtest.load_panel(cfg.path("processed"), bt["series"])
    ctx = dict(cfg["models"]["snaive_growth"], national_growth=bt_script.national_growth(cfg, panel))
    proc = cfg.path("processed")
    mo = pd.read_parquet(proc / "mo.parquet")
    nat = pd.read_parquet(proc / "national.parquet").set_index("period")
    pctx = {"groups": {"category": panel_models.groups(panel.index, mo, "category"),
                       "type": panel_models.groups(panel.index, mo, "type")},
            "periods": panel.periods, "national": nat}
    pmodels = panel_models.variants(pctx)
    gctx = gbm.context(panel, mo, pd.read_parquet(proc / "neighbours.parquet"),
                       pd.read_parquet(proc / "regional.parquet"), nat.reset_index(),
                       pmodels[cfg["models"]["lgbm_base"]], ctx, pctx["groups"]["type"])
    # последняя точка, у которой есть цель внутри окна отбора
    last_origin = (pd.Period(last_target, "M") - 1).strftime("%Y-%m")
    base = pmodels[cfg["models"]["lgbm_base"]]
    fb = backtest.run(base, panel, bt["first_origin"], last_origin, ctx)
    fb = fb[fb.target <= last_target]

    grid = cfg["models"]["lgbm"]["grid"]
    keys = list(grid)
    rows = []
    for vals in itertools.product(*(grid[k] for k in keys)):
        params = dict(cfg["models"]["lgbm"]["params"], **dict(zip(keys, vals)))
        gctx["params"] = params
        f = backtest.run(gbm.make(gctx), panel, bt["first_origin"], last_origin, ctx)
        f = f[f.target <= last_target]
        mae = (f.yhat - f.y).abs().mean()
        row = dict(zip(keys, vals), MAE=mae, MAE_base=(fb.yhat - fb.y).abs().mean(), pairs=len(f))
        rows.append(row)
        print({k: row[k] for k in keys}, f"MAE {mae:.2f}", flush=True)
    res = pd.DataFrame(rows).sort_values("MAE")
    res.to_csv(ROOT / "results" / "metrics" / "lgbm_tuning.csv", index=False)
    print("\nлучший вариант на окне отбора:")
    print(res.head(5).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
