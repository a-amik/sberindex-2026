"""Шаг 4. Ансамбль прогнозов и честная проверка выбора.

Кандидаты и способ свёртки выбираются на окне отбора — все пары «ряд ×
точка × шаг», цель которых не позже мая 2024 года. Отчёт — по всем точкам
и отдельно по отчётному окну, точки июнь—ноябрь 2024 года: ни одна их цель
при выборе не использовалась.

    python scripts/04_ensemble.py
"""
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config, metrics  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.ensemble import HOW, combine  # noqa: E402

FC = ROOT / "results" / "forecasts"


def main():
    cfg, _ = config.cli(__doc__)
    ens = cfg["ensemble"]
    last = "2024-12"
    pool = {n: pd.read_parquet(FC / f"{n}.parquet") for n in ens["candidates"]}
    sel = lambda f: f[f.target <= ens["select_last_target"]]

    rows = []
    for k in range(1, len(pool) + 1):
        for names in combinations(pool, k):
            for how in (list(HOW) if k > 1 else ["single"]):
                f = pool[names[0]] if k == 1 else combine([pool[n] for n in names], how)
                rows.append({"members": "+".join(names), "how": how,
                             "select_MAE": float((sel(f).yhat - sel(f).y).abs().mean())})
    choice = pd.DataFrame(rows).sort_values("select_MAE")
    out = ROOT / "results" / "metrics"
    choice.to_csv(out / "ensemble_selection_free.csv", index=False)       # отбор без обязательных
    must = ens.get("force_include") or []
    if must:
        choice = choice[choice.members.str.split("+").apply(lambda m: all(x in m for x in must))]
    choice.to_csv(out / "ensemble_selection.csv", index=False)
    best = choice.iloc[0]
    print(f"Окно отбора, цели до {ens['select_last_target']} (лучшие пять):")
    print(choice.head(5).round(1).to_string(index=False))

    names = best.members.split("+")
    f = pool[names[0]] if best.how == "single" else combine([pool[n] for n in names], best.how)
    f.to_parquet(FC / "ensemble.parquet", index=False)

    ref = pd.read_parquet(FC / f"{cfg['backtest']['reference']}.parquet")
    rep = lambda d: d[d.origin >= ens["report_from"]]
    tab = []
    for H in cfg["backtest"]["horizons"]:
        for name, g in [("ensemble", f), *pool.items(), ("prophet_default", ref)]:
            a = metrics.horizon_rows(g, H, last)
            r = rep(a)
            tab.append({"model": name, "H": H, "MAE_all": a.eval("abs(yhat-y)").mean(),
                        "MAE_report": r.eval("abs(yhat-y)").mean() if len(r) else np.nan})
    tab = pd.DataFrame(tab)
    tab.to_csv(out / "ensemble_by_horizon.csv", index=False)
    print(f"\nВыбран: {best.members} ({best.how})")
    print("\nMAE по всем точкам:")
    print(tab.pivot(index="model", columns="H", values="MAE_all").round(1).to_string())
    print(f"\nMAE по отчётному окну (точки с {ens['report_from']}; на H = 12 таких точек нет):")
    print(tab.pivot(index="model", columns="H", values="MAE_report").round(1).to_string())


if __name__ == "__main__":
    main()
