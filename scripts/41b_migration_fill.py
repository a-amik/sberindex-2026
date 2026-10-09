"""Шаг 41б. Миграция для субъектов без 2023 года — последний доступный год из того же архива.

У семи субъектов (Новосибирская, Кемеровская, Тверская, Рязанская, Северная Осетия,
Бурятия, Ингушетия) в БД ПМО сальдо миграции кончается 2022 годом (у Бурятии — 2021).
Их части читаются из архива по диапазонам байтов (tools/remote_zip.py), берётся
последний год, и в migration_2023.parquet добавляется столбец year, чтобы сервис
и проверка знали, какого года число.

    python scripts/41b_migration_fill.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.remote_zip import RemoteZip  # noqa: E402

URL = "https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20250918/indicators/section31/data_Y48112023_112_v20250918.zip"
OUT = ROOT / "data/external/bdmo/migration_2023.parquet"
KEEP = {"Миграция — всего": "migr_2023", "В пределах России": "migr_in_2023", "Международная": "migr_ext_2023"}


def main():
    cur = pd.read_parquet(OUT)
    if "year" not in cur:
        cur["year"] = 2023
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    mo["k"] = mo.oktmo8.astype(str).str.zfill(8)
    have = set(cur.oktmo)
    missing = mo[~mo.k.isin(have)]
    prefixes = sorted(set(missing.k.str[:2]))
    z = RemoteZip(URL)
    parts = {re.search(r"region(\d+)", n).group(1): n for n in z.names() if n.endswith(".parquet") and "region" in n and "__MACOSX" not in n}
    frames = []
    for rid in prefixes:
        if rid not in parts:
            continue
        d = pd.read_parquet(io.BytesIO(z.read(parts[rid])), columns=["migr", "grup_2", "vozr", "mun_level", "oktmo", "year", "indicator_value"])
        d = d[(d.mun_level == "Муниципальное образование верхнего уровня") & (d.grup_2 == "Всего") & (d.vozr == "Всего") & d.migr.isin(KEEP)]
        d["oktmo"] = d.oktmo.astype(str).str.zfill(8)
        d = d[d.oktmo.isin(set(missing.k))]
        if not len(d):
            continue
        y = int(d.year.max())
        p = d[d.year == y].pivot_table(index="oktmo", columns="migr", values="indicator_value", aggfunc="sum").rename(columns=KEEP).reset_index()
        p["year"] = y
        frames.append(p)
        print(rid, "год", y, "МО", len(p))
    if frames:
        add = pd.concat(frames, ignore_index=True)
        add = add[~add.oktmo.isin(have)]
        out = pd.concat([cur, add], ignore_index=True)
        out.to_parquet(OUT, index=False)
        print("добавлено", len(add), "итого", len(out), "по годам:", out.year.value_counts().to_dict())


if __name__ == "__main__":
    main()
