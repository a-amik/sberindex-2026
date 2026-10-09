"""Шаг 41в. Возраст МО для субъектов, которых не отдала форма Росстата (шаг 23), —
из той же базы показателей МО в плоской выгрузке (показатель 8112014, data/external/bdmo/
age_bdmo_all.parquet, снят из архива по диапазонам байтов).

Берётся 1 января 2023 года, оба пола, МО верхнего уровня; группы складываются
из пятилеток (0—4…80+), где их нет — из одиночных годов. Добавляются только МО,
которых нет в age_mo_2023.parquet; схема файла сохраняется.

    python scripts/41c_age_fill.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/external/bdmo/age_bdmo_all.parquet"
AGE = ROOT / "data/external/rosstat/age_mo_2023.parquet"
FIVE = {"0-14": ["0‒4", "5‒9", "10‒14"], "15-24": ["15‒19", "20‒24"], "25-34": ["25‒29", "30‒34"],
        "35-64": ["35‒39", "40‒44", "45‒49", "50‒54", "55‒59", "60‒64"], "65+": ["65‒69", "70‒74", "75‒79", "80+", "80‒84", "85‒89", "90‒94", "95‒99", "100 и более лет"]}
SINGLE = {"0-14": range(0, 15), "15-24": range(15, 25), "25-34": range(25, 35), "35-64": range(35, 65), "65+": range(65, 100)}


def main():
    d = pd.read_parquet(SRC)
    d = d[(d.year == 2023) & (d.grup_2 == "Всего") & (d.mun_level == "Муниципальное образование верхнего уровня") & (d.indicator_period == "На 1 января")]
    d["oktmo"] = d.oktmo.astype(str).str.zfill(8)
    age = pd.read_parquet(AGE)
    have = set(age[age.total > 0].oktmo8.astype(str).str.zfill(8))
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    need = set(mo.oktmo8.astype(str).str.zfill(8)) - have
    d = d[d.oktmo.isin(need)]
    piv = d.pivot_table(index="oktmo", columns="vozr", values="indicator_value", aggfunc="sum")
    def pick(r, names):
        v = r.reindex(names).dropna()
        return float(v.sum()) if len(v) == len(names) else None

    def singles(r, rng):
        v = r.reindex([str(i) for i in rng]).dropna()
        return float(v.sum()) if len(v) == len(list(rng)) else None

    rows = []
    for k, r in piv.iterrows():
        tot = r.get("Всего")
        if not (tot and tot > 0):
            continue
        g = {}
        g["0-14"] = r.get("0‒14") if pd.notna(r.get("0‒14")) else (pick(r, ["0‒4", "5‒9", "10‒14"]) or singles(r, range(0, 15)))
        g["15-24"] = pick(r, ["15‒19", "20‒24"]) or singles(r, range(15, 25))
        g["25-34"] = pick(r, ["25‒29", "30‒34"]) or singles(r, range(25, 35))
        g["35-64"] = pick(r, ["35‒39", "40‒44", "45‒49", "50‒54", "55‒59", "60‒64"]) or singles(r, range(35, 65))
        old70 = r.get("70 и старше") if pd.notna(r.get("70 и старше")) else (pick(r, ["70‒74", "75‒79", "80+"]) or pick(r, ["70‒74", "75‒79", "80‒84", "85‒89", "90‒94", "95‒99", "100 и более лет"]))
        g["65+"] = (float(r["65‒69"]) + float(old70)) if pd.notna(r.get("65‒69")) and old70 is not None else None
        if any(v is None for v in g.values()):
            continue
        if abs(sum(g.values()) / tot - 1) > 0.01:
            continue
        rows.append({"oktmo8": k, "total": float(tot), **{a: float(b) for a, b in g.items()}})
    add = pd.DataFrame(rows)
    if not len(add):
        print("добавлять нечего"); return
    add["region_code"] = add.oktmo8.str[:2]
    add["name"] = add.oktmo8.map(mo.set_index(mo.oktmo8.astype(str).str.zfill(8)).name.to_dict())
    add = add[["region_code", "name", "oktmo8", "total", "0-14", "15-24", "25-34", "35-64", "65+"]]
    out = pd.concat([age, add], ignore_index=True)
    out.to_parquet(AGE, index=False)
    chk = (add[["0-14", "15-24", "25-34", "35-64", "65+"]].sum(axis=1) / add.total)
    print("добавлено МО:", len(add), "сумма групп к итогу: медиана", round(chk.median(), 3), "мин", round(chk.min(), 3), "макс", round(chk.max(), 3))
    print("по субъектам:", add.region_code.value_counts().to_dict())
    print("всего МО с возрастом:", int((out.total > 0).sum()))


if __name__ == "__main__":
    main()
