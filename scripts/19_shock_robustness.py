"""Шаг 19. Как модели прогноза переживают шок.

В долю рядов вписывается шок — так же, как в бенчмарке детекторов (detect.inject,
те же доли, величины и виды). Модели заново проходят скользящий бэктест на
изменённой панели. Сравнивается ошибка на шаг вперёд в рядах с шоком в месяцы
τ…τ+5 — с шоком и без него: насколько шок сбивает модель и как быстро она
возвращается.

    python scripts/19_shock_robustness.py
    python scripts/19_shock_robustness.py --models snaive_growth panel_blend_sesseas_bytype

Итог — results/metrics/shock_robustness.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config, detect  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import baselines, foundation, panel as panel_models, prophet_model  # noqa: E402

DEFAULT = ["snaive_growth", "panel_blend_sesseas_bytype", "chronos2_dev", "prophet_default"]
AFTER = 6


def main():
    cfg, args = config.cli(__doc__, lambda ap: ap.add_argument("--models", nargs="*", default=None))
    bt, dc = cfg["backtest"], cfg["detect"]
    P = cfg.path("processed")
    panel = backtest.load_panel(P, bt["series"])
    rng = np.random.default_rng(dc["seed_test"])
    y2, truth = detect.inject(panel.y, rng, dc["share"], dc["sizes"], dc["kinds"], dc["first"], dc["last"])
    shocked = backtest.Panel(y=y2, periods=panel.periods, index=panel.index)
    bt3 = __import__("03_backtest")
    mo = pd.read_parquet(P / "mo.parquet")
    nat = pd.read_parquet(P / "national.parquet").set_index("period")
    pctx = {"groups": {"category": panel_models.groups(panel.index, mo, "category"),
                       "type": panel_models.groups(panel.index, mo, "type")},
            "periods": panel.periods, "national": nat}
    pmodels = panel_models.variants(pctx)
    tau, kind = truth["tau"], truth["kind"]
    hit = np.where(tau >= 0)[0]
    out_path = ROOT / "results" / "metrics" / "shock_robustness.json"
    res = json.loads(out_path.read_text()) if out_path.exists() else {}
    preds = {}

    for name in args.models or DEFAULT:
        if name.startswith("prophet_"):
            model = prophet_model.make(cfg["models"]["prophet"][name[8:]], panel.periods, bt["workers"])
        elif name in pmodels:
            model = pmodels[name]
        elif name.startswith("chronos2_"):
            pctx.setdefault("pipe", foundation.load())
            model = foundation.make(pctx["pipe"], name[9:], pmodels[cfg["models"]["lgbm_base"]], pctx["groups"]["type"],
                                    nat["workdays"].dropna().to_dict(), panel.periods, store={})
        else:
            model = baselines.MODELS[name]
        ctx = dict(cfg["models"]["snaive_growth"], national_growth=bt3.national_growth(cfg, shocked))
        f = backtest.run(model, shocked, bt["first_origin"], bt["last_origin"], ctx)
        f = f[f.step == 1]
        preds[name] = f
        base = pd.read_parquet(ROOT / "results" / "forecasts" / f"{name}.parquet")
        base = base[base.step == 1].set_index(["row", "target"]).yhat
        res[name] = summarize(f, base, panel, tau, kind, hit)
        print(f"· {name}: рост ошибки {res[name]['rise']:+.0%}")

    # Ансамбль — как в шаге 4, из своих членов.
    sel = pd.read_csv(ROOT / "results" / "metrics" / "ensemble_selection.csv").iloc[0]
    members = sel.members.split("+")
    if all(m in preds for m in members):
        f = preds[members[0]].copy()
        stack = np.column_stack([preds[m].sort_values(["row", "origin"]).yhat.to_numpy() for m in members])
        f = f.sort_values(["row", "origin"])
        f["yhat"] = np.exp(np.log(stack).mean(axis=1)) if sel.how == "geo" else stack.mean(axis=1)
        base = pd.read_parquet(ROOT / "results" / "forecasts" / "ensemble.parquet")
        base = base[base.step == 1].set_index(["row", "target"]).yhat
        res["ensemble"] = summarize(f, base, panel, tau, kind, hit)
        print(f"· ensemble: рост ошибки {res['ensemble']['rise']:+.0%}")
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(out_path)


def summarize(f, base, panel, tau, kind, hit):
    """MAE на шаг вперёд в рядах с шоком, месяцы τ…τ+5: с шоком против исходной панели."""
    pidx = {p: i for i, p in enumerate(panel.periods)}
    f = f[f.row.isin(hit)].copy()
    f["t"] = f.target.map(pidx)
    f["k"] = f.t - tau[f.row.to_numpy()]
    f = f[(f.k >= 0) & (f.k < AFTER)]
    f["base"] = base.reindex(pd.MultiIndex.from_arrays([f.row, f.target])).to_numpy()
    f["y0"] = panel.y[f.row.to_numpy(), f.t.to_numpy()]
    f["e1"] = (f.yhat - f.y).abs()          # ошибка на ряде с шоком
    f["e0"] = (f.base - f.y0).abs()         # та же точка без шока
    by_k = f.groupby("k")[["e1", "e0"]].mean()
    by_kind = f.assign(kind=kind[f.row.to_numpy()]).groupby("kind")[["e1", "e0"]].mean()
    return {
        "mae_shock": float(f.e1.mean()), "mae_base": float(f.e0.mean()), "rise": float(f.e1.mean() / f.e0.mean() - 1),
        "by_month": [float(r.e1 / r.e0 - 1) for r in by_k.itertuples()],
        "by_kind": {k: float(r.e1 / r.e0 - 1) for k, r in zip(by_kind.index, by_kind.itertuples())},
        "n": int(len(f)),
    }


if __name__ == "__main__":
    main()
