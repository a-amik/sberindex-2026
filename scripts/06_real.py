"""Шаг 6. Реальные кейсы и раннее предупреждение.

* апрель 2023 — шок группы: если фактор считать по категории без деления
  на город и район, районы массово уходят от фактора, и предохранитель
  узнаёт шок группы;
* паводки весны 2024 — доля тревог в трёх паводковых субъектах против
  остальной страны до и после события;
* раннее предупреждение — вероятность тревоги у МО в следующем месяце;
  скользящая проверка: учимся на месяцах до t, проверяем на t + 1.

    python scripts/06_real.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from sbi import backtest, config, detect  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

OUT = ROOT / "results" / "metrics"
neighbours = __import__("05_detect").neighbours




def main():
    cfg, _ = config.cli(__doc__)
    P = cfg.path("processed")
    panel = backtest.load_panel(P, "full")
    mo = pd.read_parquet(P / "mo.parquet")
    idx = panel.index.merge(mo[["territory_id", "name", "region", "mo_type"]], on="territory_id", how="left")
    g_type = panel_models.groups(panel.index, mo, "type")
    g_cat = panel_models.groups(panel.index, mo, "category")
    nb_rows = neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))
    ch = detect.choice(OUT / "detect_choice.json")
    th = ch["thresholds"]
    per = panel.periods
    report = {}

    # — апрель 2023: фактор по категории без деления на город и район
    d_cat = detect.signal(panel.y, g_cat)
    z = detect.run_online(d_cat, g_cat, nb_rows, "zscore", start=3) > th["zscore"]
    urban = idx.mo_type.isin(panel_models.URBAN).to_numpy()
    t_apr = per.index("2023-04")
    report["april_2023"] = {
        "alarm_share_district_pct": round(float(z[~urban, t_apr].mean() * 100), 2),
        "alarm_share_city_pct": round(float(z[urban, t_apr].mean() * 100), 2),
        "alarm_share_district_other_months_pct": round(float(np.delete(z[~urban], t_apr, axis=1)[:, 4:].mean() * 100), 2),
        "by_category_district_pct": {c: round(float(z[(~urban) & (panel.index.category.astype(str) == c).to_numpy(), t_apr].mean() * 100), 1)
                                     for c in panel.index.category.astype(str).unique()},
    }

    # — паводки 2024
    d = detect.signal(panel.y, g_type)
    a_and, a_z, a_b = detect.alarm_pair(d, g_type, nb_rows, ch)   # a_z — тревоги ведущего детектора
    fc = cfg["cases"]["floods_2024"]
    flood = idx.region.isin(fc["regions"]).to_numpy()
    w0, w1 = per.index(fc["window"][0]), per.index(fc["window"][1]) + 1
    b0, b1 = per.index(fc["before"][0]), per.index(fc["before"][1]) + 1
    share = lambda mask, a, s, e: float(a[mask, s:e].any(axis=1).mean() * 100)
    report["floods_2024"] = {
        "series_flood_regions": int(flood.sum()),
        "alarm_any_pct": {"flood_after": round(share(flood, a_z, w0, w1), 1),
                          "flood_before": round(share(flood, a_z, b0, b1), 1),
                          "rest_after": round(share(~flood, a_z, w0, w1), 1),
                          "rest_before": round(share(~flood, a_z, b0, b1), 1)},
    }
    # сдвиг отклонения от фактора: апрель—июнь против января—марта, паводковые субъекты против остальных
    shift = d[:, w0:w1].mean(axis=1) - d[:, b0:b1].mean(axis=1)
    cats = panel.index.category.astype(str).to_numpy()
    report["floods_2024"]["shift_pct_by_category"] = {
        c: {"flood": round(float(np.median(shift[flood & (cats == c)]) * 100), 2),
            "rest": round(float(np.median(shift[~flood & (cats == c)]) * 100), 2)} for c in np.unique(cats)}
    top = [{"name": idx.name[i], "region": idx.region[i], "category": cats[i],
            "period": per[t], "dev_change_pct": round(float((d[i, t] - d[i, t - 3:t].mean()) * 100), 1)}
           for i, t in zip(*np.where(a_z[:, w0:w1] & flood[:, None])) for t in [t + w0]]
    report["floods_2024"]["alarms"] = sorted(top, key=lambda r: -abs(r["dev_change_pct"]))[:15]

    # — раннее предупреждение: тревога ведущего детектора в месяце t+1 по признакам месяца t
    zs = detect.run_online(d, g_type, nb_rows, "zscore")
    bs = detect.run_online(d, g_type, nb_rows, "bocpd")
    region = idx.region.to_numpy()
    rows = []
    for t in range(detect.MIN_HIST + 1, len(per) - 1):
        nb_al = np.array([a_z[r, t].mean() if r else 0.0 for r in nb_rows])
        reg = pd.Series(a_z[:, t]).groupby(region).transform("mean").to_numpy()
        x = d[:, : t + 1]
        rows.append(pd.DataFrame({
            "t": t, "row": np.arange(len(d)), "label": a_z[:, t + 1].astype(int),
            "z_now": zs[:, t], "z_max3": zs[:, t - 2:t + 1].max(axis=1), "b_now": bs[:, t],
            "alarm_now": a_z[:, t].astype(int), "nb_alarm": nb_al, "region_alarm": reg,
            "vol6": np.diff(x[:, -7:], axis=1).std(axis=1), "trend3": x[:, -1] - x[:, -4],
            "category": pd.Categorical(cats).codes, "district": (~urban).astype(int),
            "target_month": int(per[t + 1][5:7]),
        }))
    ds = pd.concat(rows, ignore_index=True)
    feats = [c for c in ds.columns if c not in ("t", "row", "label")]
    ew = cfg["early_warning"]
    res, k = [], ew["top_k"]
    for t in sorted(ds.t.unique()):
        if per[t + 1] < ew["first_target"]:
            continue
        tr, te = ds[ds.t < t], ds[ds.t == t]
        if tr.label.sum() < 20 or te.label.sum() == 0:
            continue
        m = lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=15, min_data_in_leaf=200,
                           verbose=-1, seed=42), lgb.Dataset(tr[feats], tr.label), num_boost_round=150)
        p = m.predict(te[feats])
        base = te.z_max3.to_numpy()                       # правило: недавний сильный балл — жди тревоги
        topk = np.argsort(-p)[:k]
        res.append({"target": per[t + 1], "positives": int(te.label.sum()), "rate_pct": round(te.label.mean() * 100, 2),
                    "auc_model": roc_auc_score(te.label, p), "auc_rule": roc_auc_score(te.label, base),
                    f"precision_top{k}": float(te.label.to_numpy()[topk].mean()),
                    f"precision_top{k}_rule": float(te.label.to_numpy()[np.argsort(-base)[:k]].mean())})
    ew_tab = pd.DataFrame(res)
    ew_tab.to_csv(OUT / "early_warning.csv", index=False)
    report["early_warning"] = {
        "months": len(ew_tab), "auc_model": round(float(ew_tab.auc_model.mean()), 3),
        "auc_rule": round(float(ew_tab.auc_rule.mean()), 3),
        f"precision_top{k}": round(float(ew_tab[f"precision_top{k}"].mean()), 3),
        f"precision_top{k}_rule": round(float(ew_tab[f"precision_top{k}_rule"].mean()), 3),
        "base_rate_pct": round(float(ew_tab.rate_pct.mean()), 2),
    }
    json.dump(report, open(OUT / "real_cases.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items()}, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
