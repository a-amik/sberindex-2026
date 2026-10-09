"""Шаг 5. Детекторы точек структурных изменений: полусинтетический бенчмарк
и прогон на реальных данных.

    python scripts/05_detect.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config, detect  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

OUT = ROOT / "results" / "metrics"


def neighbours(panel, nb):
    row_of = {(tid, c): i for i, (tid, c) in enumerate(zip(panel.index.territory_id, panel.index.category.astype(str)))}
    m = nb.groupby("territory_id").neighbour_id.apply(list).to_dict()
    return [[row_of[(j, c)] for j in m.get(tid, []) if (j, c) in row_of]
            for tid, c in zip(panel.index.territory_id, panel.index.category.astype(str))]


def thresholds(scores, first):
    v = scores[:, first:].ravel()
    v = v[v > 0]
    if not len(v):
        return [np.inf]
    return sorted(set(np.quantile(v, np.linspace(0.80, 0.999, 40)).round(4)))


def valve(alarm, groups, share):
    """Предохранитель: если в группе за месяц тревожит больше доли share рядов,
    это шок группы, а не МО — такие тревоги снимаются."""
    a = alarm.copy()
    for g in np.unique(groups):
        s = groups == g
        frac = a[s].mean(axis=0)
        a[np.ix_(s, frac > share)] = False
    return a


def main():
    cfg, _ = config.cli(__doc__)
    dc = cfg["detect"]
    P = cfg.path("processed")
    panel = backtest.load_panel(P, "full")
    mo = pd.read_parquet(P / "mo.parquet")
    groups = panel_models.groups(panel.index, mo, "type")
    nb_rows = neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))

    draws = {}
    for tag, seed in (("tune", dc["seed_tune"]), ("test", dc["seed_test"])):
        rng = np.random.default_rng(seed)
        y2, truth = detect.inject(panel.y, rng, dc["share"], dc["sizes"], dc["kinds"], dc["first"], dc["last"])
        d = detect.signal(y2, groups)
        sc = {m: detect.run_online(d, groups, nb_rows, m) for m in dc["methods"]}
        draws[tag] = (y2, truth, d, sc)
        print(f"· выборка {tag}: шоков {int((truth['tau'] >= 0).sum()):,}")

    rows, chosen = [], {}
    _, t_tune, _, s_tune = draws["tune"]
    _, t_test, d_test, s_test = draws["test"]
    for m in dc["methods"]:
        if m == "zero":
            th, f1_tune = np.inf, 0.0
        else:
            f1_tune, th = max(((detect.evaluate(s_tune[m] > th, t_tune, dc["first"], dc["max_delay"])["f1"], th)
                               for th in thresholds(s_tune[m], dc["first"])))
        chosen[m] = th
        r = detect.evaluate(s_test[m] > th, t_test, dc["first"], dc["max_delay"])
        rows.append({"method": m, "threshold": th, "f1_tune": f1_tune, **{k: v for k, v in r.items() if k != "recall_by"},
                     **{f"recall_{k}": v for k, v in r["recall_by"].items()}})

    # двухуровневая схема: лучший онлайн-детектор по F1 настроечной выборки + предохранитель
    # + подтверждение PELT. До 04.10.2026 ведущий метод и пара выбирались по F1 отчётной выборки.
    tab = pd.DataFrame(rows)
    lead = tab[tab.method != "zero"].sort_values("f1_tune", ascending=False).iloc[0].method
    for share in (dc["valve_share"],):
        a = valve(s_test[lead] > chosen[lead], groups, share)
        r = detect.evaluate(a, t_test, dc["first"], dc["max_delay"])
        rows.append({"method": f"{lead}+valve", "threshold": chosen[lead],
                     **{k: v for k, v in r.items() if k != "recall_by"},
                     **{f"recall_{k}": v for k, v in r["recall_by"].items()}})
    # согласие двух лучших по настроечной выборке: тревога в t, когда к t сработали оба
    # (каждый в t или t−1), и тревога любого из двух
    top2 = tab[tab.method != "zero"].sort_values("f1_tune", ascending=False).method.tolist()[:2]
    a1, a2 = s_test[top2[0]] > chosen[top2[0]], s_test[top2[1]] > chosen[top2[1]]
    for name, a in ((f"{top2[0]}&{top2[1]}", detect.agree(a1, a2)), (f"{top2[0]}|{top2[1]}", a1 | a2)):
        r = detect.evaluate(a, t_test, dc["first"], dc["max_delay"])
        rows.append({"method": name, "threshold": np.nan, **{k: v for k, v in r.items() if k != "recall_by"},
                     **{f"recall_{k}": v for k, v in r["recall_by"].items()}})
    # для подтверждения берём порог мягче: PELT отсеет лишнее
    loose = np.quantile(s_tune[lead][:, dc["first"]:].ravel(), 0.95)
    base_alarm = valve(s_test[lead] > loose, groups, dc["valve_share"])
    scale_t = {t: detect.group_scale(d_test, groups, t) for t in range(d_test.shape[1])}
    for pen in dc["pelt_pen"]:
        conf = np.zeros_like(base_alarm)
        for i, t in zip(*np.where(base_alarm)):
            if t + 1 < d_test.shape[1] and detect.confirm_pelt(d_test[i], t, pen, scale_t[t + 1][i]):
                conf[i, t + 1] = True                    # подтверждение приходит месяцем позже
        r = detect.evaluate(conf, t_test, dc["first"], dc["max_delay"])
        rows.append({"method": f"{lead}+pelt(pen={pen})", "threshold": float(loose),
                     **{k: v for k, v in r.items() if k != "recall_by"},
                     **{f"recall_{k}": v for k, v in r["recall_by"].items()}})

    tab = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT / "detect_benchmark.csv", index=False)
    cols = ["method", "recall", "precision", "f1", "fa_per_100", "delay_mean", "recall_over_random",
            "recall_step", "recall_ramp", "recall_spike", "recall_size_0.1", "recall_size_0.3"]
    print("\nПолусинтетика, выборка для отчёта (порог подобран на другой):")
    print(tab[[c for c in cols if c in tab]].round(3).to_string(index=False))

    # реальные данные: лучший детектор без внесённых шоков
    d_real = detect.signal(panel.y, groups)
    s_real = detect.run_online(d_real, groups, nb_rows, lead)
    a_real = s_real > chosen[lead]
    a_valve = valve(a_real, groups, dc["valve_share"])
    by_month = pd.DataFrame({"period": panel.periods, "alarms": a_real.sum(axis=0),
                             "alarms_after_valve": a_valve.sum(axis=0),
                             "share_pct": (a_real.mean(axis=0) * 100).round(2)})
    by_month.to_csv(OUT / "detect_real_by_month.csv", index=False)
    print(f"\nРеальные данные, {lead}: тревоги по месяцам")
    print(by_month[by_month.period >= panel.periods[detect.MIN_HIST]].to_string(index=False))
    idx = panel.index.assign(group=groups)
    alarms = [{"territory_id": int(idx.territory_id[i]), "category": str(idx.category[i]),
               "period": panel.periods[t], "score": float(s_real[i, t])}
              for i, t in zip(*np.where(a_valve))]
    pd.DataFrame(alarms).merge(mo[["territory_id", "name", "region"]], on="territory_id") \
        .to_csv(OUT / "detect_real_alarms.csv", index=False)
    json.dump({"lead": lead, "pair": top2, "thresholds": {k: float(v) for k, v in chosen.items()}},
              open(OUT / "detect_choice.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
