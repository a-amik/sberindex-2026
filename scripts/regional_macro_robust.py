"""Выбор макропоправки, выдерживающей две политики задержки."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, config, metrics
from sbi.models.macro_components import MacroComponents
from sbi.models.regional_signals import prepare_regional

spec = importlib.util.spec_from_file_location("runner", ROOT / "scripts/09_regional_signals.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def choose_robust(rows, settings):
    d = pd.DataFrame(rows)
    if d.empty:
        return dict(variant="base", strength=0.0)
    group = d.groupby(["variant", "strength"])
    summary = group.agg(worst_regional_MAE=("regional_MAE", "max"),
        minimum_gain_pct=("regional_gain_pct", "min"), maximum_loss_pct=("municipal_loss_pct", "max"),
        active_origins=("active_origins", "min"), policies=("policy", "nunique")).reset_index()
    valid = summary[(summary.minimum_gain_pct >= settings["minimum_regional_gain_pct"]) &
                    (summary.maximum_loss_pct <= settings["maximum_municipal_loss_pct"]) &
                    (summary.active_origins >= settings["minimum_active_origins"]) &
                    (summary.policies == len(settings["policies"]))]
    if valid.empty:
        return dict(variant="base", strength=0.0)
    return valid.sort_values(["worst_regional_MAE", "strength", "variant"], kind="stable").iloc[0].to_dict()


def main():
    cp = ROOT / "configs/regional_macro_robust.json"
    s = json.loads(cp.read_text())
    cfg = config.load(ROOT / "configs/regional_signals_chronos.yaml")
    defaults = cfg["regional_signals"]
    out = ROOT / "results/regional_macro_robust"
    out.mkdir(parents=True, exist_ok=True)
    pp = cfg.path("processed")
    external = cfg.path("external")
    paths = [cp, Path(__file__), ROOT / "src/sbi/models/macro_components.py", ROOT / "src/sbi/models/regional_signals.py",
        ROOT / "src/sbi/metrics.py", ROOT / "scripts/09_regional_signals.py", ROOT / "docs/regional_macro_robust.md",
        ROOT / "configs/regional_signals_chronos.yaml", pp / "panel.parquet", pp / "mo.parquet", pp / "national.parquet",
        pp / "news_region.parquet", external / "weather.parquet", external / "rosstat/cpi_regions.parquet",
        external / "rosstat/wages_regions.parquet", ROOT / f"results/forecasts/{s['base']}.parquet", ROOT / "results/forecasts/ensemble.parquet"]
    manifest = dict(started_at=datetime.now(timezone.utc).isoformat(), settings=s,
        status="exploratory_after_prior_report", files={str(p.relative_to(ROOT)): m.digest(p) for p in paths})
    m.write_json(out / "manifest.json", manifest)
    for p in paths:
        if p.suffix in (".py", ".md", ".yaml", ".json"):
            target = out / "source" / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
    panel = backtest.load_panel(pp)
    mo = pd.read_parquet(pp / "mo.parquet")
    regional = prepare_regional(pd.read_parquet(external / "rosstat/cpi_regions.parquet"), pd.read_parquet(external / "rosstat/wages_regions.parquet"))
    weather, national, news = (pd.read_parquet(p) for p in [external / "weather.parquet", pp / "national.parquet", pp / "news_region.parquet"])
    base = pd.read_parquet(ROOT / f"results/forecasts/{s['base']}.parquet").sort_values(m.KEYS).reset_index(drop=True)
    rbase = m.regional_frame(base, panel, mo)
    raw, audits, correction_rows = {}, [], []
    context = None
    for policy, delays in s["policies"].items():
        settings = dict(defaults, release_lags={**defaults["release_lags"], **delays})
        context = MacroComponents(panel, mo, base, regional, weather, national, news, settings)
        context.cells.reset_index(names="cell").to_csv(out / "cells.csv", index=False)
        for variant, signals in s["variants"].items():
            corrections = {}
            for t in range(panel.pos(s["first_origin"]), panel.pos(s["last_origin"]) + 1):
                available = context.base[t].shape[1]
                corr, audit = context.predict(t, min(available, 3), signals, "ridge")
                full = np.zeros((len(context.cells), available))
                full[:, :corr.shape[1]] = corr
                corrections[t] = full
                audits.append(dict(policy=policy, variant=variant, origin=panel.periods[t], **audit))
                for step in range(corr.shape[1]):
                    correction_rows.append(context.cells.reset_index(names="cell").assign(origin=panel.periods[t], step=step+1,
                        policy=policy, variant=variant, log_correction=corr[:, step]))
            raw[policy, variant] = m.as_frame(base, corrections, context)
            print(policy, variant, flush=True)
    correction = pd.concat(correction_rows, ignore_index=True)
    correction.to_parquet(out / "corrections.parquet", index=False)
    m.write_json(out / "training_audit.json", audits)
    choices, control_choices, selection = {}, {}, []
    for group, steps in s["groups"].items():
        early = (base.origin <= s["selection_last_origin"]) & (base.target <= s["selection_last_target"]) & base.step.isin(steps)
        er = (rbase.origin <= s["selection_last_origin"]) & (rbase.target <= s["selection_last_target"]) & rbase.step.isin(steps)
        mo_mae = metrics.scores(base[early])["MAE"]
        region_mae = metrics.scores(rbase[er])["MAE"]
        rows = []
        for (policy, variant), f in raw.items():
            active = f[early & (f.log_correction.abs() > 1e-12)].origin.nunique()
            for strength in s["strengths"]:
                pred = m.with_strength(f[early], strength)
                rm = metrics.scores(m.regional_frame(pred, panel, mo))["MAE"]
                mm = metrics.scores(pred)["MAE"]
                rows.append(dict(group=group, policy=policy, variant=variant, strength=strength,
                    regional_MAE=rm, municipal_MAE=mm, regional_gain_pct=100*(1-rm/region_mae),
                    municipal_loss_pct=100*(mm/mo_mae-1), active_origins=int(active), last_target=pred.target.max()))
        choices[group] = choose_robust(rows, s)
        control_choices[group] = choose_robust([r for r in rows if r["variant"] == "controls"], s)
        selection += rows
    pd.DataFrame(selection).to_csv(out / "selection.csv", index=False)
    m.write_json(out / "choice.json", dict(selected=choices, control=control_choices))
    # Последующее окно рассчитывается только после фиксации решения.
    frames = {"base": base, "ensemble": pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet").sort_values(m.KEYS).reset_index(drop=True)}
    for policy in s["policies"]:
        for label, chosen in (("selected", choices), ("control_selected", control_choices)):
            f = base.drop(columns=[c for c in ("q05", "q95") if c in base]).copy()
            for group, steps in s["groups"].items():
                a = chosen[group]
                if a["variant"] == "base":
                    continue
                ix = f.step.isin(steps)
                f.loc[ix, "yhat"] *= np.exp(a["strength"] * raw[policy, a["variant"]].loc[ix, "log_correction"])
            assert np.array_equal(f.loc[f.step >= 4, "yhat"], base.loc[base.step >= 4, "yhat"])
            frames[policy + "_" + label] = f
            if label == "selected":
                f.to_parquet(out / f"{policy}_forecast.parquet", index=False)
    settings = dict(s, horizons=[1, 3, 6, 12])
    results, slices, by_month = [], [], []
    def evaluate(name, frame, kind):
        for level, g in (("municipal", frame), ("regional", m.regional_frame(frame, panel, mo))):
            results.extend(dict(level=level, kind=kind, **r) for r in m.scores(g, name, settings))
            if level == "regional":
                late = g[g.origin >= s["report_from"]].copy()
                for H in (1, 3, 6):
                    h = metrics.horizon_rows(late, H, "2024-12").copy()
                    h["error"] = (h.y - h.yhat).abs()
                    for column in ("region_key", "category"):
                        a = h.groupby(column, observed=True).error.agg(["mean", "size"]).reset_index()
                        slices.extend(dict(model=name, kind=kind, H=H, level=column, key=str(r[column]), MAE=r["mean"], n=r["size"]) for _, r in a.iterrows())
                    a = h.groupby("target").error.agg(["mean", "size"]).reset_index()
                    by_month.extend(dict(model=name, kind=kind, H=H, target=r.target, MAE=r["mean"], n=r["size"]) for _, r in a.iterrows())
    for name, f in frames.items():
        evaluate(name, f, "choice")
    for (policy, variant), f in raw.items():
        evaluate(policy + "_" + variant, m.with_strength(f, .25), "fixed_0.25")
    pd.DataFrame(results).to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(slices).to_csv(out / "slices.csv", index=False)
    pd.DataFrame(by_month).to_csv(out / "by_target_month.csv", index=False)
    compare = []
    for policy in s["policies"]:
        for level in ("municipal", "regional"):
            transform = (lambda f: f) if level == "municipal" else (lambda f: m.regional_frame(f, panel, mo))
            a = transform(frames[policy + "_selected"])
            a = a[a.origin >= s["report_from"]]
            for name in ("base", "ensemble", policy + "_control_selected"):
                b = transform(frames[name]);b = b[b.origin >= s["report_from"]]
                for H in (1, 3, 6):
                    compare.append(dict(policy=policy, level=level, reference=name, **metrics.compare(a, b, H, "2024-12", s["bootstrap"], s["seed"])))
    pd.DataFrame(compare).to_csv(out / "comparisons.csv", index=False)
    for p in paths:
        if m.digest(p) != manifest["files"][str(p.relative_to(ROOT))]:
            raise ValueError("Вход изменился во время вычисления: " + str(p))
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["output_sha256"] = {p.name: m.digest(p) for p in out.glob("*") if p.is_file() and p.name != "manifest.json"}
    m.write_json(out / "manifest.json", manifest)
    print(json.dumps(choices, ensure_ascii=False, indent=2))
    print(pd.DataFrame(results).query("level == 'regional' and window == 'report' and evaluation == 'mean_1_to_H'").pivot(index="model", columns="H", values="MAE").round(2).to_string())


if __name__ == "__main__":
    main()
