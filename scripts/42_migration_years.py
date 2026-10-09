"""Шаг 42а. Сальдо внутренней миграции по МО за 2019—2023 годы — из архива БД ПМО по диапазонам.

Нужно для честной проверки канала в прогнозе: связь «сальдо 2022 → рост 2023» оценивается
вне отчётного окна, а «сальдо 2023 → рост 2024» только проверяется. Каждая часть архива
(субъект) читается по HTTP Range один раз (tools/remote_zip.py); берутся МО верхнего уровня,
оба пола, все возрасты, три направления.

    python scripts/42_migration_years.py

Выход — data/external/bdmo/migration_years.parquet: oktmo, year, migr, migr_in, migr_ext.
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
OUT = ROOT / "data/external/bdmo/migration_years.parquet"
KEEP = {"Миграция — всего": "migr", "В пределах России": "migr_in", "Международная": "migr_ext"}


def main():
    z = RemoteZip(URL)
    parts = {re.search(r"region(\d+)", n).group(1): n for n in z.names() if n.endswith(".parquet") and "region" in n and "__MACOSX" not in n}
    frames = []
    for i, (rid, n) in enumerate(sorted(parts.items())):
        d = pd.read_parquet(io.BytesIO(z.read(n)), columns=["migr", "grup_2", "vozr", "mun_level", "oktmo", "year", "indicator_value"])
        d = d[(d.year >= 2019) & (d.mun_level == "Муниципальное образование верхнего уровня") & (d.grup_2 == "Всего") & (d.vozr == "Всего") & d.migr.isin(KEEP)]
        if len(d):
            p = d.pivot_table(index=["oktmo", "year"], columns="migr", values="indicator_value", aggfunc="sum").rename(columns=KEEP).reset_index()
            frames.append(p)
        print(f"{i + 1}/{len(parts)} {rid}: {len(d)} строк", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out["oktmo"] = out.oktmo.astype(str).str.zfill(8)
    out.to_parquet(OUT, index=False)
    print(OUT, len(out), "по годам:", out.groupby("year").oktmo.nunique().to_dict())


if __name__ == "__main__":
    main()
