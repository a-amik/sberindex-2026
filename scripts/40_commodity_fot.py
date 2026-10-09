"""Шаг 40. Звено «цена сырья → ФОТ отрасли» на рядах с 2017 года.

Мир доходит до доходов жителей через зарплату отрасли (ZADANIE 6.7); здесь
измеряется первое звено: как годовой прирост фонда оплаты труда отрасли
(СберИндекс, 20 отраслей, с 2017) отвечает на годовой прирост цены сырья
в рублях с лагом 0…12 месяцев. Цены — месячные МВФ через FRED (Brent, уголь,
железная руда, медь, никель, алюминий, пшеница, кукуруза, подсолнечное масло,
газ в Европе), Urals — Минэк/Минфин, если собран файл urals.csv; курс —
ЦБ, среднее за месяц. Цена в рублях = цена × курс.

Для каждой пары (отрасль, товар) — регрессия Δ12 log ФОТ на Δ12 log цены
с лагом L, ошибки Ньюи—Уэста (12 лагов), 2018-01…2026-07; выбирается лаг
с наибольшим t по модулю, но отчёт даёт и лаг 0, 3, 6, 12. Пары заданы
по смыслу: добыча — нефть, уголь, газ, руда; сельское хозяйство — пшеница,
кукуруза, масло; обработка — металлы и нефть; транспортировка — нефть
и уголь; все отрасли — нефть (бюджетный канал).

    python scripts/40_commodity_fot.py

Выход — results/forward_check/commodity_fot.csv, data/processed/commodities.parquet.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/forward_check"
SRC = ROOT / "data/external/commodities"
FRED = {"Brent": "POILBREUSDM", "уголь": "PCOALAUUSDM", "железная руда": "PIORECRUSDM", "медь": "PCOPPUSDM",
        "никель": "PNICKUSDM", "алюминий": "PALUMUSDM", "пшеница": "PWHEAMTUSDM", "кукуруза": "PMAIZMTUSDM",
        "подсолнечное масло": "PSUNOUSDM", "газ (Европа)": "PNGASEUUSDM"}
PAIRS = {"Добыча полезных ископаемых": ["Urals", "Brent", "уголь", "газ (Европа)", "железная руда"],
         "Сельское хозяйство": ["пшеница", "кукуруза", "подсолнечное масло"],
         "Обрабатывающие производства": ["медь", "никель", "алюминий", "железная руда", "Brent"],
         "Транспортировка и хранение": ["Brent", "уголь"],
         "Все отрасли": ["Urals", "Brent"]}


def usdrub() -> pd.Series:
    root = ET.parse(SRC / "usdrub.xml").getroot()
    rows = [(r.get("Date"), float(r.find("VunitRate").text.replace(",", "."))) for r in root.findall("Record")]
    s = pd.Series(dict(rows))
    s.index = pd.to_datetime(s.index, format="%d.%m.%Y")
    return s.resample("MS").mean().rename("usdrub")


def prices() -> pd.DataFrame:
    fx = usdrub()
    cols = {}
    for name, fid in FRED.items():
        d = pd.read_csv(SRC / f"{fid}.csv")
        s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy(), index=pd.to_datetime(d.iloc[:, 0]))
        cols[name] = s
    if (SRC / "urals.csv").exists():
        u = pd.read_csv(SRC / "urals.csv")      # столбцы: period (ГГГГ-ММ), usd
        cols["Urals"] = pd.Series(u.usd.to_numpy(), index=pd.to_datetime(u.period))
    p = pd.DataFrame(cols)
    p = p[p.index >= "2016-01"]
    rub = p.mul(fx.reindex(p.index), axis=0).add_suffix(" ₽")
    out = pd.concat([p, rub, fx.reindex(p.index)], axis=1)
    out.index = out.index.strftime("%Y-%m")
    return out


def fot_yoy() -> pd.DataFrame:
    f = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    f["period"] = (pd.to_datetime(f.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    w = np.log(f.pivot_table(index="period", columns="activity", values="value"))
    return w - w.shift(12)


def fit(y: pd.Series, x: pd.Series, lag: int) -> dict:
    d = pd.concat([y, x.shift(lag)], axis=1).dropna()
    d = d[(d.index >= "2018-01") & (d.index <= "2026-07")]
    X = sm.add_constant(d.iloc[:, 1].to_numpy())
    r = sm.OLS(d.iloc[:, 0].to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
    return {"лаг": lag, "β": r.params[1], "se": r.bse[1], "t": r.tvalues[1], "R2": r.rsquared, "n": len(d)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = prices()
    p.to_parquet(ROOT / "data/processed/commodities.parquet")
    lp = np.log(p[[c for c in p.columns if c.endswith(" ₽")]])
    dx = lp - lp.shift(12)
    fy = fot_yoy()
    rows = []
    for ind, goods in PAIRS.items():
        for g in goods:
            col = f"{g} ₽"
            if col not in dx or dx[col].notna().sum() < 36:
                continue
            fits = [fit(fy[ind], dx[col], L) for L in range(0, 13)]
            best = max(fits, key=lambda r: abs(r["t"]))
            for r in fits:
                if r["лаг"] in (0, 3, 6, 12) or r is best:
                    rows.append({"отрасль": ind, "товар": g, **r, "лучший": r is best})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "commodity_fot.csv", index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 300)
    print(res.round(3).to_string(index=False))
    print("\nЛучшие лаги:")
    print(res[res.лучший].round(3)[["отрасль", "товар", "лаг", "β", "t", "R2", "n"]].to_string(index=False))


def robustness():
    """Те же пары без ковидного года (цели 2020-03…2021-02) и без года после
    февраля 2022 (2022-03…2023-02): держится ли знак и сила у лучших лагов."""
    p = pd.read_parquet(ROOT / "data/processed/commodities.parquet")
    lp = np.log(p[[c for c in p.columns if c.endswith(" ₽")]])
    dx = lp - lp.shift(12)
    fy = fot_yoy()
    checks = [("Добыча полезных ископаемых", "Brent", 6), ("Добыча полезных ископаемых", "уголь", 6),
              ("Сельское хозяйство", "пшеница", 0), ("Сельское хозяйство", "пшеница", 6),
              ("Обрабатывающие производства", "никель", 1), ("Все отрасли", "Brent", 6)]
    rows = []
    for ind, g, L in checks:
        d = pd.concat([fy[ind], dx[f"{g} ₽"].shift(L)], axis=1).dropna()
        d = d[(d.index >= "2018-01") & (d.index <= "2026-07")]
        for name, mask in (("всё", np.ones(len(d), bool)),
                           ("без ковида", ~((d.index >= "2020-03") & (d.index <= "2021-02"))),
                           ("без 2022/23", ~((d.index >= "2022-03") & (d.index <= "2023-02"))),
                           ("без обоих", ~((d.index >= "2020-03") & (d.index <= "2021-02")) & ~((d.index >= "2022-03") & (d.index <= "2023-02")))):
            dd = d[mask]
            r = sm.OLS(dd.iloc[:, 0].to_numpy(), sm.add_constant(dd.iloc[:, 1].to_numpy())).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
            rows.append({"отрасль": ind, "товар": g, "лаг": L, "окно": name, "β": r.params[1], "t": r.tvalues[1], "R2": r.rsquared, "n": len(dd)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "commodity_fot_robust.csv", index=False)
    pd.set_option("display.width", 220)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    import sys
    robustness() if (len(sys.argv) > 1 and sys.argv[1] == "--robust") else main()
