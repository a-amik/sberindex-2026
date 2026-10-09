"""Шаг 3. Скользящий бэктест прогнозов и сравнение с базовой моделью.

    python scripts/03_backtest.py                              эталоны и Prophet
    python scripts/03_backtest.py --models naive snaive        названные
    python scripts/03_backtest.py --grid                       чувствительность Prophet
                                                               к настройкам на выборке рядов
    python scripts/03_backtest.py --report                     только пересчитать таблицы

Прогнозы ложатся в results/forecasts/ (в git не идут), таблицы метрик —
в results/metrics/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config, metrics  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import baselines, foundation, gbm, panel as panel_models, prophet_model  # noqa: E402

OUT = ROOT / "results"


def national_growth(cfg, panel):
    nat = pd.read_parquet(cfg.path("processed") / "national.parquet").set_index("period")
    types = panel.index.category.astype(str).map(cfg["models"]["snaive_growth"]["national_type"]).to_numpy()

    def g(t0):
        period = panel.periods[t0]
        row = nat.loc[period]
        return np.array([1 + row[f"spend_yoy_nominal:{t}"] / 100 for t in types])
    return g


def sample_rows(panel, per_category, seed):
    rng = np.random.default_rng(seed)
    idx = []
    for _, g in panel.index.groupby("category", observed=True):
        idx += list(rng.choice(g.index.to_numpy(), min(per_category, len(g)), replace=False))
    idx = sorted(idx)
    return backtest.Panel(y=panel.y[idx], periods=panel.periods, index=panel.index.iloc[idx].reset_index(drop=True))


def save(name, f, folder):
    folder.mkdir(parents=True, exist_ok=True)
    f.to_parquet(folder / f"{name}.parquet", index=False)


def report(cfg, panel, folder, tag):
    bt = cfg["backtest"]
    last = panel.periods[-1]
    fc = {p.stem: pd.read_parquet(p) for p in sorted(folder.glob("*.parquet"))}
    if not fc:
        return
    tab = metrics.table(fc, bt["horizons"], last)
    mdir = OUT / "metrics"
    mdir.mkdir(parents=True, exist_ok=True)
    tab.to_csv(mdir / f"{tag}_by_horizon.csv", index=False)

    cats = panel.index.category.astype(str).to_numpy()
    rows = []
    for name, f in fc.items():
        for H in bt["horizons"]:
            d = metrics.horizon_rows(f, H, last)
            for c, g in d.groupby(cats[d.row.to_numpy()]):
                rows.append({"model": name, "H": H, "category": c, **metrics.scores(g)})
    pd.DataFrame(rows).to_csv(mdir / f"{tag}_by_category.csv", index=False)

    ref = bt["reference"] if bt["reference"] in fc else "default"
    if ref in fc:
        cmp_rows = [{"model": n, **metrics.compare(f, fc[ref], H, last, bt["bootstrap"], bt["seed"])}
                    for n, f in fc.items() if n != ref for H in bt["horizons"]]
        pd.DataFrame(cmp_rows).to_csv(mdir / f"{tag}_vs_{ref}.csv", index=False)

    piv = tab.pivot(index="model", columns="H", values="MAE").round(1)
    piv = piv.sort_values(piv.columns[0])
    print(f"\nMAE, руб. на жителя ({tag}, рядов {panel.y.shape[0]:,}):")
    print(piv.to_string())
    r2 = tab.pivot(index="model", columns="H", values="R2_growth").round(3).loc[piv.index]
    print("\nR² прироста:")
    print(r2.to_string())


def main():
    cfg, args = config.cli(__doc__, lambda ap: (
        ap.add_argument("--models", nargs="*", default=None),
        ap.add_argument("--grid", action="store_true"),
        ap.add_argument("--report", action="store_true")))
    bt = cfg["backtest"]
    panel = backtest.load_panel(cfg.path("processed"), bt["series"])
    ctx = dict(cfg["models"]["snaive_growth"], national_growth=national_growth(cfg, panel))

    if args.grid:
        sub = sample_rows(panel, cfg["models"]["prophet_grid"]["sample_per_category"], bt["seed"])
        sub_ctx = dict(ctx, national_growth=national_growth(cfg, sub))
        folder = OUT / "forecasts_grid"
        if not args.report:
            for name, pcfg in cfg["models"]["prophet_grid"]["configs"].items():
                if (folder / f"{name}.parquet").exists():   # посчитанное не пересчитываем
                    continue
                print(f"· prophet {name}")
                save(name, backtest.run(prophet_model.make(pcfg, sub.periods, bt["workers"]), sub,
                                        bt["first_origin"], bt["last_origin"], sub_ctx), folder)
            for name in ("snaive", "snaive_growth"):
                save(name, backtest.run(baselines.MODELS[name], sub, bt["first_origin"], bt["last_origin"],
                                        sub_ctx), folder)
        report(cfg, sub, folder, "prophet_grid")
        return

    folder = OUT / "forecasts"
    if not args.report:
        mo = pd.read_parquet(cfg.path("processed") / "mo.parquet")
        nat = pd.read_parquet(cfg.path("processed") / "national.parquet").set_index("period")
        pctx = {"groups": {"category": panel_models.groups(panel.index, mo, "category"),
                           "type": panel_models.groups(panel.index, mo, "type")},
                "periods": panel.periods, "national": nat}
        pmodels = panel_models.variants(pctx)
        names = args.models or (list(baselines.MODELS) + [f"prophet_{k}" for k in cfg["models"]["prophet"]]
                                + list(pmodels))
        for name in names:
            print(f"· {name}")
            if name.startswith("prophet_"):
                model = prophet_model.make(cfg["models"]["prophet"][name[8:]], panel.periods, bt["workers"])
            elif name in pmodels:
                model = pmodels[name]
            elif name.startswith(("chronos2_", "chronosbolt_")):
                key = "bolt" if name.startswith("chronosbolt_") else "pipe"
                if key not in pctx:
                    pctx[key] = foundation.load("amazon/chronos-bolt-base" if key == "bolt" else "amazon/chronos-2")
                wd = nat["workdays"].dropna().to_dict()
                store = {}
                model = foundation.make(pctx[key], name.split("_", 1)[1], pmodels[cfg["models"]["lgbm_base"]],
                                        pctx["groups"]["type"], wd, panel.periods, store=store)
            elif name == "lgbm":
                nb = pd.read_parquet(cfg.path("processed") / "neighbours.parquet")
                regional = pd.read_parquet(cfg.path("processed") / "regional.parquet")
                gctx = gbm.context(panel, mo, nb, regional, nat.reset_index(), pmodels[cfg["models"]["lgbm_base"]],
                                   ctx, pctx["groups"]["type"])
                gctx["params"] = dict(cfg["models"]["lgbm"]["params"])
                model = gbm.make(gctx)
            else:
                model = baselines.MODELS[name]
            f = backtest.run(model, panel, bt["first_origin"], bt["last_origin"], ctx)
            if name.startswith(("chronos2_", "chronosbolt_")):   # интервалы — для детектора шоков
                lo = np.concatenate([store[o][0][:, :s].ravel(order="F") for o, s in
                                     f.groupby("origin", sort=False).step.max().items()])
                hi = np.concatenate([store[o][1][:, :s].ravel(order="F") for o, s in
                                     f.groupby("origin", sort=False).step.max().items()])
                f["q05"], f["q95"] = lo, hi
            save(name, f, folder)
    report(cfg, panel, folder, "forecast")


if __name__ == "__main__":
    main()
