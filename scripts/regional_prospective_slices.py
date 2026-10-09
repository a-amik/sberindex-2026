"""Абляция с общей силой 0,25; отдельное покрытие поисковых данных."""
from pathlib import Path
import importlib.util
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest

spec = importlib.util.spec_from_file_location("runner", ROOT / "scripts/09_regional_signals.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main():
    out = ROOT / "results/regional_prospective_signals"
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    base = pd.read_parquet(ROOT / "results/forecasts/chronos2_dev.parquet").sort_values(m.KEYS).reset_index(drop=True)
    mapping = panel.index.merge(mo[["territory_id", "region_key"]], on="territory_id", validate="many_to_one")
    cells = mapping[["region_key", "category"]].drop_duplicates().sort_values(["region_key", "category"])
    lookup = {tuple(r): i for i, r in enumerate(cells.astype(str).itertuples(index=False, name=None))}
    keys = [lookup[(r, str(c))] for r, c in zip(mapping.region_key, mapping.category)]
    indexed = base.assign(cell=np.array(keys)[base.row.to_numpy()])
    correction = pd.read_parquet(out / "corrections.parquet")
    s = dict(report_from="2024-06", horizons=[1, 3, 6])
    pilot = [r["key"] for r in json.loads((ROOT / "configs/wordstat_pilot.json").read_text())["regions"] if r["key"] != "russia"]
    rows, region_rows = [], []
    for name in ["base", *correction.model.unique()]:
        if name == "base":
            frame = base
        else:
            f = indexed.merge(correction[correction.model == name].drop(columns="model"), on=["origin", "step", "cell"], validate="many_to_one")
            if not f[m.KEYS].equals(base[m.KEYS]):
                raise ValueError("Сетка переставлена")
            frame = m.with_strength(f, .25)
        region = m.regional_frame(frame, panel, mo)
        for scope, subset in (("all73", region), ("pilot5", region[region.region_key.isin(pilot)]),
                              ("other68", region[~region.region_key.isin(pilot)])):
            rows += [dict(scope=scope, strength=0 if name == "base" else .25, **r) for r in m.scores(subset, name, s)]
        for key in pilot:
            region_rows += [dict(region_key=key, **r) for r in m.scores(region[region.region_key == key], name, s)]
    pd.DataFrame(rows).to_csv(out / "fixed_strength_regional_metrics.csv", index=False)
    pd.DataFrame(region_rows).to_csv(out / "pilot_regions.csv", index=False)
    manifest = json.loads((out / "manifest.json").read_text())
    manifest["postanalysis"] = "Общая сила 0,25: полный состав, пять пилотов и прочие 68; без выбора новой модели по поздним метрикам"
    manifest["files"][str(Path(__file__).relative_to(ROOT))] = m.digest(Path(__file__))
    for file in ("fixed_strength_regional_metrics.csv", "pilot_regions.csv"):
        manifest["output_sha256"][file] = m.digest(out / file)
    m.write_json(out / "manifest.json", manifest)
    print(pd.DataFrame(rows).query("window == 'report' and evaluation == 'mean_1_to_H' and H == 3").pivot(index="model", columns="scope", values="MAE").round(2).to_string())


if __name__ == "__main__":
    main()
