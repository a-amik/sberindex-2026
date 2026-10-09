"""Шаг 41а. Миграционный прирост по МО за 2023 год из архива БД ПМО — частями, без распаковки.

Архив показателя 8112023 («Если быть точным», 1,2 ГБ) лежит по субъектам; читать его
целиком нельзя — сто частей разом не помещаются в память. Каждая часть читается
из zip по отдельности, в ней оставляется 2023 год, период январь—декабрь и итоговые
разрезы (все направления, все возрасты), и результат складывается в компактный файл.

    python scripts/41a_migration_extract.py

Выход — data/external/bdmo/migration_2023.parquet: oktmo, migr_2023 (всего), migr_in_2023 (в пределах России), migr_ext_2023 (международная), человек.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data/external/bdmo/migration.zip"
OUT = ROOT / "data/external/bdmo/migration_2023.parquet"


KEEP = {"Миграция — всего": "migr_2023", "В пределах России": "migr_in_2023", "Международная": "migr_ext_2023"}


def main():
    z = zipfile.ZipFile(ZIP)
    names = [n for n in z.namelist() if n.endswith(".parquet") and "__MACOSX" not in n and "region" in n]
    frames = []
    for n in names:
        d = pd.read_parquet(io.BytesIO(z.read(n)), columns=["migr", "grup_2", "vozr", "mun_level", "oktmo", "year", "indicator_value"])
        d = d[(d.year == 2023) & (d.mun_level == "Муниципальное образование верхнего уровня") & (d.grup_2 == "Всего") & (d.vozr == "Всего") & d.migr.isin(KEEP)]
        if len(d):
            frames.append(d.pivot_table(index="oktmo", columns="migr", values="indicator_value", aggfunc="sum").rename(columns=KEEP).reset_index())
    out = pd.concat(frames, ignore_index=True).groupby("oktmo", as_index=False).sum(min_count=1)
    out["oktmo"] = out.oktmo.astype(str).str.zfill(8)
    out.to_parquet(OUT, index=False)
    print(OUT, len(out), "МО; сальдо всего", int(out.migr_2023.sum()), "внутри России", int(out.migr_in_2023.sum()), "международная", int(out.migr_ext_2023.sum()))


if __name__ == "__main__":
    main()
