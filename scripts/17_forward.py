"""Шаг 17. Прогноз вперёд: 2025—2027 годы от последней точки истории (декабрь 2024).

Те же модели, что в бэктесте, но точка прогона — последний известный месяц,
шагов тридцать шесть. Модель, которая дальше года не считается, остаётся с тем, что посчитала. Месяцы за концом истории модели получают из рядов РФ
и календаря: сезонность панели — по месяцу, рабочие дни — из national.parquet.
Ансамбль — тот же, что выбран в шаге 4.

    python scripts/17_forward.py
    python scripts/17_forward.py --models panel_blend_sesseas_bytype snaive_growth
    python scripts/17_forward.py --ensemble-only     # только свёртка из уже посчитанных членов

Прогнозы — results/forecasts_forward/<модель>.parquet: row, target, yhat (у Chronos-2 ещё q05, q95).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.ensemble import combine_stack, selection  # noqa: E402
from sbi.models import baselines, foundation, gbm, panel as panel_models, prophet_model  # noqa: E402

OUT = ROOT / "results" / "forecasts_forward"
STEPS = 36   # три года: 2025—2027; дальше 12 месяцев точность не измерить, только оценить
DEFAULT = ["snaive_growth", "panel_blend_sesseas_bytype", "panel_blend_ses_bytype", "prophet_default", "lgbm", "chronos2_dev"]


def future(periods, steps):
    y, m = map(int, periods[-1].split("-"))
    out = []
    for _ in range(steps):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        out.append(f"{y}-{m:02d}")
    return out


def main():
    cfg, args = config.cli(__doc__, lambda ap: (ap.add_argument("--models", nargs="*", default=None),
                                                ap.add_argument("--ensemble-only", action="store_true")))
    if args.ensemble_only:
        return ensemble_forward({})
    bt = cfg["backtest"]
    P = cfg.path("processed")
    panel = backtest.load_panel(P, bt["series"])
    t0 = len(panel.periods) - 1
    ext = panel.periods + future(panel.periods, STEPS)
    bt3 = __import__("03_backtest")
    # Рост РФ г/г на точку прогона: за концом рядов РФ — последний известный.
    nat_all = pd.read_parquet(P / "national.parquet").set_index("period")
    types = panel.index.category.astype(str).map(cfg["models"]["snaive_growth"]["national_type"]).to_numpy()

    def national_growth(t0):
        period = ext[t0] if t0 < len(ext) else ext[-1]
        rows = nat_all.loc[:period]
        return np.array([1 + rows[f"spend_yoy_nominal:{t}"].dropna().iloc[-1] / 100 for t in types])
    ctx = dict(cfg["models"]["snaive_growth"], national_growth=national_growth)
    mo = pd.read_parquet(P / "mo.parquet")
    nat = pd.read_parquet(P / "national.parquet").set_index("period")
    pctx = {"groups": {"category": panel_models.groups(panel.index, mo, "category"),
                       "type": panel_models.groups(panel.index, mo, "type")},
            "periods": ext, "national": nat}
    pmodels = panel_models.variants(pctx)
    OUT.mkdir(parents=True, exist_ok=True)
    targets = ext[t0 + 1:]

    def save(name, yhat, lo=None, hi=None):
        n = yhat.shape[0]
        f = pd.DataFrame({"row": np.repeat(np.arange(n), STEPS), "target": np.tile(targets, n), "yhat": yhat.ravel()})
        if lo is not None:
            f["q05"], f["q95"] = lo.ravel(), hi.ravel()
        f.to_parquet(OUT / f"{name}.parquet", index=False)

    done = {}
    for name in args.models or DEFAULT:
        t = time.time()
        store = {}
        if name.startswith("prophet_"):
            model = prophet_model.make(cfg["models"]["prophet"][name[8:]], panel.periods, bt["workers"])
        elif name in pmodels:
            model = pmodels[name]
        elif name.startswith("chronos2_"):
            if "pipe" not in pctx:
                pctx["pipe"] = foundation.load()
            wd = nat["workdays"].dropna().to_dict()
            model = foundation.make(pctx["pipe"], name[9:], pmodels[cfg["models"]["lgbm_base"]],
                                    pctx["groups"]["type"], wd, ext, store=store)
        elif name == "lgbm":
            nb = pd.read_parquet(P / "neighbours.parquet")
            regional = pd.read_parquet(P / "regional.parquet")
            gctx = gbm.context(panel, mo, nb, regional, nat.reset_index(), pmodels[cfg["models"]["lgbm_base"]],
                               ctx, pctx["groups"]["type"])
            gctx["params"] = dict(cfg["models"]["lgbm"]["params"])
            model = gbm.make(gctx)
        else:
            model = baselines.MODELS[name]
        # Год за годом: прогноз года дописывается к истории, и от его конца считается следующий.
        # Дальше первого года это прогноз по прогнозу — его точность оценивается, а не измеряется.
        hist, blocks = panel.y, []
        for b in range(STEPS // 12):
            try:
                blk = np.asarray(model(hist, hist.shape[1] - 1, 12, ctx), float)
            except Exception as e:                   # модель, которой нечем смотреть дальше
                print(f"· {name}: год {b + 1} не считается — {type(e).__name__}: {e}")
                break
            blocks.append(blk)
            hist = np.hstack([hist, blk])
        if not blocks:
            continue
        yhat = np.hstack(blocks)
        if yhat.shape[1] < STEPS:                    # дальше года — пусто, а не повтор
            yhat = np.hstack([yhat, np.full((yhat.shape[0], STEPS - yhat.shape[1]), np.nan)])
        lo, hi = store.get(ext[t0], (None, None))
        pad = lambda a: None if a is None else np.hstack([a[:, :STEPS], np.full((a.shape[0], max(0, STEPS - a.shape[1])), np.nan)])
        save(name, yhat, pad(lo), pad(hi))
        done[name] = yhat
        print(f"· {name}: {time.time() - t:.0f} с")

    ensemble_forward(done)


def ensemble_forward(done: dict):
    """Ансамбль вперёд — тот же состав и та же свёртка, что выбраны в шаге 4 (sbi.ensemble)."""
    members, how = selection(ROOT / "results" / "metrics" / "ensemble_selection.csv")
    missing = [m for m in members if m not in done and not (OUT / f"{m}.parquet").exists()]
    if missing:
        print(f"· ensemble не собран: нет прогнозов вперёд у {missing}")
        return
    frames = {m: done[m] if m in done else pd.read_parquet(OUT / f"{m}.parquet") for m in members}
    first = frames[members[0]] if isinstance(frames[members[0]], pd.DataFrame) else pd.read_parquet(OUT / f"{members[0]}.parquet")
    targets = list(first.target.unique()) if isinstance(first, pd.DataFrame) else None
    # Члены складываются позиционно: ключи row и target у всех обязаны совпадать.
    for m, f in frames.items():
        if isinstance(f, pd.DataFrame):
            assert f.row.to_numpy().tolist() == first.row.to_numpy().tolist() and f.target.to_numpy().tolist() == first.target.to_numpy().tolist(), f"порядок строк у {m} отличается от {members[0]}"
    stack = np.stack([f if isinstance(f, np.ndarray) else f.yhat.to_numpy().reshape(-1, len(targets)) for f in frames.values()], axis=-1)
    ens = combine_stack(stack, how)
    steps = ens.shape[1]
    n = ens.shape[0]
    pd.DataFrame({"row": np.repeat(np.arange(n), steps), "target": np.tile(targets, n), "yhat": ens.ravel()}).to_parquet(OUT / "ensemble.parquet", index=False)
    print(f"· ensemble: {'+'.join(members)} ({how}), {n} рядов × {steps} шагов")


if __name__ == "__main__":
    main()
