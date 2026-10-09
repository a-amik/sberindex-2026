"""Региональные сигналы: изолированный скользящий эксперимент.

    .venv/bin/python scripts/09_regional_signals.py --probe
    .venv/bin/python scripts/09_regional_signals.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from sbi import backtest, config, metrics
from sbi.models.regional_signals import RegionalContext, prepare_regional

ROOT = config.ROOT
OUT = ROOT / "results" / "regional_signals"
KEYS = ["row", "origin", "step"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def as_frame(base, corrections, context):
    f = base.copy()
    if corrections:
        t = f.origin.map({p: i for i, p in enumerate(context.panel.periods)}).to_numpy()
        row, h = f.row.to_numpy(), f.step.to_numpy() - 1
        delta = np.zeros(len(f))
        for origin in np.unique(t):
            ix = t == origin
            if origin in corrections:
                delta[ix] = corrections[origin][context.cell_of_row[row[ix]], h[ix]]
        f["log_correction"] = delta
    else:
        f["log_correction"] = 0.0
    return f


def with_strength(frame, strength):
    # Интервалы базовой модели не оценивались для новой поправки.
    out = frame.drop(columns=[c for c in ("q05", "q95") if c in frame]).copy()
    out["yhat"] = out.yhat.to_numpy() * np.exp(strength * out.log_correction.to_numpy())
    return out


def selected_rows(frame, settings):
    return frame[(frame.origin <= settings["selection_last_origin"]) &
                 (frame.target <= settings["selection_last_target"]) &
                 (frame.step <= settings["selection_max_step"])]


def scores(frame, name, settings):
    rows = []
    for window in ("all", "report"):
        part = frame if window == "all" else frame[frame.origin >= settings["report_from"]]
        for H in settings["horizons"]:
            d = metrics.horizon_rows(part, H, "2024-12")
            if d.empty:
                continue
            for evaluation, g in [("mean_1_to_H", d), ("step_H", d[d.step == H])]:
                rows.append({"model": name, "window": window, "H": H, "evaluation": evaluation,
                             "origins": g.origin.nunique(), "target_months": g.target.nunique(),
                             **metrics.scores(g)})
    return rows


def regional_frame(f, panel, mo):
    mapping = panel.index.merge(mo[["territory_id", "region_key", "pop"]], on="territory_id",
                                how="left", validate="many_to_one")
    g = f.merge(mapping.reset_index(names="row"), on="row", how="left", validate="many_to_one")
    g = g[g["pop"].notna() & (g["pop"] > 0)].copy()
    for col in ("y", "yhat", "y_origin"):
        g[col] *= g["pop"]
    d = g.groupby(["origin", "step", "target", "region_key", "category"], observed=True)
    out = d.agg(y=("y", "sum"), yhat=("yhat", "sum"), y_origin=("y_origin", "sum"),
                pop=("pop", "sum"), n_mo=("row", "size")).reset_index()
    for col in ("y", "yhat", "y_origin"):
        out[col] /= out["pop"]
    out["row"] = pd.factorize(pd.MultiIndex.from_frame(out[["region_key", "category"]]))[0]
    return out


def compute(context, settings, variants):
    forecasts, audits = {}, []
    for name, variant in variants.items():
        start = time.monotonic()
        corrections = {}
        for t in range(context.panel.pos(settings["first_origin"]), context.panel.pos(settings["last_origin"]) + 1):
            steps = context.base[t].shape[1]
            corr, audit = context.predict(t, steps, variant["signals"], variant["estimator"])
            corrections[t] = corr
            audits.append({"model": name, "origin": context.panel.periods[t], **audit})
        forecasts[name] = as_frame(BASE, corrections, context)
        print(f"{name}: {time.monotonic()-start:.1f} с", flush=True)
    return forecasts, audits


def main():
    global BASE, OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "configs" / "regional_signals.yaml"))
    ap.add_argument("--output", default=str(OUT))
    args = ap.parse_args()
    cfg = config.load(args.config)
    OUT = Path(args.output)
    s = cfg["regional_signals"]
    P, FC = cfg.path("processed"), ROOT / "results" / "forecasts"
    panel = backtest.load_panel(P)
    mo = pd.read_parquet(P / "mo.parquet")
    cpi_path = cfg.path("external") / "rosstat" / "cpi_regions.parquet"
    wage_path = cfg.path("external") / "rosstat" / "wages_regions.parquet"
    regional_data = prepare_regional(pd.read_parquet(cpi_path), pd.read_parquet(wage_path))
    BASE = pd.read_parquet(FC / f"{s['base']}.parquet").sort_values(KEYS).reset_index(drop=True)
    names = [s["base"], *s["compare"]]
    paths = [P / x for x in ("panel.parquet", "mo.parquet", "regional.parquet", "national.parquet", "news_region.parquet")]
    paths += [cpi_path, wage_path, cfg.path("external") / "weather.parquet", Path(args.config).resolve(),
              ROOT / "src" / "sbi" / "models" / "regional_signals.py", Path(__file__).resolve(),
              ROOT / "docs" / "regional_signals_protocol.md"]
    if "protocol" in s:
        paths.append(ROOT / s["protocol"])
    paths += [FC / f"{n}.parquet" for n in names]
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "settings": s,
                "files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
                "series": len(panel.y), "months": len(panel.periods)}
    context = RegionalContext(panel, mo, BASE, regional_data,
                              pd.read_parquet(cfg.path("external") / "weather.parquet"),
                              pd.read_parquet(P / "national.parquet"), pd.read_parquet(P / "news_region.parquet"), s)
    print(f"Рядов {len(panel.y)}, субъектов {len(context.regions)}, региональных ячеек {len(context.cells)}", flush=True)
    if args.probe:
        start = time.monotonic()
        t = panel.pos("2024-06")
        corr, audit = context.predict(t, 6, ["macro", "weather", "calendar", "news"], "ridge")
        print(json.dumps({"seconds": time.monotonic()-start, "shape": list(corr.shape),
                          "max_abs_correction": float(abs(corr).max()), **audit}, ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "manifest.json", manifest)
    import shutil
    for path in paths:
        if path.suffix in (".py", ".yaml", ".md"):
            snapshot = OUT / "source" / path.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, snapshot)
    raw, audits = compute(context, s, s["variants"])
    selection = []
    for name, frame in raw.items():
        g = selected_rows(frame, s)
        for strength in s["strengths"]:
            error = abs(g.y.to_numpy() - g.yhat.to_numpy() * np.exp(strength * g.log_correction.to_numpy()))
            selection.append({"variant": name, "strength": strength, "MAE": float(error.mean()), "n": len(g),
                              "last_target": g.target.max()})
    select = pd.DataFrame(selection).sort_values(["MAE", "strength", "variant"], kind="stable")
    select.to_csv(OUT / "selection.csv", index=False)
    best = select.iloc[0]
    control = select[select.variant == "controls"].iloc[0]
    chosen = {"variant": str(best.variant), "strength": float(best.strength), "select_MAE": float(best.MAE),
              "control_strength": float(control.strength), "selection_last_target": s["selection_last_target"],
              "report_from": s["report_from"]}
    # Выбор записывается до вычисления метрик последующего окна.
    write_json(OUT / "choice.json", chosen)
    frames = {"base": BASE}
    for name in s["compare"]:
        frames[name] = pd.read_parquet(FC / f"{name}.parquet").sort_values(KEYS).reset_index(drop=True)
        if not frames[name][KEYS + ["target", "y", "y_origin"]].equals(BASE[KEYS + ["target", "y", "y_origin"]]):
            raise ValueError(f"У {name} другая сетка прогнозов")
    for name, frame in raw.items():
        weight = select[select.variant == name].iloc[0].strength
        frames[name] = with_strength(frame, float(weight))
    frames["selected"] = with_strength(raw[best.variant], float(best.strength))
    frames["selected"].to_parquet(OUT / "selected_forecast.parquet", index=False)

    # Та же выбранная модель и сила, но наблюдения внешних рядов старше на месяц.
    delayed_settings = dict(s, release_lags={k: v + 1 if k != "news" else v for k, v in s["release_lags"].items()})
    delayed = RegionalContext(panel, mo, BASE, regional_data,
                              pd.read_parquet(cfg.path("external") / "weather.parquet"),
                              pd.read_parquet(P / "national.parquet"), pd.read_parquet(P / "news_region.parquet"), delayed_settings)
    delayed_raw, delayed_audit = compute(delayed, s, {best.variant: s["variants"][best.variant]})
    frames["selected_delayed"] = with_strength(delayed_raw[best.variant], float(best.strength))
    write_json(OUT / "training_audit.json", audits + [{**a, "model": "selected_delayed"} for a in delayed_audit])

    municipal, regional, slices, paired = [], [], [], []
    for name, f in frames.items():
        municipal += scores(f, name, s)
        regional += scores(regional_frame(f, panel, mo), name, s)
        for H in (1, 3, 6):
            part = metrics.horizon_rows(f[f.origin >= s["report_from"]], H, "2024-12")
            idx = panel.index.merge(mo[["territory_id", "region_key"]], on="territory_id", how="left")
            g = part.merge(idx.reset_index(names="row"), on="row", how="left")
            g["error"] = abs(g.yhat - g.y)
            for level in ("category", "region_key"):
                for key, group in g.groupby(level, observed=True):
                    slices.append({"model": name, "H": H, "level": level, "key": str(key),
                                   "MAE": float(group.error.mean()), "n": len(group)})
    for ref in dict.fromkeys(["base", *s["compare"], "controls"]):
        for H in (1, 3, 6):
            a = frames["selected"][frames["selected"].origin >= s["report_from"]]
            b = frames[ref][frames[ref].origin >= s["report_from"]]
            paired.append({"reference": ref, **metrics.compare(a, b, H, "2024-12", s["bootstrap"], s["seed"])})
    pd.DataFrame(municipal).to_csv(OUT / "municipal_metrics.csv", index=False)
    pd.DataFrame(regional).to_csv(OUT / "regional_metrics.csv", index=False)
    pd.DataFrame(slices).to_csv(OUT / "slices.csv", index=False)
    pd.DataFrame(paired).to_csv(OUT / "comparisons.csv", index=False)
    example = context.features(panel.pos("2024-06"), 1)
    coverage = [{"feature": c, "nonmissing_share": float(example[c].notna().mean()), "unique_values": int(example[c].nunique())}
                for c in example]
    pd.DataFrame(coverage).to_csv(OUT / "feature_coverage.csv", index=False)
    raw_corrections = []
    for name, f in raw.items():
        cell_f = f.assign(cell=context.cell_of_row[f.row.to_numpy()])
        raw_corrections.append(cell_f.groupby(["origin", "step", "cell"]).log_correction.first().reset_index().assign(model=name))
    pd.concat(raw_corrections, ignore_index=True).to_parquet(OUT / "corrections.parquet", index=False)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["population_missing_series"] = int(panel.index.merge(mo[["territory_id", "pop"]], on="territory_id")["pop"].isna().sum())
    manifest["regional_cells"] = len(context.cells)
    manifest["regions"] = len(context.regions)
    write_json(OUT / "manifest.json", manifest)
    print("Выбор:", chosen, flush=True)
    report = pd.DataFrame(municipal).query("window == 'report' and evaluation == 'mean_1_to_H'")
    print(report.pivot(index="model", columns="H", values="MAE").round(2).to_string(), flush=True)


if __name__ == "__main__":
    main()
