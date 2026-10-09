from pathlib import Path
import importlib.util
import json
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from sbi.models.prospective_signals import ProspectiveContext

spec = importlib.util.spec_from_file_location("regional_runner", ROOT / "scripts/09_regional_signals.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    cfg = json.loads((ROOT / "configs/wordstat_pilot.json").read_text())
    rows, paths = [], []
    for p in (ROOT / "data/external/wordstat").glob("*.json"):
        a = json.loads(p.read_text())
        if "query" not in a:
            continue
        paths.append(p)
        values = a["response"]["graph"]["images"]["timeSeries"]["preparedValues"]
        shares = {(v["year"], v["month"]): v["y"] for v in values["relative"]}
        for v in values["absolute"]:
            rows.append(dict(region_key=a["region"]["key"], category=a["query"]["category"],
                phrase=a["query"]["phrase"], period=f"{v['year']}-{v['month']+1:02}", count=v["y"],
                share_pct=shares[v["year"], v["month"]], retrieved_at=a["retrieved_at"]))
    search = pd.DataFrame(rows)
    if len(paths) != len(cfg["regions"]) * len(cfg["queries"]) or len(search) != 1080:
        raise ValueError("Неполная поисковая выгрузка")
    if search.groupby(["region_key", "category"]).period.nunique().ne(36).any():
        raise ValueError("Неполная история")
    search.to_parquet(ROOT / "data/external/wordstat/pilot.parquet", index=False)
    ProspectiveContext.search_data = search
    ep = ROOT / "data/external/announced_events/events.json"
    ProspectiveContext.event_data = json.loads(ep.read_text())
    runner.RegionalContext = ProspectiveContext
    out = ROOT / "results/regional_prospective_signals"
    out.mkdir(parents=True, exist_ok=True)
    paths += [ep, ROOT / "configs/wordstat_pilot.json", Path(__file__),
              ROOT / "scripts/collect_wordstat_pilot.cjs", ROOT / "src/sbi/models/prospective_signals.py"]
    paths += list((ep.parent).glob("*.html"))
    input_hashes = {str(p.relative_to(ROOT)): runner.digest(p) for p in paths}
    runner.write_json(out / "prospective_inputs.json", input_hashes)
    sys.argv = [__file__, "--config", str(ROOT / "configs/regional_prospective_signals.yaml"), "--output", str(out)]
    runner.main()
    manifest = json.loads((out / "manifest.json").read_text())
    for p in paths:
        if runner.digest(p) != input_hashes[str(p.relative_to(ROOT))]:
            raise ValueError("Вход изменился во время опыта")
        if p.suffix in (".py", ".cjs", ".json") and "data/external" not in str(p):
            target = out / "source" / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
    manifest["files"].update(input_hashes)
    manifest["status"] = "exploratory; current historical search vintage; only two announced events"
    manifest["search_regional_coverage"] = [r["key"] for r in cfg["regions"] if r["key"] != "russia"]
    manifest["output_sha256"] = {p.name: runner.digest(p) for p in out.glob("*") if p.is_file() and p.name != "manifest.json"}
    runner.write_json(out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
