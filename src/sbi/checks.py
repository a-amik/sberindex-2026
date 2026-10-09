"""Проверки данных до моделей.

Что смотрим и почему:
* состав набора по месяцам — МО входит в набор, когда оценка выше порога
  качества, и выпадает из него; выпадение в середине ряда — дыра, в начале
  или в конце — обрезанный ряд;
* эффект состава — медиана по всем МО месяца против медианы по МО с полным
  рядом: если они расходятся, «общий фактор», посчитанный по плавающему
  составу, несёт ложные сдвиги;
* доля прочих трат — «Все категории» больше суммы пяти категорий на прочие
  траты; скачок этой доли у МО — признак смены методики или разрыва;
* выбросы — отклонение логарифма от медианы своего ряда в единицах MAD;
* покрытие населением, соседями и региональными рядами;
* апрель 2023 — сдвиг «город — село», найденный в открытом решении: проверяем
  на своей панели по типам МО.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FIVE = ["Продовольствие", "Здоровье", "Общественное питание", "Транспорт", "Маркетплейсы"]


def _coverage(panel):
    per_month = panel[panel.category == "Все категории"].groupby("period").territory_id.nunique()
    allc = panel[panel.category == "Все категории"]
    periods = sorted(panel.period.unique())
    idx = {p: i for i, p in enumerate(periods)}
    kinds = {"full": 0, "late_start": 0, "early_end": 0, "inner_gap": 0}
    for _, g in allc.groupby("territory_id"):
        pos = sorted(idx[p] for p in g.period)
        if len(pos) == len(periods):
            kinds["full"] += 1
            continue
        if pos[-1] - pos[0] + 1 > len(pos):
            kinds["inner_gap"] += 1
        if pos[0] > 0:
            kinds["late_start"] += 1
        if pos[-1] < len(periods) - 1:
            kinds["early_end"] += 1
    series = panel.groupby(["territory_id", "category"], observed=True).size()
    return {
        "mo_per_month": {"min": int(per_month.min()), "max": int(per_month.max()),
                         "min_month": per_month.idxmin(), "max_month": per_month.idxmax()},
        "series_total": int(len(series)), "series_full": int((series == len(periods)).sum()),
        "mo_all_categories": kinds,
    }


def _composition(panel):
    allc = panel[panel.category == "Все категории"]
    full = allc[allc.full]
    m_all = allc.groupby("period").value.median()
    m_full = full.groupby("period").value.median()
    gap = (np.log(m_all) - np.log(m_full)) * 100
    return {"median_all_vs_full_pct": {k: round(float(v), 2) for k, v in gap.items()},
            "max_abs_pct": round(float(gap.abs().max()), 2), "month_of_max": gap.abs().idxmax()}


def _other_share(panel):
    w = panel.pivot_table(index=["territory_id", "period"], columns="category", values="value", observed=True)
    w = w.dropna(subset=["Все категории"] + FIVE)
    share = 1 - w[FIVE].sum(axis=1) / w["Все категории"]
    by_month = share.groupby(level="period").median()
    jump = share.groupby(level="territory_id").diff().abs()
    return {
        "median_other_share": round(float(share.median()), 3),
        "q05_q95": [round(float(share.quantile(.05)), 3), round(float(share.quantile(.95)), 3)],
        "negative_rows": int((share < 0).sum()),
        "by_month": {k: round(float(v), 3) for k, v in by_month.items()},
        "mo_with_jump_over_20pp": int((jump > 0.20).groupby(level="territory_id").any().sum()),
    }


def _outliers(panel, thr=6.0):
    lv = np.log(panel.value.clip(lower=1))
    g = panel.assign(lv=lv).groupby(["territory_id", "category"], observed=True).lv
    med = g.transform("median")
    mad = g.transform(lambda s: (s - s.median()).abs().median()).replace(0, np.nan)
    z = (lv - med) / (1.4826 * mad)
    out = panel.assign(z=z)[z.abs() > thr]
    return {"threshold_mad": thr, "rows": int(len(out)),
            "by_category": out.category.value_counts().to_dict(),
            "top": out.reindex(out.z.abs().sort_values(ascending=False).index).head(10)
                      [["territory_id", "category", "period", "value", "z"]]
                      .assign(z=lambda d: d.z.round(1)).to_dict("records")}


def _april_2023(panel, mo):
    w = panel[panel.period.isin(["2023-03", "2023-04"])].pivot_table(
        index=["territory_id", "category"], columns="period", values="value", observed=True).dropna()
    w["chg"] = (np.log(w["2023-04"]) - np.log(w["2023-03"])) * 100
    w = w.reset_index().merge(mo[["territory_id", "mo_type"]], on="territory_id")
    t = w.pivot_table(index="mo_type", columns="category", values="chg", aggfunc="median", observed=True).round(1)
    return {"median_log_change_pct_mar_to_apr": t.to_dict(orient="index")}


def _vs_national(panel, mo, national):
    """Прирост год к году по панели (МО с полным рядом, вес — население) против
    общероссийского ряда СберИндекса. Ряды разные по охвату — сверяем динамику."""
    allc = panel[(panel.category == "Все категории") & panel.full].merge(
        mo[["territory_id", "pop"]], on="territory_id").dropna(subset=["pop"])
    agg = allc.assign(w=allc.value * allc["pop"]).groupby("period").agg(w=("w", "sum"), p=("pop", "sum"))
    lvl = agg.w / agg.p
    yoy = (lvl / lvl.shift(12) - 1).dropna() * 100
    nat = national.set_index("period")["spend_yoy_nominal:Всего"].reindex(yoy.index)
    diff = (yoy - nat).dropna()
    return {"months": len(diff), "corr": round(float(yoy.corr(nat)), 3),
            "mean_abs_diff_pp": round(float(diff.abs().mean()), 2),
            "panel_yoy": {k: round(float(v), 1) for k, v in yoy.items()},
            "sberindex_yoy": {k: round(float(v), 1) for k, v in nat.dropna().items()}}


def run(panel, mo, nb, regions, regional, national) -> dict:
    nb_count = nb.groupby("territory_id").size().reindex(mo.territory_id, fill_value=0)
    cov_regions = set(regional.dropna(subset=["cpi_total"]).region_key)
    cov_wages = set(regional.dropna(subset=["wage"]).region_key)
    return {
        "coverage": _coverage(panel),
        "composition_effect": _composition(panel),
        "other_spending_share": _other_share(panel),
        "outliers": _outliers(panel),
        "april_2023_shift": _april_2023(panel, mo),
        "population": {"matched": int(mo["pop"].notna().sum()), "of": int(len(mo)),
                       "by_source": mo.pop_source.replace("", "none").value_counts().to_dict(),
                       "missing_by_region": mo[mo["pop"].isna()].region.value_counts().head(5).to_dict()},
        "neighbours": {"by_kind": nb.drop_duplicates("territory_id").kind.value_counts().to_dict(),
                       "mo_with_full_k": int((nb_count == nb_count.max()).sum()),
                       "mo_without": int((nb_count == 0).sum()),
                       "median_km_to_kth": round(float(nb.groupby("territory_id").distance.max().median()), 1)},
        "regional_links": {"regions_in_panel": int(mo.region_key.nunique()),
                           "with_cpi": len(set(mo.region_key) & cov_regions),
                           "with_wages": len(set(mo.region_key) & cov_wages)},
        "market_access_missing": int(mo.market_access.isna().sum()),
        "coordinates_missing": int(mo.lat.isna().sum()),
        "monotowns_matched": int((mo.mono_status != "").sum()),
        "national_periods": [national.period.min(), national.period.max()],
        "panel_vs_national_yoy": _vs_national(panel, mo, national),
    }


def print_report(r: dict) -> None:
    c = r["coverage"]
    print("\nПроверки данных")
    print(f"  МО в месяце: {c['mo_per_month']['min']}–{c['mo_per_month']['max']}; "
          f"рядов {c['series_total']:,}, полных {c['series_full']:,}")
    print(f"  «Все категории» по МО: {c['mo_all_categories']}")
    ce = r["composition_effect"]
    print(f"  эффект состава: до {ce['max_abs_pct']} % ({ce['month_of_max']})")
    o = r["other_spending_share"]
    print(f"  доля прочих трат: медиана {o['median_other_share']}, 5–95 % {o['q05_q95']}, "
          f"отрицательных {o['negative_rows']}, МО со скачком > 20 п.п.: {o['mo_with_jump_over_20pp']}")
    print(f"  выбросы > {r['outliers']['threshold_mad']} MAD: {r['outliers']['rows']} {r['outliers']['by_category']}")
    print(f"  население: {r['population']}")
    print(f"  соседи: {r['neighbours']}")
    print(f"  региональные ряды: {r['regional_links']}; нет доступности рынков: {r['market_access_missing']}; "
          f"моногородов: {r['monotowns_matched']}")
    v = r["panel_vs_national_yoy"]
    print(f"  панель против ряда РФ, прирост г/г 2024: корреляция {v['corr']}, "
          f"средний разрыв {v['mean_abs_diff_pp']} п.п. за {v['months']} мес.")
    print("  апрель 2023, медианное изменение к марту, %:")
    for t, row in r["april_2023_shift"]["median_log_change_pct_mar_to_apr"].items():
        print(f"    {t[:40]:40s} " + "  ".join(f"{k[:6]} {v:+.1f}" for k, v in row.items()))
