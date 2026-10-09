"""Поправка общего фактора по макросигналам, выученная на ряде России.

Разложение ошибки (10_layers.py) показало, что общий слой — главный резерв:
39—46 % MAE на 3—6 месяцах. Фактор панели прогнозируется правилом
«тот же месяц год назад плюс средний рост г/г за три месяца». У панели
24 месяца, учить поправку к правилу на ней не на чем. Поэтому то же правило
прогоняется на общероссийском ряду СберИндекса с 2018 года, и его ошибка
учится по сигналам, известным на дату прогноза:

* изменение ключевой ставки за три месяца и реальная ставка;
* изменение базовой инфляции за три месяца;
* ускорение фонда оплаты труда («Все отрасли», лаг публикации два месяца).

Годы ковидной базы (цели 2020-03…2022-02) исключены. Обучение для точки T
только на целях не позже T. Выученная поправка переносится на группы
панели по категории ряда России; сила (0, 0,5, 1) выбирается на целях
до мая 2024 года, отчёт — по точкам с июня, как у ансамбля.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.config import load as load_cfg  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]


def signals(nat: pd.DataFrame) -> pd.DataFrame:
    fot = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    fot = fot[fot.activity == "Все отрасли"].copy()
    fot["period"] = (pd.to_datetime(fot.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    f = np.log(fot.groupby("period").value.mean())
    fyoy = (f - f.shift(12))
    s = pd.DataFrame(index=nat.index)
    s["d_rate"] = nat.key_rate_cmi - nat.key_rate_cmi.shift(3)
    s["real_rate"] = nat.real_key_rate
    s["d_core"] = nat.core_inflation_3m - nat.core_inflation_3m.shift(3)
    acc = (fyoy - fyoy.shift(3)).reindex(s.index)
    s["fot_acc"] = acc.shift(2)          # месяц T знает фонд по T−2
    return s


def rule_errors(nat: pd.DataFrame, col: str) -> pd.DataFrame:
    """Ошибка правила фактора на ряде России: прогноз − факт, в логарифмах."""
    s = np.log(nat[col].dropna())
    p = list(s.index)
    rows = []
    for i in range(24, len(p)):
        gr = np.mean([s.iloc[i - j] - s.iloc[i - j - 12] for j in range(3)])
        for h in range(1, 13):
            if i + h >= len(p):
                break
            rows.append({"origin": p[i], "step": h, "target": p[i + h],
                         "err": s.iloc[i + h - 12] + gr - s.iloc[i + h]})
    e = pd.DataFrame(rows)
    covid = lambda x: (x >= "2020-03") & (x <= "2022-02")
    return e[~covid(e.target) & ~covid(e.origin)]


def main():
    cfg = load_cfg()
    ntype = cfg["models"]["snaive_growth"]["national_type"]
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    sig = signals(nat)
    feats = list(sig.columns)
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    origins = sorted(pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet", columns=["origin"]).origin.unique())

    adj, coefs = [], []
    for k in sorted(set(ntype.values())):
        e = rule_errors(nat, f"spend_bn:{k}").merge(sig, left_on="origin", right_index=True).dropna()
        for o in origins:
            tr = e[e.target <= o]
            X = np.c_[np.ones(len(tr)), tr[feats].to_numpy(), tr.step.to_numpy() / 12]
            mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-9
            Z = np.c_[X[:, :1], (X[:, 1:] - mu) / sd]
            lam = 5.0 * len(tr) / 100        # гребневая регуляризация, коэффициент ставится заранее
            beta = np.linalg.solve(Z.T @ Z + lam * np.diag([0] + [1] * (Z.shape[1] - 1)), Z.T @ tr.err.to_numpy())
            coefs.append({"type": k, "origin": o, "n": len(tr), **dict(zip(["const"] + feats + ["h"], beta.round(4)))})
            x0 = sig.loc[o, feats].to_numpy(float)
            for h in range(1, 13):
                z = np.r_[1, (np.r_[x0, h / 12] - mu) / sd]
                adj.append({"type": k, "origin": o, "step": h, "pred_err": float(z @ beta)})
    adj = pd.DataFrame(adj)
    pd.DataFrame(coefs).to_csv(OUT / "factor_model_coefs.csv", index=False)

    nowc = pd.read_csv(OUT / "factor_adjustments.csv")[["origin", "step", "category", "now"]]
    k_now = {"Все категории": 1.0, "Продовольствие": 1.0, "Общественное питание": 1.0,
             "Здоровье": 1.0, "Маркетплейсы": 0.0, "Транспорт": 0.0}   # из 11_factor_signals.py, окно выбора
    rows = []
    for name in ["panel_blend_ses_bytype", "ensemble"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["category"] = cats[f.row.to_numpy()]
        f["type"] = f.category.map(ntype)
        f = f.merge(adj, on=["type", "origin", "step"], how="left").merge(nowc, on=["origin", "step", "category"], how="left")
        f = f.fillna({"pred_err": 0.0, "now": 0.0})
        sel = f[f.target <= "2024-05"]
        mae = {s: (sel.yhat * np.exp(-s * sel.pred_err) - sel.y).abs().mean() for s in (0.0, 0.5, 1.0)}
        s_best = min(mae, key=mae.get)
        print(name, "сила макропоправки на окне выбора:", {k: round(v, 1) for k, v in mae.items()}, "→", s_best)
        for v, a in {"macro": -s_best * f.pred_err, "macro+now": -s_best * f.pred_err + f.category.map(k_now) * f.now,
                     "macro_full": -1.0 * f.pred_err}.items():
            g = f.assign(yhat=f.yhat * np.exp(a))
            g[COLS].to_parquet(OUT / f"fc_{name}+{v}.parquet")
            for H in (1, 3, 6):
                r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
                rows.append({"base": name, "variant": v, "strength": s_best if v != "macro_full" else 1.0, **r})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "factor_model.csv", index=False)
    pd.set_option("display.width", 220)
    print(pd.DataFrame(coefs).groupby("type")[["n"] + feats + ["h"]].last().round(3).to_string())
    print(res[["base", "variant", "strength", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
