"""Шаг 36. Доходы по отраслям для всех МО: shift-share через структуру занятости.

Мир доходит до расходов жителей через зарплату отрасли, в которой они заняты
(ZADANIE 6.7). Шаг 21 проверил это на моногородах по двум отраслям; здесь —
все МО и все 19 отраслей:

* доли занятости по видам деятельности — Росстат, среднегодовая численность
  занятых по субъектам (ОКВЭД2, с учётом ВПН-2020), последний год — 2022;
  МО получает доли своего субъекта, моногород — половину от субъекта
  и половину от пары «обработка + добыча» (отрасль градообразующего
  предприятия в реестре не названа);
* рост ФОТ по отраслям — СберИндекс, годовой прирост в логарифмах,
  лаг публикации два месяца, как в шагах 13 и 21;
* сигнал МО на дату T: разрыв s = Σ доля × (рост ФОТ отрасли − рост ФОТ всех
  отраслей), и его ускорение за три месяца (как в шаге 21).

Поправка yhat·exp(β·s): β из сетки выбирается на целях до мая 2024 года,
отчёт — точки с июня 2024, отдельно по всем рядам, по моногородам и по
пятой части МО с самой концентрированной занятостью (добыча + сельское
хозяйство). Отдельно — шаги 1—3, как в итоговом прогнозе дня.

    python scripts/36_shiftshare.py

Выход — data/processed/mo_industry_shares.parquet (доли по МО, для сервиса),
results/forward_check/shiftshare.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics, regions  # noqa: E402

OUT = ROOT / "results/forward_check"
LAST, REPORT_FROM, SELECT_TO = "2024-12", "2024-06", "2024-05"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
EMP = ROOT / "data/external/rosstat/employment/SCHZ_sub_OKVED2_(VPN-2020).xlsx"

# столбцы Росстата (порядок листа) → отрасли ФОТ СберИндекса
OKVED_TO_FOT = ["Сельское хозяйство", "Добыча полезных ископаемых", "Обрабатывающие производства", "Услуги ЖКХ",
                "Водоснабжение", "Строительство", "Торговля", "Транспортировка и хранение", "Гостиницы и общепит",
                "Деятельность в области информации и связи", "Финансы и страхование", "Операции с недвижимостью",
                "Научная и профессиональная деятельность", "Административная деятельность",
                "Государственное управление и военная безопасность", "Образование", "Здравоохранение",
                "Спорт и досуг", "Прочие услуги"]


def employment_shares(year: str = "2022") -> pd.DataFrame:
    s = pd.read_excel(EMP, sheet_name=year, header=None)
    body = s.iloc[8:].dropna(subset=[1])
    body = body[~body[0].astype(str).str.contains("федеральный округ|Российская Федерация", regex=True)]
    names = body[0].astype(str).str.replace(r"\d\)$", "", regex=True).str.strip()
    vals = body.iloc[:, 2:2 + len(OKVED_TO_FOT)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    vals.columns = OKVED_TO_FOT
    shares = vals.div(vals.sum(axis=1), axis=0)
    shares.index = names.map(regions.key)
    return shares[~shares.index.duplicated()]


def fot_gap() -> pd.DataFrame:
    f = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    f["period"] = (pd.to_datetime(f.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    w = np.log(f.pivot_table(index="period", columns="activity", values="value"))
    yoy = w - w.shift(12)
    gap = yoy[OKVED_TO_FOT].sub(yoy["Все отрасли"], axis=0)
    return gap.shift(2)      # месяц T знает фонд по T−2


def mo_shares(mo: pd.DataFrame, sub: pd.DataFrame) -> pd.DataFrame:
    sh = sub.reindex(mo.region_key).to_numpy().copy()
    miss = np.isnan(sh).any(axis=1)
    sh[miss] = sub.mean().to_numpy()
    mono = (mo.mono_status.fillna("").str.strip() != "").to_numpy()
    pair = np.zeros(len(OKVED_TO_FOT)); pair[1] = pair[2] = 0.5
    sh[mono] = 0.5 * sh[mono] + 0.5 * pair
    out = pd.DataFrame(sh, columns=OKVED_TO_FOT)
    out.insert(0, "territory_id", mo.territory_id.to_numpy())
    out["subject_matched"] = ~miss
    out["mono"] = mono
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    sub = employment_shares()
    shares = mo_shares(mo, sub)
    shares.to_parquet(ROOT / "data/processed/mo_industry_shares.parquet", index=False)
    print(f"субъектов в файле {len(sub)}, МО с найденным субъектом {shares.subject_matched.sum()} из {len(shares)}, моногородов {shares.mono.sum()}")
    print("не найдены:", sorted(set(mo.loc[~shares.subject_matched, 'region'].unique()))[:10])

    gap = fot_gap()
    S = shares.set_index("territory_id")[OKVED_TO_FOT]
    row_sh = S.reindex(panel.index.territory_id).to_numpy()          # ряды × отрасли
    sig_level = {p: row_sh @ gap.loc[p].to_numpy() for p in gap.index if p in panel.periods and gap.loc[p].notna().all()}
    acc = gap - gap.shift(3)
    sig_acc = {p: row_sh @ acc.loc[p].to_numpy() for p in acc.index if p in panel.periods and acc.loc[p].notna().all()}
    conc = (S["Добыча полезных ископаемых"] + S["Сельское хозяйство"]).reindex(panel.index.territory_id).to_numpy()
    top = conc >= np.quantile(conc, 0.8)
    mono_rows = shares.set_index("territory_id").mono.reindex(panel.index.territory_id).to_numpy()

    rows = []
    for base in ["ensemble", "fc_ensemble+robust"]:
        path = ROOT / ("results/forecasts" if base == "ensemble" else "results/signal_value") / f"{base}.parquet"
        f = pd.read_parquet(path)
        for sname, sig in (("разрыв", sig_level), ("ускорение", sig_acc)):
            s = np.array([sig.get(o, np.zeros(len(panel.index)))[r] for o, r in zip(f.origin, f.row)])
            for steps_name, mask in (("все шаги", np.ones(len(f), bool)), ("шаги 1—3", (f.step <= 3).to_numpy())):
                sel = (f.target <= SELECT_TO).to_numpy() & mask
                grid = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0, 2.0)
                mae = {b: (f.yhat[sel] * np.exp(b * s[sel]) - f.y[sel]).abs().mean() for b in grid}
                beta = min(mae, key=mae.get)
                g = f.assign(yhat=f.yhat * np.exp(np.where(mask, beta * s, 0.0)))
                for scope, keep in (("все ряды", np.ones(len(panel.index), bool)), ("моногорода", mono_rows), ("добыча+село, верхняя пятая", top)):
                    a = g[(g.origin >= REPORT_FROM) & keep[g.row.to_numpy()]][COLS]
                    b = f[(f.origin >= REPORT_FROM) & keep[f.row.to_numpy()]][COLS]
                    for H in (1, 3, 6):
                        r = metrics.compare(a, b, H, LAST, 1000, 42)
                        rows.append({"база": base, "сигнал": sname, "шаги": steps_name, "β": beta, "срез": scope, "H": H,
                                     "MAE": r["MAE"], "MAE_до": r["MAE_ref"], "выигрыш_%": r["gain_pct"],
                                     "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"]})
                print(base, sname, steps_name, "β:", {k: round(v, 2) for k, v in mae.items()}, "→", beta)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "shiftshare.csv", index=False)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 400)
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
