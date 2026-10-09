"""Шаг 7. Новости: разметка, согласование с данными СберИндекса и проверка пользы.

Правила согласования:
* новость датируется публикацией по МСК, месяц СберИндекса — месяц публикации;
* в признак месяца t идут новости, вышедшие до конца t, — без заглядывания вперёд;
* география: МО — по газетиру, субъект — все МО субъекта; федеральные решения —
  все ряды;
* дубликаты одной новости в двух лентах в счётчиках не схлопываются нарочно:
  две ленты на одно событие — признак его масштаба.

Проверки:
* событийный анализ: отклонение МО от фактора в месяцы после местной новости
  о ЧС против МО той же группы без таких новостей;
* объяснимость тревог: доля реальных тревог детектора, у которых рядом
  по времени есть новость о том же МО или субъекте, против случайного совпадения;
* раннее предупреждение с новостями и без, и плацебо — новости, сдвинутые
  на шесть месяцев назад: настоящий выигрыш обязан исчезнуть.

    python scripts/07_news.py
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

from sbi import backtest, config, detect, newsgeo  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

OUT = ROOT / "results" / "metrics"
LOCAL = ["flood", "fire", "emergency", "attack", "plant", "layoff", "payments", "transport"]
SHOCK = ["disaster"]          # паводок или режим ЧС; пожары и аварии — слишком мелкий шум
neighbours = __import__("05_detect").neighbours


def main():
    cfg, _ = config.cli(__doc__)
    P = cfg.path("processed")
    mo = pd.read_parquet(P / "mo.parquet")
    raw = pd.read_parquet(cfg.path("external") / "news_headlines.parquet")
    gz = newsgeo.gazetteer(mo, cfg.path("raw") / "hackathon" / "t_dict_municipal_districts.xlsx")
    ann = newsgeo.annotate(raw, gz)
    ann.to_parquet(P / "news_annotated.parquet", index=False)
    reg_m, mo_m = newsgeo.monthly(ann, mo)
    reg_m.to_parquet(P / "news_region.parquet", index=False)
    mo_m.to_parquet(P / "news_mo.parquet", index=False)
    rep = {"headlines": int(len(ann)), "by_source": ann.source.value_counts().to_dict(),
           "typed_pct": round(float((ann.types.map(len) > 0).mean() * 100), 1),
           "with_region_pct": round(float((ann.regions.map(len) > 0).mean() * 100), 1),
           "with_mo_pct": round(float((ann.mos.map(len) > 0).mean() * 100), 1),
           "by_type": pd.Series([t for x in ann.types for t in x]).value_counts().to_dict()}
    # выборка для проверки точности глазами: по 25 на тип, с привязкой к МО
    smp = ann[ann.mos.map(len) > 0].explode("types").dropna(subset=["types"])
    smp = smp.sample(frac=1, random_state=1).groupby("types").head(25)
    smp.assign(mo_names=smp.mos.map(lambda m: "; ".join(mo.set_index("territory_id").name.get(x, "") for x in m)))[
        ["date", "source", "types", "title", "mo_names", "regions", "url"]].to_csv(OUT / "news_review_sample.csv", index=False)

    panel = backtest.load_panel(P, "full")
    per = panel.periods
    groups = panel_models.groups(panel.index, mo, "type")
    d = detect.signal(panel.y, groups)
    tid = panel.index.territory_id.to_numpy()
    rk = panel.index.merge(mo[["territory_id", "region_key"]], on="territory_id", how="left").region_key.to_numpy()
    cats = panel.index.category.astype(str).to_numpy()

    def counts(table, key, keyvals, types, shift=0):
        """Матрица ряды × месяцы: число новостей нужных типов о МО или субъекте ряда."""
        t = table.copy()
        cols = [c for c in types if c in t]
        t["n"] = t[cols].sum(axis=1) if cols else 0
        if shift:
            t["period"] = (pd.PeriodIndex(t.period, freq="M") - shift).strftime("%Y-%m")
        piv = t.pivot_table(index=key, columns="period", values="n", aggfunc="sum").reindex(columns=per).fillna(0)
        return piv.reindex(keyvals).fillna(0).to_numpy()

    n_mo = counts(mo_m, "territory_id", tid, SHOCK)
    n_reg = counts(reg_m, "region_key", rk, SHOCK)

    # — событийный анализ: первая местная новость о ЧС у МО в месяце t (t ≥ 3)
    ev = []
    for i in range(len(d)):
        hits = np.where(n_mo[i] > 0)[0]
        hits = hits[(hits >= 3) & (hits <= len(per) - 3)]
        if len(hits):
            t = hits[0]
            ev.append((i, t, d[i, t:t + 3].mean() - d[i, t - 3:t].mean()))
    ev = pd.DataFrame(ev, columns=["row", "t", "chg"])
    ctrl = []
    for (t, g), grp in ev.groupby([ev.t, groups[ev.row]]):
        pool = np.where((groups == g) & (n_mo.sum(axis=1) == 0))[0]
        ctrl.append(np.median(d[pool, t:t + 3].mean(axis=1) - d[pool, t - 3:t].mean(axis=1)))
    rng = np.random.default_rng(0)
    eff = ev.assign(cat=cats[ev.row]).groupby("cat").chg
    rep["event_study"] = {"events": int(len(ev)), "control_median_chg_pct": round(float(np.median(ctrl)) * 100, 2)}
    for c, x in eff:
        boot = [np.median(rng.choice(x.to_numpy(), len(x))) for _ in range(1000)]
        rep["event_study"][c] = {"n": int(len(x)), "median_chg_pct": round(float(np.median(x)) * 100, 2),
                                 "ci95": [round(float(np.percentile(boot, 2.5)) * 100, 2),
                                          round(float(np.percentile(boot, 97.5)) * 100, 2)]}

    # — объяснимость тревог детектора
    al = pd.read_csv(OUT / "detect_real_alarms.csv")
    pos = {p: i for i, p in enumerate(per)}
    row_of = {(a, b): i for i, (a, b) in enumerate(zip(tid, cats))}
    def explained(n_mat, rows, ts):
        return np.array([n_mat[r, max(0, t - 1): t + 1].sum() > 0 for r, t in zip(rows, ts)])
    rows = np.array([row_of[(a, b)] for a, b in zip(al.territory_id, al.category)])
    ts = np.array([pos[p] for p in al.period])
    rand_rows = rng.integers(0, len(d), len(rows) * 20)
    rand_ts = rng.integers(detect.MIN_HIST, len(per), len(rows) * 20)
    rep["alarm_explained"] = {
        "alarms": int(len(rows)),
        "by_mo_news_pct": round(float(explained(n_mo, rows, ts).mean() * 100), 2),
        "by_mo_news_random_pct": round(float(explained(n_mo, rand_rows, rand_ts).mean() * 100), 2),
        "by_region_news_pct": round(float(explained(n_reg, rows, ts).mean() * 100), 2),
        "by_region_news_random_pct": round(float(explained(n_reg, rand_rows, rand_ts).mean() * 100), 2),
    }
    ex = al.assign(mo_news=explained(n_mo, rows, ts), region_news=explained(n_reg, rows, ts))
    ex.to_csv(OUT / "detect_real_alarms_news.csv", index=False)

    # — раннее предупреждение с новостями и без, плюс плацебо
    ch = json.load(open(OUT / "detect_choice.json"))
    th = ch["thresholds"]
    nb_rows = neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))
    zs = detect.run_online(d, groups, nb_rows, "zscore")
    a = detect.run_online(d, groups, nb_rows, ch["lead"]) > th[ch["lead"]]   # метка — тревога ведущего детектора
    n_reg_pl = counts(reg_m, "region_key", rk, SHOCK, shift=6)
    n_mo_pl = counts(mo_m, "territory_id", tid, SHOCK, shift=6)
    def frame(t, nr, nm):
        return pd.DataFrame({"t": t, "label": a[:, t + 1].astype(int), "z_now": zs[:, t],
                             "z_max3": zs[:, t - 2:t + 1].max(axis=1), "vol6": np.diff(d[:, t - 6:t + 1], axis=1).std(axis=1),
                             "trend3": d[:, t] - d[:, t - 3], "category": pd.Categorical(cats).codes,
                             "news_region": nr[:, t], "news_mo": nm[:, t], "news_region_3m": nr[:, t - 2:t + 1].sum(axis=1)})
    res = {}
    for tag, nr, nm in (("with_news", n_reg, n_mo), ("placebo_shift6", n_reg_pl, n_mo_pl)):
        ds = pd.concat([frame(t, nr, nm) for t in range(detect.MIN_HIST + 2, len(per) - 1)], ignore_index=True)
        for feats_tag, feats in (("no_news", ["z_now", "z_max3", "vol6", "trend3", "category"]),
                                 (tag, ["z_now", "z_max3", "vol6", "trend3", "category", "news_region", "news_mo", "news_region_3m"])):
            aucs = []
            for t in sorted(ds.t.unique()):
                if per[t + 1] < "2024-01":
                    continue
                tr, te = ds[ds.t < t], ds[ds.t == t]
                if tr.label.sum() < 20 or te.label.sum() == 0:
                    continue
                m = lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=15, min_data_in_leaf=200,
                                   verbose=-1, seed=42), lgb.Dataset(tr[feats], tr.label), num_boost_round=150)
                aucs.append(roc_auc_score(te.label, m.predict(te[feats])))
            res[feats_tag] = round(float(np.mean(aucs)), 4)
    rep["early_warning_auc"] = res
    # — крупнейшие события по числу новостей: реакция расходов субъекта
    big = reg_m.assign(n=reg_m.get("disaster", 0)).sort_values("n", ascending=False)
    big = big[big.n >= cfg["news_eval"]["min_disaster_news"]]
    al_rk = al.merge(mo[["territory_id", "region_key"]], on="territory_id")
    ev_rows = []
    for r in big.itertuples():
        if r.period not in per:
            continue
        t, s_ = per.index(r.period), rk == r.region_key
        if t < 3 or t + 2 >= len(per) or not s_.any():
            continue
        sh = d[s_, t:t + 3].mean(axis=1) - d[s_, t - 3:t].mean(axis=1)
        row = {"region_key": r.region_key, "period": r.period, "disaster_news": int(r.n),
               "alarms_3m_before": int(((al_rk.region_key == r.region_key) & (al_rk.period >= per[t - 3]) & (al_rk.period < r.period)).sum()),
               "alarms_3m_after": int(((al_rk.region_key == r.region_key) & (al_rk.period >= r.period) & (al_rk.period <= per[t + 2])).sum())}
        for c in np.unique(cats):
            row[c] = round(float(np.median(sh[cats[s_] == c]) * 100), 1)
        ev_rows.append(row)
    big_tab = pd.DataFrame(ev_rows)
    big_tab.to_csv(OUT / "news_major_events.csv", index=False)
    rep["major_events"] = big_tab.to_dict("records")
    json.dump(rep, open(OUT / "news_report.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
