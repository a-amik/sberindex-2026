"""Шаг 37. Shift-share на отраслевой структуре самого МО (БД ПМО Росстата).

Шаг 36 брал доли занятости субъекта, одинаковые для всех его МО, и рычага
не вышло. Здесь доли — свои у каждого МО: среднесписочная численность
работников организаций без малого бизнеса по разделам ОКВЭД2 (БД ПМО,
показатель 8423005; плоская выгрузка «Если быть точным», CC BY 4.0,
data/external/bdmo/). Берётся год 2022, январь—декабрь — он известен
к любой точке прогноза бэктеста; нет 2022 — 2021. Стыковка по ОКТМО
со справочником МО; где не нашлось или работников меньше 200 —
доли субъекта из шага 36 (помечено в столбце source).

Сигнал и проверка — те же, что в шаге 36: разрыв роста ФОТ отрасли
(СберИндекс, лаг два месяца) и его ускорение, взвешенные долями МО;
β из сетки по целям до мая 2024, отчёт с июня 2024. Срезы: все ряды,
моногорода, пятая часть МО с самой высокой долей добычи и сельского
хозяйства, МО с одной доминирующей отраслью (доля добычи, обработки
или сельского хозяйства ≥ 35 %).

    python scripts/37_shiftshare_mo.py

Выход — data/processed/mo_industry_shares.parquet (перезаписывается:
доли МО, источник), results/forward_check/shiftshare_mo.csv.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402

OUT = ROOT / "results/forward_check"
LAST, REPORT_FROM, SELECT_TO = "2024-12", "2024-06", "2024-05"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
BDMO = ROOT / "data/external/bdmo/data_Y48423005_112_v20250918.parquet"
MIN_WORKERS = 200

KEYWORDS = [("Сельское", "Сельское хозяйство"), ("Добыча", "Добыча полезных ископаемых"),
            ("Обрабатывающие", "Обрабатывающие производства"), ("электрической", "Услуги ЖКХ"),
            ("Водоснабжение", "Водоснабжение"), ("Строительство", "Строительство"), ("Торговля", "Торговля"),
            ("Транспортировка", "Транспортировка и хранение"), ("гостиниц", "Гостиницы и общепит"),
            ("информации", "Деятельность в области информации и связи"), ("финансовая", "Финансы и страхование"),
            ("недвижимым", "Операции с недвижимостью"), ("профессиональная", "Научная и профессиональная деятельность"),
            ("административная", "Административная деятельность"), ("Государственное", "Государственное управление и военная безопасность"),
            ("Образование", "Образование"), ("здравоохранения", "Здравоохранение"), ("культуры", "Спорт и досуг"),
            ("прочих", "Прочие услуги")]


def load36():
    spec = importlib.util.spec_from_file_location("s36", ROOT / "scripts/36_shiftshare.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def bdmo_shares(fot_cols: list[str]) -> pd.DataFrame:
    d = pd.read_parquet(BDMO, columns=["okved2", "oktmo", "mun_level", "year", "indicator_value", "indicator_period"])
    d = d[(d.mun_level != "Субъект РФ") & (d.indicator_period == "Январь-декабрь") & d.year.isin([2021, 2022])]
    act = pd.Series(pd.NA, index=d.index, dtype="string")
    for kw, name in KEYWORDS:
        act = act.mask(d.okved2.str.contains(kw, case=False) & act.isna(), name)
    d = d.assign(activity=act).dropna(subset=["activity"])
    d = d.groupby(["oktmo", "year", "activity"], as_index=False).indicator_value.sum()
    w = d.pivot_table(index=["oktmo", "year"], columns="activity", values="indicator_value").reindex(columns=fot_cols).fillna(0.0)
    w = w.reset_index().sort_values("year").groupby("oktmo").tail(1).set_index("oktmo")
    total = w[fot_cols].sum(axis=1)
    sh = w[fot_cols].div(total, axis=0)
    sh["workers"] = total
    sh["bdmo_year"] = w.year
    return sh


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s36 = load36()
    cols = s36.OKVED_TO_FOT
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    sub = s36.mo_shares(mo, s36.employment_shares()).set_index("territory_id")
    bd = bdmo_shares(cols)
    key = mo.oktmo8.astype(str).str.zfill(8) if "oktmo8" in mo else mo.oktmo.astype(str).str[:8].str.zfill(8)
    hit = bd.reindex(key.to_numpy())
    ok = hit.workers.fillna(0).to_numpy() >= MIN_WORKERS
    shares = sub[cols].copy()
    shares.loc[ok, cols] = hit.loc[ok, cols].to_numpy()
    shares["source"] = np.where(ok, "МО (БД ПМО)", "субъект")
    shares["workers"] = hit.workers.to_numpy()
    shares["mono"] = sub.mono
    shares.reset_index().to_parquet(ROOT / "data/processed/mo_industry_shares.parquet", index=False)
    print(f"МО с долями из БД ПМО: {ok.sum()} из {len(mo)}; по типам:")
    print(pd.crosstab(mo.mo_type, shares.source.to_numpy()).to_string())
    top3 = shares[cols].apply(lambda r: r.sort_values(ascending=False).index[0], axis=1)
    print("ведущая отрасль МО (число МО):", top3.value_counts().head(8).to_dict())

    gap = s36.fot_gap()
    row_sh = shares[cols].reindex(panel.index.territory_id).to_numpy()
    acc = gap - gap.shift(3)
    sig_level = {p: row_sh @ gap.loc[p].to_numpy() for p in gap.index if p in panel.periods and gap.loc[p].notna().all()}
    sig_acc = {p: row_sh @ acc.loc[p].to_numpy() for p in acc.index if p in panel.periods and acc.loc[p].notna().all()}
    conc = (shares["Добыча полезных ископаемых"] + shares["Сельское хозяйство"]).reindex(panel.index.territory_id).to_numpy()
    dom = shares[["Добыча полезных ископаемых", "Обрабатывающие производства", "Сельское хозяйство"]].max(axis=1).reindex(panel.index.territory_id).to_numpy() >= 0.35
    mono_rows = shares.mono.reindex(panel.index.territory_id).to_numpy().astype(bool)
    scopes = (("все ряды", np.ones(len(panel.index), bool)), ("моногорода", mono_rows),
              ("добыча+село, верхняя пятая", conc >= np.quantile(conc, 0.8)), ("одна отрасль ≥ 35 %", dom))
    print("рядов в срезах:", {k: int(v.sum()) for k, v in scopes})

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
                print(base, sname, steps_name, "β →", beta)
                for scope, keep in scopes:
                    a = g[(g.origin >= REPORT_FROM) & keep[g.row.to_numpy()]][COLS]
                    b = f[(f.origin >= REPORT_FROM) & keep[f.row.to_numpy()]][COLS]
                    for H in (1, 3, 6):
                        r = metrics.compare(a, b, H, LAST, 1000, 42)
                        rows.append({"база": base, "сигнал": sname, "шаги": steps_name, "β": beta, "срез": scope, "H": H,
                                     "MAE": r["MAE"], "MAE_до": r["MAE_ref"], "выигрыш_%": r["gain_pct"], "доля_рядов_лучше": r["share_series_better"],
                                     "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"]})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "shiftshare_mo.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 400)
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
