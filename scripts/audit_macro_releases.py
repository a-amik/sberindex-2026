"""Сверка исторических релизов с нынешней таблицей и реестр доступности."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import net


def cpi_from_text(text, table, value_index):
    if table == "petersburg":
        block = text.split("Ниже приведены", 1)[0]
        total = r"Потребительские товары и услуги"
    else:
        block = text.split("Индексы потребительских цен на товары и услуги", 1)[1].split("Индексы цен на отдельные", 1)[0]
        total = r"Индекс потребительских\s+цен"
    patterns = dict(cpi_total=total, cpi_food=r"продовольственные\s+товары(?:\s+1\b)?",
                    cpi_nonfood=r"непродовольственные\s+товары", cpi_services=r"услуги")
    values = {}
    for column, label in patterns.items():
        match = re.search(r"(?m)^\s*" + label + r"[ \t]*\s+((?:\d+[,.]\d+[ \t]*)+)", block)
        if not match:
            raise ValueError("Нет строки " + column)
        numbers = re.findall(r"\d+[,.]\d+", match[1])
        values[column] = float(numbers[value_index].replace(",", "."))
    return values


def main():
    cp = ROOT / "configs/release_audit.json"
    raw = ROOT / "data/external/release_audit"
    raw.mkdir(parents=True, exist_ok=True)
    out = ROOT / "results/macro_release_audit"
    out.mkdir(parents=True, exist_ok=True)
    cpi = pd.read_parquet(ROOT / "data/external/rosstat/cpi_regions.parquet").query("kind == 'region'").set_index(["region_key", "period"])
    wages = pd.read_parquet(ROOT / "data/external/rosstat/wages_regions.parquet").set_index(["region_key", "period"])
    rows, sources = [], []
    for record in json.loads(cp.read_text()):
        suffix = ".html" if record["table"] == "wage" else ".pdf"
        path = raw / (record["id"] + suffix)
        if not path.exists():
            path.write_bytes(net.fetch(net.session(), record["url"], tries=1, timeout=30).content)
        if suffix == ".pdf":
            txt = path.with_suffix(".txt")
            subprocess.run(["pdftotext", "-layout", str(path), str(txt)], check=True)
            observed = cpi_from_text(txt.read_text(), record["table"], record["value_index"])
            current = cpi.loc[[(record["region_key"], record["period"])]]
            precision = .01
        else:
            text = html.fromstring(path.read_text()).text_content()
            a = re.search(r"размере\s+(\d+)\s+рублей", text)
            if not a:
                raise ValueError("Нет значения зарплаты")
            observed = dict(wage=float(a[1]))
            current = wages.loc[[(record["region_key"], record["period"])]]
            precision = record["rounding_rubles"]
        if len(current) != 1:
            raise ValueError("Неоднозначный региональный ряд")
        current = current.iloc[0]
        pub_month = record["published_at"][:7]
        lag = pd.Period(pub_month, "M").ordinal - pd.Period(record["period"], "M").ordinal
        for column, value in observed.items():
            latest = float(current[column])
            rows.append(dict(id=record["id"], region_key=record["region_key"], period=record["period"],
                feature=column, published_at=record["published_at"], release_month_lag=lag,
                release_value=value, current_value=latest, absolute_difference=abs(value-latest),
                release_precision=precision, matches_rounding=bool(abs(value-latest) <= precision/2+1e-8),
                source=record["url"], snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        sources.append(dict(**record, snapshot=str(path.relative_to(ROOT)),
            retrieved_at=datetime.now(timezone.utc).isoformat(), historical_unchanged_version_verified=False))
    pd.DataFrame(rows).to_csv(out / "release_comparison.csv", index=False)
    (out / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2)+'\n')
    paths = [cp, Path(__file__), ROOT / "data/external/rosstat/cpi_regions.parquet", ROOT / "data/external/rosstat/wages_regions.parquet"]
    paths += [ROOT / s["snapshot"] for s in sources]
    manifest = dict(files={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                    caveat="Семь релизов не сертифицируют всю панель. Текущий снимок архивного документа не доказывает неизменность файла с даты публикации.")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(pd.DataFrame(rows).groupby("feature").agg(n=("matches_rounding", "size"), matches=("matches_rounding", "sum"), max_difference=("absolute_difference", "max")).to_string())


if __name__ == "__main__":
    main()
