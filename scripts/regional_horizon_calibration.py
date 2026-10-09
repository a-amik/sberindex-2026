"""Калибровка сохранённых поправок по коротким горизонтам."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics

spec = importlib.util.spec_from_file_location("signals_runner", ROOT / "scripts/09_regional_signals.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def select_candidates(candidates, settings):
    """Выбор из уже ограниченного по времени раннего окна."""
    d = pd.DataFrame(candidates)
    valid = d[(d.regional_gain_pct >= settings["minimum_regional_gain_pct"]) &
              (d.municipal_loss_pct <= settings["maximum_municipal_loss_pct"]) &
              (d.active_origins >= settings["minimum_active_origins"])]
    if valid.empty:
        return {"variant": "base", "strength": 0.0}
    return valid.sort_values(["regional_MAE", "strength", "variant"], kind="stable").iloc[0].to_dict()


def apply_choice(base, raw, choice, groups):
    out = base.drop(columns=[c for c in ("q05", "q95") if c in base]).copy()
    for group, steps in groups.items():
        selected = choice[group]
        if selected["variant"] == "base":
            continue
        ix = out.step.isin(steps)
        out.loc[ix, "yhat"] *= np.exp(selected["strength"] * raw[selected["variant"]].loc[ix, "log_correction"])
    return out


def main():
    cfgpath = ROOT / "configs/regional_horizon_calibration.json"
    s = json.loads(cfgpath.read_text())
    source = ROOT / s["corrections_run"]
    out = ROOT / "results/regional_horizon_calibration"
    out.mkdir(parents=True, exist_ok=True)
    paths = [cfgpath, Path(__file__), ROOT / "docs/regional_horizon_calibration.md",
             source / "corrections.parquet", source / "training_audit.json", source / "manifest.json",
             ROOT / "data/processed/panel.parquet", ROOT / "data/processed/mo.parquet",
             ROOT / f"results/forecasts/{s['base']}.parquet", ROOT / "results/forecasts/ensemble.parquet",
             ROOT / "src/sbi/metrics.py", ROOT / "scripts/09_regional_signals.py"]
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "settings": s,
                "status": "exploratory_after_viewing_prior_report", "files": {str(p.relative_to(ROOT)): runner.digest(p) for p in paths}}
    runner.write_json(out / "manifest.json", manifest)
    import shutil
    for path in paths:
        if path.suffix in (".py", ".json", ".md"):
            target = out / "source" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    mapping = panel.index.merge(mo[["territory_id", "region_key"]], on="territory_id", validate="many_to_one")
    cells = mapping[["region_key", "category"]].drop_duplicates().sort_values(["region_key", "category"]).reset_index(drop=True)
    cells["category"] = cells.category.astype(str)
    cell_lookup = {tuple(row): i for i, row in enumerate(cells.itertuples(index=False, name=None))}
    mapping["cell"] = [cell_lookup[(r, str(c))] for r, c in zip(mapping.region_key, mapping.category)]
    cells.reset_index(names="cell").to_csv(out / "cells.csv", index=False)
    base = pd.read_parquet(paths[8]).sort_values(runner.KEYS).reset_index(drop=True)
    original = json.loads((source / "manifest.json").read_text())
    base_key = str(paths[8].relative_to(ROOT))
    if runner.digest(paths[8]) != original["files"][base_key]:
        raise ValueError("Базовый прогноз изменён после вычисления поправок")
    corrections = pd.read_parquet(source / "corrections.parquet")
    keyed = base.assign(cell=mapping.cell.to_numpy()[base.row.to_numpy()])
    raw = {}
    selection_rows, choice, control_choice = [], {}, {}
    for variant in s["variants"]:
        raw[variant] = keyed.merge(corrections[corrections.model == variant].drop(columns="model"),
                                   on=["origin", "step", "cell"], how="left", validate="many_to_one")
        if raw[variant].log_correction.isna().any() or not raw[variant][runner.KEYS].equals(base[runner.KEYS]):
            raise ValueError("Неполная или переставленная сетка поправок")
    for group, steps in s["groups"].items():
        early = (base.origin <= s["selection_last_origin"]) & (base.target <= s["selection_last_target"]) & base.step.isin(steps)
        baseline = base[early]
        region_mae = metrics.scores(runner.regional_frame(baseline, panel, mo))["MAE"]
        mo_mae = metrics.scores(baseline)["MAE"]
        candidates = []
        for variant in s["variants"]:
            active = raw[variant][early & (raw[variant].log_correction.abs() > 1e-12)].origin.nunique()
            for strength in s["strengths"]:
                f = runner.with_strength(raw[variant][early], strength)
                rm = metrics.scores(runner.regional_frame(f, panel, mo))["MAE"]
                mm = metrics.scores(f)["MAE"]
                candidates.append(dict(group=group, variant=variant, strength=strength, regional_MAE=rm,
                    municipal_MAE=mm, regional_gain_pct=100*(1-rm/region_mae), municipal_loss_pct=100*(mm/mo_mae-1),
                    active_origins=int(active), origins=int(f.origin.nunique()), last_target=f.target.max()))
        selection_rows.extend(candidates)
        choice[group] = select_candidates(candidates, s)
        control_choice[group] = select_candidates([c for c in candidates if c["variant"] == "controls"], s)
    pd.DataFrame(selection_rows).to_csv(out / "selection.csv", index=False)
    runner.write_json(out / "choice.json", {"selected": choice, "control": control_choice})
    frames = {"base": base, "selected": apply_choice(base, raw, choice, s["groups"]),
              "controls": apply_choice(base, raw, control_choice, s["groups"]),
              "prior_weather": pd.read_parquet(source / "selected_forecast.parquet").sort_values(runner.KEYS).reset_index(drop=True),
              "ensemble": pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet").sort_values(runner.KEYS).reset_index(drop=True)}
    frames["selected"].to_parquet(out / "selected_forecast.parquet", index=False)
    settings = dict(s, horizons=[1, 3, 6, 12])
    for level in ("municipal", "regional"):
        rows = []
        for name, f in frames.items():
            d = f if level == "municipal" else runner.regional_frame(f, panel, mo)
            rows += runner.scores(d, name, settings)
        pd.DataFrame(rows).to_csv(out / f"{level}_metrics.csv", index=False)
    comparisons = []
    for level in ("municipal", "regional"):
        transform = (lambda f: f) if level == "municipal" else (lambda f: runner.regional_frame(f, panel, mo))
        a = transform(frames["selected"].query("origin >= @s['report_from']"))
        for ref in ("base", "ensemble", "controls"):
            b = transform(frames[ref].query("origin >= @s['report_from']"))
            for H in (1, 3, 6):
                comparisons.append(dict(level=level, reference=ref, **metrics.compare(a, b, H, "2024-12", s["bootstrap"], s["seed"])))
    pd.DataFrame(comparisons).to_csv(out / "comparisons.csv", index=False)
    # Длинные отдельные шаги должны совпасть с базой побитово.
    long = base.step >= 4
    assert np.array_equal(frames["selected"].loc[long, "yhat"], base.loc[long, "yhat"])
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["output_sha256"] = {p.name: runner.digest(p) for p in out.glob("*") if p.is_file() and p.name != "manifest.json"}
    runner.write_json(out / "manifest.json", manifest)
    print(json.dumps(choice, ensure_ascii=False, indent=2))
    print(pd.read_csv(out / "regional_metrics.csv").query("window == 'report' and evaluation == 'mean_1_to_H'").pivot(index="model", columns="H", values="MAE").round(2).to_string())


if __name__ == "__main__":
    main()
