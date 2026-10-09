"""Шаг 18. Чувствительность расходов к внешним факторам — для сценариев сервиса.

Ставка. По МО её не оценить: ставка одна на всех, и общий фактор месяца её
съедает. Поэтому — по ряду РФ СберИндекса (2018—2026): годовой прирост расходов
категории против изменения ключевой ставки за год, с лагом и с прошлым приростом
в правой части. Коэффициент — п. п. прироста на 1 п. п. ставки.

Погода. Внутри панели МО: отклонение ряда от медианы своей группы
(категория × город или район) и от собственного среднего — против аномалии
температуры и осадков МО в тот же месяц (тоже за вычетом среднего по всем МО
и собственного среднего). Летние месяцы отдельно: жара летом и зимой — разное.

Рабочие дни. По ряду РФ: месячный прирост расходов против изменения числа
рабочих дней, с месяцем года в правой части.

Паводок. Не регрессия, а разобранный случай весны 2024 года: сдвиг категорий
в субъектах паводка против остальных (results/metrics/real_cases.json).

Ошибки — HAC (Ньюи — Уэст) для рядов РФ и по кластерам субъекта для панели.

    python scripts/18_sensitivity.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402

from sbi import config  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

CATS = ["Все категории", "Продовольствие", "Здоровье", "Общественное питание", "Транспорт", "Маркетплейсы"]
# Ряд РФ, по которому оценивается ставка: у СберИндекса свои укрупнённые категории.
NATIONAL = {"Все категории": "Всего", "Продовольствие": "Продовольственные товары", "Здоровье": "Услуги",
            "Общественное питание": "Общественное питание", "Транспорт": "Услуги", "Маркетплейсы": "Непродовольственные товары"}
LAG = 6


def ols(y, X, cov="HAC", groups=None):
    X = sm.add_constant(X, has_constant="add")
    m = sm.OLS(y, X, missing="drop")
    r = m.fit(cov_type="HAC", cov_kwds={"maxlags": 6}) if cov == "HAC" else m.fit(cov_type="cluster", cov_kwds={"groups": groups})
    return r


def main():
    cfg, _ = config.cli(__doc__)
    P = cfg.path("processed")
    nat = pd.read_parquet(P / "national.parquet").set_index("period").sort_index()
    out = {c: {} for c in CATS}

    # ── Ставка: Δ12 ставки с лагом против годового прироста
    rate = nat["key_rate_mean"]
    d12 = (rate - rate.shift(12)).shift(LAG)
    for c in CATS:
        g = nat[f"spend_yoy_real:{NATIONAL[c]}"]
        df = pd.DataFrame({"g": g, "d12": d12, "g_lag": g.shift(12)}).dropna()
        r = ols(df.g, df[["d12", "g_lag"]])
        out[c]["rate"] = {"coef": float(r.params.d12), "se": float(r.bse.d12), "n": int(r.nobs), "series": NATIONAL[c], "lag": LAG}

    # ── Рабочие дни: месячный прирост расходов против изменения рабочих дней
    wd = nat["workdays"]
    for c in CATS:
        lv = np.log(nat[f"spend_bn:{NATIONAL[c]}"])
        df = pd.DataFrame({"dl": lv.diff() * 100, "dwd": wd.diff(), "m": nat.index.str[5:7]}).dropna()
        X = pd.concat([df[["dwd"]], pd.get_dummies(df.m, prefix="m", drop_first=True, dtype=float)], axis=1)
        r = ols(df.dl, X)
        out[c]["workday"] = {"coef": float(r.params.dwd), "se": float(r.bse.dwd), "n": int(r.nobs), "series": NATIONAL[c]}

    # ── Погода: внутри панели
    f = pd.read_parquet(P / "features.parquet")
    mo = pd.read_parquet(P / "mo.parquet")[["territory_id", "region_key", "mo_type"]]
    f = f.merge(mo, on="territory_id")
    f["kind"] = np.where(f.mo_type.isin(panel_models.URBAN), "город", "район")
    f = f.dropna(subset=["T2M", "PRECTOTCORR"])
    f["ly"] = np.log(f.value)
    f["dev"] = f.ly - f.groupby(["category", "kind", "date"]).ly.transform("median")
    f["dev"] -= f.groupby(["territory_id", "category"]).dev.transform("mean")
    for v in ("T2M", "PRECTOTCORR"):
        a = f[v] - f.groupby(["date", "category"])[v].transform("mean")
        f[f"{v}_a"] = a - a.groupby([f.territory_id, f.category]).transform("mean")
    f["summer"] = f.date.str[5:7].isin(["06", "07", "08"]).astype(float)
    f["heat_summer"] = f.T2M_a * f.summer
    f["heat_other"] = f.T2M_a * (1 - f.summer)
    for c in CATS:
        g = f[f.category == c]
        r = ols(g.dev * 100, g[["heat_summer", "heat_other", "PRECTOTCORR_a"]], cov="cluster", groups=g.region_key.astype("category").cat.codes)
        out[c]["heat"] = {"coef": float(r.params.heat_summer), "se": float(r.bse.heat_summer), "n": int(r.nobs), "season": "июнь—август"}
        out[c]["heat_other"] = {"coef": float(r.params.heat_other), "se": float(r.bse.heat_other)}
        out[c]["rain"] = {"coef": float(r.params.PRECTOTCORR_a), "se": float(r.bse.PRECTOTCORR_a)}

    # ── Паводок: случай 2024 года
    cases = json.loads((ROOT / "results/metrics/real_cases.json").read_text())
    for c in CATS:
        s = cases["floods_2024"]["shift_pct_by_category"][c]
        out[c]["flood"] = {"coef": s["flood"] - s["rest"], "source": "real_cases.json: паводки 2024, субъекты паводка против остальных"}

    dst = ROOT / "results" / "metrics" / "sensitivity.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    rows = [{"категория": c, **{k: f"{v['coef']:+.2f}" + (f" ± {v['se']:.2f}" if "se" in v else "") for k, v in d.items() if k in ("rate", "workday", "heat", "rain", "flood")}} for c, d in out.items()]
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\n{dst}")


if __name__ == "__main__":
    main()
