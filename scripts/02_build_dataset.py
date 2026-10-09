"""Шаг 2. Панель, характеристики МО, соседи, внешние ряды и проверки данных.

    python scripts/02_build_dataset.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sbi import checks, config, dataset  # noqa: E402


def main():
    cfg, _ = config.cli(__doc__)
    raw, ext, out = cfg.path("raw") / "hackathon", cfg.path("external"), cfg.path("processed")
    out.mkdir(parents=True, exist_ok=True)

    panel = dataset.build_panel(raw)
    ids = set(panel.territory_id.unique())
    mo = dataset.build_mo(raw, ext, ids)
    k = cfg["panel"]["neighbours_k"]
    nb = dataset.add_geo_neighbours(dataset.build_neighbours(raw, ids, k), mo, k)
    regions = dataset.build_regions(panel, mo)
    national = dataset.build_national(ext, cfg)
    regional = dataset.build_regional(ext)

    for name, df in (("panel", panel), ("mo", mo), ("neighbours", nb), ("regions", regions),
                     ("national", national), ("regional", regional)):
        df.to_parquet(out / f"{name}.parquet", index=False)
        print(f"  {name}: {df.shape[0]:,} × {df.shape[1]}")

    report = checks.run(panel, mo, nb, regions, regional, national)
    (out / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    checks.print_report(report)


if __name__ == "__main__":
    main()
