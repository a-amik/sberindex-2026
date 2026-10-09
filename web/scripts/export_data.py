"""Данные экрана из результатов репозитория: web/public/data.

Запуск из корня: .venv/bin/python web/scripts/export_data.py

meta.json      модели, метрики прогноза и детекторов, раннее предупреждение
mo.json        справочник МО и сводка по категориям для карты
alarms.json    тревоги ведущего детектора с отметкой о новостях
sample.json    выборка полных рядов для массового прогона на стенде
reg/<n>.json   субъект целиком: ряды, ряд субъекта, прогнозы по точкам, тревоги, новости
"""
import json
import math
from pathlib import Path

import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "web/public/data"
P = ROOT / "data/processed"
M = ROOT / "results/metrics"
F = ROOT / "results/forecasts"

CATS = ["Все категории", "Продовольствие", "Здоровье", "Общественное питание", "Транспорт", "Маркетплейсы"]
# Шесть моделей на графиках; полный список — в таблице метрик.
# Ряд РФ для сверки прогноза 2025 года — недельный индекс СберИндекса: он ближе
# к категориям МО, а в месячном ряду по общепиту в январе 2025 года ступенька методики.
CHECK = {"Все категории": "Все категории ", "Продовольствие": "Продовольственные товары", "Здоровье": "Медицинские услуги",
         "Общественное питание": "Общественное питание", "Транспорт": "Локальный транспорт", "Маркетплейсы": "Маркетплейсы"}
SHOWN = ["prophet_default", "snaive_growth", "panel_blend_sesseas_bytype", "lgbm", "chronos2_dev", "ensemble", "ensemble_strict"]
# Сдаваемая и рабочая модель сайта: строгий прогноз (scripts/37_strict.py) — ансамбль-медиана
# четырёх моделей с поправкой роста фактора на шагах 4—12 и конформными интервалами.
# Все числа экрана — рост 2025, календарь месяцев, ошибка по горизонтам, сверка с рядом РФ —
# снимаются с него; остальные модели на графиках — исследовательское сравнение.
MAIN = "ensemble_strict"


def dump(name, obj):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return path.stat().st_size


def clean(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def records(df):
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def main():
    mo = pd.read_parquet(P / "mo.parquet")
    panel = pd.read_parquet(P / "panel.parquet")
    regions = pd.read_parquet(P / "regions.parquet")
    periods = sorted(panel.period.unique())
    pidx = {p: i for i, p in enumerate(periods)}
    cidx = {c: i for i, c in enumerate(CATS)}

    # Порядок рядов в прогнозах — как в backtest.load_panel: полные ряды, сводная по (МО, категория).
    full = panel[panel.full].pivot_table(index=["territory_id", "category"], columns="period", values="value", observed=True).dropna()
    rows = full.index.to_frame(index=False)
    rows["ci"] = rows.category.map(cidx)

    # ── Детекторы тем же кодом, что считал results: онлайн-счёт по месяцам
    # и всё, что нужно экрану, чтобы пересчитать его на ряде со вписанным шоком.
    from importlib import import_module
    from sbi import backtest, detect
    from sbi.models import panel as panel_models
    bp = backtest.load_panel(P, "full")
    groups = panel_models.groups(bp.index, mo, "type")
    nb_rows = import_module("05_detect").neighbours(bp, pd.read_parquet(P / "neighbours.parquet"))
    dsig = detect.signal(bp.y, groups)
    DETS = ["zscore", "panel", "cusum", "bocpd", "forecast", "chronos"]
    det_scores = {m: detect.run_online(dsig, groups, nb_rows, m) for m in DETS}
    T = dsig.shape[1]
    gnames = sorted(set(groups))
    gid = {g: i for i, g in enumerate(gnames)}
    ly = np.log(bp.y)
    gstat = []
    jump = np.full_like(dsig, np.nan)
    for t in range(3, T):
        jump[:, t] = dsig[:, t] - dsig[:, t - 3:t].mean(axis=1)
    nbj = np.zeros_like(dsig)
    for t in range(3, T):
        nbj[:, t] = [np.median(jump[r, t]) if r else 0.0 for r in nb_rows]
    rel = jump - nbj
    scale = np.stack([detect.group_scale(dsig, groups, t) for t in range(T)], axis=1)
    for g in gnames:
        sel = groups == g
        rm = [float(np.median(rel[sel, t])) if t >= 3 else 0.0 for t in range(T)]
        rd = [float(max(detect._mad(rel[sel, t]), 1e-3)) if t >= 3 else 1.0 for t in range(T)]
        gstat.append({"name": g, "med": [round(float(v), 6) for v in np.median(ly[sel], axis=0)],
                      "scale": [round(float(v), 6) for v in scale[sel][0]], "relmed": [round(v, 6) for v in rm], "relmad": [round(v, 6) for v in rd]})
    det_of = {}
    for i, (tid, c) in enumerate(zip(bp.index.territory_id, bp.index.category.astype(str))):
        det_of[(int(tid), CATS.index(c))] = {"g": gid[groups[i]], "nb": [round(float(v), 5) for v in nbj[i]],
                                             "s": {m: [round(float(v), 3) for v in det_scores[m][i]] for m in DETS}}

    wide = panel.pivot_table(index=["territory_id", "category"], columns="period", values="value", observed=True)

    # ── Прогнозы по точкам: (row, origin, step) → yhat
    fc = {}
    for m in SHOWN:
        d = pd.read_parquet(F / f"{m}.parquet", columns=["row", "origin", "step", "yhat"] + (["q05", "q95"] if m.startswith("chronos") else []))
        fc[m] = d
    origins = sorted(fc[MAIN].origin.unique())

    def per_series(d, col):
        d = d.sort_values(["row", "origin", "step"])
        out = {}
        for (row, origin), g in d.groupby(["row", "origin"], sort=False):
            out.setdefault(row, {})[origin] = [round(float(v)) for v in g[col]]
        return out

    series_fc = {m: per_series(fc[m], "yhat") for m in SHOWN}

    # ── Прогноз на 2025 год от декабря 2024 (scripts/17_forward.py)
    FW = ROOT / "results/forecasts_forward"
    fwd = {}
    for m in SHOWN:
        if (FW / f"{m}.parquet").exists():
            d = pd.read_parquet(FW / f"{m}.parquet")
            steps = d.groupby("row").size().iloc[0]
            fwd[m] = d.yhat.to_numpy().reshape(-1, steps)
            if "q05" in d:
                fwd[m + ":q05"], fwd[m + ":q95"] = d.q05.to_numpy().reshape(-1, steps), d.q95.to_numpy().reshape(-1, steps)
    fwd_targets = sorted(pd.read_parquet(FW / f"{MAIN}.parquet").target.unique()) if fwd else []
    assert MAIN in fwd, f"нет прогноза вперёд сдаваемой модели: {FW / (MAIN + '.parquet')} (make ahead)"
    # Интервал строгого прогноза вперёд по категории и шагу: полуширина 90 % в долях к точке,
    # и фактическое покрытие 90 % на бэктесте по шагам — экрану, чтобы интервал и средняя
    # ошибка не смешивались.
    fs = pd.read_parquet(FW / f"{MAIN}.parquet")
    fs["c"] = rows.category.to_numpy()[fs.row.to_numpy()]
    fs["step"] = fs.groupby("row").cumcount() + 1
    iv = {c: [round(float(v), 4) for v in (g.hi90 / g.yhat - 1).groupby(g.step).median()] for c, g in [("Все", fs)] + list(fs.groupby("c"))}
    sb = pd.read_parquet(F / f"{MAIN}.parquet", columns=["origin", "step", "y", "lo90", "hi90"])
    sb = sb[sb.origin >= "2024-06"]
    cov90 = [round(float(((g.y >= g.lo90) & (g.y <= g.hi90)).mean()), 3) for h, g in sb.groupby("step") if h <= 6]
    q05 = per_series(fc["chronos2_dev"], "q05")
    q95 = per_series(fc["chronos2_dev"], "q95")

    # ── Выигрыш над Prophet по ряду на 3 мес.: 1 − MAE ансамбля / MAE Prophet
    def mae3(m):
        d = pd.read_parquet(F / f"{m}.parquet", columns=["row", "step", "y", "yhat"])
        d = d[d.step <= 3]
        return (d.yhat - d.y).abs().groupby(d.row).mean()
    gain = 1 - mae3(MAIN) / mae3("prophet_default")

    # ── Тревоги
    al = pd.read_csv(M / "detect_real_alarms_news.csv")
    al["ci"] = al.category.map(cidx)
    al["t"] = al.period.map(pidx)
    det_row = {(int(t), CATS.index(c)): i for i, (t, c) in enumerate(zip(bp.index.territory_id, bp.index.category.astype(str)))}

    def strength(tid, ci, t):
        """Сила тревоги: насколько месяц отошёл от обычного соотношения ряда с его группой, %."""
        i = det_row.get((tid, ci))
        if i is None or t < 1:
            return None
        return round(float(np.exp(dsig[i, t] - dsig[i, :t].mean()) - 1), 3)
    alarms = [[int(r.territory_id), int(r.ci), int(r.t), round(float(r.score), 2), int(bool(r.mo_news)), int(bool(r.region_news)), strength(int(r.territory_id), int(r.ci), int(r.t))] for r in al.itertuples()]
    dump("alarms.json", alarms)

    # ── Справочник и сводка для карты
    reg_keys = sorted(mo.region_key.dropna().unique())
    rk = {k: i for i, k in enumerate(reg_keys)}
    last3 = al[al.t >= len(periods) - 3].groupby(["territory_id", "ci"]).score.apply(lambda s: s.abs().max())
    row_of = {(int(t), int(c)): i for i, (t, c) in enumerate(zip(rows.territory_id, rows.ci))}
    # Москва и Петербург: точки внутригородских МО — из cities.json (собирает cities_geo.py).
    msk = json.loads((OUT / "cities.json").read_text()) if (OUT / "cities.json").exists() else {}
    # Для бизнес-режима: рост 2025 к 2024, точность прогноза ряда, его собственная
    # волатильность, число тревог и годовой уровень расходов на жителя.
    ens_bt = pd.read_parquet(F / f"{MAIN}.parquet", columns=["row", "step", "y", "yhat"])
    ens_bt = ens_bt[ens_bt.step <= 3]
    wape3 = (ens_bt.yhat - ens_bt.y).abs().groupby(ens_bt.row).sum() / ens_bt.y.groupby(ens_bt.row).sum()
    vol = {k: float(np.std(np.diff(dsig[i])) * 100) for k, i in det_row.items()}
    n_al = al.groupby(["territory_id", "ci"]).size().to_dict()
    mo_rows = []
    for r in mo.itertuples():
        g = msk.get(str(int(r.territory_id)))
        lat = g["ly"] if g else (None if pd.isna(r.lat) else round(float(r.lat), 3))
        lon = g["lx"] if g else (None if pd.isna(r.lon) else round(float(r.lon), 3))
        summ = []
        for c in range(6):
            key = (int(r.territory_id), CATS[c])
            v = wide.loc[key].to_numpy(float) if key in wide.index else None
            yoy = float(v[-1] / v[-13] - 1) if v is not None and np.isfinite(v[-1]) and np.isfinite(v[-13]) and v[-13] else None
            rr = row_of.get((int(r.territory_id), c))
            g = float(gain.get(rr, np.nan)) if rr is not None else None
            a = float(last3.get((int(r.territory_id), c), 0.0))
            k2 = (int(r.territory_id), c)
            fc25 = float(fwd[MAIN][rr][:12].sum() / np.nansum(v[12:24]) - 1) if rr is not None and MAIN in fwd and v is not None else None
            w3 = float(wape3.get(rr, np.nan)) if rr is not None else None
            lvl = float(np.nansum(v[12:24])) if v is not None and np.isfinite(v[12:24]).all() else None
            summ.append([None if yoy is None else round(yoy, 4), None if g is None or not np.isfinite(g) else round(g, 3), round(a, 2),
                         None if fc25 is None else round(fc25, 4), None if w3 is None or not np.isfinite(w3) else round(w3, 4),
                         round(vol[k2], 2) if k2 in vol else None, int(n_al.get(k2, 0)), None if lvl is None else round(lvl)])
        mo_rows.append([int(r.territory_id), r.name_short or r.name, r.name, r.region, rk.get(r.region_key, -1), r.mo_type,
                        lat, lon,
                        int(r.pop) if pd.notna(r.pop) else 0, round(float(r.urban_share), 2) if pd.notna(r.urban_share) else None, summ])
    size = dump("mo.json", {"cols": ["id", "name", "full", "region", "rk", "type", "lat", "lon", "pop", "urban", "sum"], "rows": mo_rows})
    print("mo.json", size)

    # ── Субъекты: насколько расходы субъекта повторяют динамику страны (макрориск)
    # и сколько о нём было новостей о ЧС, бедствиях и пожарах (локальный риск).
    natl = pd.read_parquet(P / "national.parquet").set_index("period")
    # Годовой рост, а не помесячный: помесячный ход у всех почти одинаков из-за сезона.
    nat_yoy = natl["spend_yoy_nominal:Всего"].reindex(periods[12:]).to_numpy(float) / 100
    nr = pd.read_parquet(P / "news_region.parquet")
    nr = nr[nr.period.isin(periods)].groupby("region_key").sum(numeric_only=True)
    reg_out = []
    for key in reg_keys:
        rg = regions[(regions.region_key == key) & (regions.category == "Все категории")].sort_values("period")
        beta = r2 = None
        if len(rg) == len(periods):
            v = rg.value.to_numpy(float)
            x = v[12:] / v[:12] - 1
            b = np.polyfit(nat_yoy, x, 1)
            beta = float(b[0])
            r2 = float(np.corrcoef(nat_yoy, x)[0, 1] ** 2)
        nn = nr.loc[key] if key in nr.index else None
        risk_news = int(sum(nn.get(c, 0) for c in ("disaster", "emergency", "fire", "flood"))) if nn is not None else 0
        reg_out.append({"key": key, "beta": None if beta is None else round(beta, 3), "r2": None if r2 is None else round(r2, 3),
                        "riskNews": risk_news, "attackNews": int(nn.get("attack", 0)) if nn is not None else 0})
    dump("regions.json", reg_out)

    # ── Новости: размеченные события по МО и субъекту
    news = pd.read_parquet(P / "news_annotated.parquet", columns=["date", "title", "types", "regions", "mos", "url"])
    news = news[news.types.str.len() > 0]
    news = news[(news.mos.str.len() > 0) | (news.regions.str.len() > 0)]
    news["t"] = news.date.str[:7].map(pidx)
    news = news[news.t.notna()]

    # ── Субъекты
    total = 0
    for key in reg_keys:
        ids = mo[mo.region_key == key].territory_id.astype(int).tolist()
        ser, fcs, band, dets, fw = {}, {}, {}, {}, {}
        for tid in ids:
            for c in range(6):
                k = (tid, CATS[c])
                if k in wide.index:
                    v = wide.loc[k].to_numpy(float)
                    ser.setdefault(tid, {})[c] = [None if not np.isfinite(x) else round(float(x)) for x in v]
                if (tid, c) in det_of:
                    dets.setdefault(tid, {})[c] = det_of[(tid, c)]
                rr = row_of.get((tid, c))
                if rr is not None and fwd:
                    fw.setdefault(tid, {})[c] = {m: [None if not np.isfinite(v) else round(float(v)) for v in a[rr]] for m, a in fwd.items()}
                if rr is not None:
                    fcs.setdefault(tid, {})[c] = {m: series_fc[m].get(rr, {}) for m in SHOWN}
                    band.setdefault(tid, {})[c] = [q05.get(rr, {}), q95.get(rr, {})]
        rg = regions[regions.region_key == key]
        R = {cidx[c]: [round(float(x)) for x in g.sort_values("period").value] for c, g in rg.groupby("category", observed=True)}
        ra = [a for a in alarms if a[0] in set(ids)]
        nn = news[news.mos.apply(lambda xs: any(int(x) in ids for x in xs)) | news.regions.apply(lambda xs: key in list(xs))]
        nl = [[int(r.t), r.date, r.title, list(r.types), [int(x) for x in r.mos if int(x) in ids]] for r in nn.itertuples()]
        total += dump(f"reg/{rk[key]}.json", {"key": key, "series": ser, "region": R, "fc": fcs, "band": band, "alarms": ra, "news": nl, "det": dets, "fwd": fw})
    print("reg/*", total, len(reg_keys))

    # ── Выборка для массового прогона: полные ряды и ряд их субъекта
    rng = np.random.default_rng(7)
    pick = rng.choice(len(rows), 360, replace=False)
    smp = []
    for i in pick:
        tid, cat = int(rows.territory_id[i]), rows.category[i]
        key = mo.set_index("territory_id").region_key.get(tid)
        rg = regions[(regions.region_key == key) & (regions.category == cat)].sort_values("period")
        if len(rg) != len(periods):
            continue
        dd = det_of[(tid, cidx[cat])]
        smp.append([tid, cidx[cat], [round(float(x)) for x in full.iloc[i]], [round(float(x)) for x in rg.value], dd["g"], dd["nb"]])
    dump("sample.json", smp)

    # ── Метрики
    byh = pd.read_csv(M / "forecast_by_horizon.csv")
    byc = pd.read_csv(M / "forecast_by_category.csv")
    ens = pd.read_csv(M / "ensemble_by_horizon.csv")
    # Строгий прогноз в таблицах метрик — теми же функциями, что считал бэктест (sbi.metrics).
    from sbi import metrics as mt
    sp = pd.read_parquet(F / f"{MAIN}.parquet", columns=["row", "origin", "step", "y", "y_origin", "yhat"])
    hz = [1, 3, 6, 12]
    byh = pd.concat([byh[byh.model != MAIN], mt.table({MAIN: sp}, hz, periods[-1])], ignore_index=True)
    sp["category"] = rows.category.to_numpy()[sp.row.to_numpy()]
    bc = [{"model": MAIN, "H": H, "category": c, **mt.scores(mt.horizon_rows(g, H, periods[-1]))} for c, g in sp.groupby("category") for H in hz]
    byc = pd.concat([byc[byc.model != MAIN], pd.DataFrame(bc)], ignore_index=True)
    rep_rows = [{"model": MAIN, "H": H, "MAE_all": mt.horizon_rows(sp, H, periods[-1]).eval("abs(yhat-y)").mean(),
                 "MAE_report": (lambda d: d.eval("abs(yhat-y)").mean() if len(d) else None)(mt.horizon_rows(sp[sp.origin >= "2024-06"], H, periods[-1]))} for H in hz]
    ens = pd.concat([ens[ens.model != MAIN], pd.DataFrame(rep_rows)], ignore_index=True)
    det = pd.read_csv(M / "detect_benchmark.csv")
    # ── Сверка прогноза 2025 года с фактическим рядом РФ (вне выборки: МО за 2025 год ещё нет)
    nat = pd.read_parquet(P / "national.parquet").set_index("period")
    sens = json.loads((M / "sensitivity.json").read_text()) if (M / "sensitivity.json").exists() else {}
    pop = mo.set_index("territory_id")["pop"].reindex(rows.territory_id).fillna(0).to_numpy()
    check = []
    if "ensemble" in fwd:
        for c in CATS:
            sel = (rows.category == c).to_numpy()
            series = CHECK[c]
            for j, tg in enumerate(fwd_targets[:12]):
                prev = periods.index(f"{int(tg[:4]) - 1}{tg[4:]}")
                w = pop[sel]
                fc_v = float((fwd[MAIN][sel, j] * w).sum() / w.sum())
                base = float((full.to_numpy()[sel, prev] * w).sum() / w.sum())
                nv = nat.get(f"weekly_yoy:{series}", pd.Series(dtype=float)).get(tg)
                check.append({"cat": c, "target": tg, "fc_yoy": round(100 * (fc_v / base - 1), 2), "nat_yoy": None if nv is None or pd.isna(nv) else round(float(nv), 2), "series": series})
    # ── Календарь месяцев: факт 2023—2024 и прогноз ансамбля на 36 месяцев по каждому ряду
    if MAIN in fwd:
        ser60 = []
        for i, (tid, ci) in enumerate(zip(rows.territory_id, rows.ci)):
            ser60.append([int(tid), int(ci), [round(float(x)) for x in full.iloc[i]] + [round(float(x)) for x in fwd[MAIN][i]]])
        print("months.json", dump("months.json", ser60))
    # Ожидаемая ошибка на шаг h: на 1—12 — измерена на бэктесте ансамбля; дальше — продолжение
    # кривой a + b·√h, подобранной по измеренным шагам: прогноз по прогнозу проверить нечем.
    eb = pd.read_parquet(F / f"{MAIN}.parquet", columns=["row", "step", "y", "yhat"])
    eb["c"] = rows.category.to_numpy()[eb.row.to_numpy()]
    herr = {}
    for c, g in [("Все", eb)] + list(eb.groupby("c")):
        w = (g.yhat - g.y).abs().groupby(g.step).sum() / g.y.groupby(g.step).sum()
        hs = np.arange(1, 13)
        b, a = np.polyfit(np.sqrt(hs), w.reindex(hs).to_numpy(), 1)
        herr[c] = [round(float(w.get(h, a + b * np.sqrt(h))) if h <= 12 else float(a + b * np.sqrt(h)), 4) for h in range(1, 37)]
    rob = json.loads((M / "shock_robustness.json").read_text()) if (M / "shock_robustness.json").exists() else {}

    # ── Происхождение данных: внешние источники, собранные таблицы и результаты — с датой
    import datetime as dt
    day = lambda p: dt.date.fromtimestamp(p.stat().st_mtime).isoformat()
    man = json.loads((ROOT / "data/manifest.json").read_text())
    ext = {}
    for path, m in man.items():
        src = path.split("/")[2] if path.startswith(("data/external/", "data/raw/")) else "прочее"
        e = ext.setdefault(src, {"files": 0, "bytes": 0, "date": "", "url": m.get("url", "")})
        e["files"] += 1; e["bytes"] += m.get("bytes", 0); e["date"] = max(e["date"], m.get("downloaded", ""))
    built = [{"file": f"data/processed/{f}", "rows": int(len(pd.read_parquet(P / f, columns=[pd.read_parquet(P / f).columns[0]]))), "date": day(P / f)}
             for f in ("panel.parquet", "mo.parquet", "regions.parquet", "national.parquet", "features.parquet", "neighbours.parquet", "news_annotated.parquet")]
    res = [{"file": f"results/{f}", "date": day(ROOT / "results" / f), "by": by}
           for f, by in (("forecasts/ensemble_strict.parquet", "scripts/37_strict.py"), ("forecasts_forward/ensemble_strict.parquet", "scripts/37_strict.py --forward"),
                         ("forecasts/ensemble.parquet", "scripts/03_backtest.py, 04_ensemble.py"), ("forecasts_forward/ensemble.parquet", "scripts/17_forward.py"),
                         ("metrics/detect_benchmark.csv", "scripts/05_detect.py"), ("metrics/detect_real_alarms_news.csv", "scripts/07_news.py"),
                         ("metrics/sensitivity.json", "scripts/18_sensitivity.py"), ("metrics/shock_robustness.json", "scripts/19_shock_robustness.py"))
           if (ROOT / "results" / f).exists()]
    sources = {"external": [{"name": k, **v} for k, v in sorted(ext.items())], "built": built, "results": res, "exported": dt.date.today().isoformat()}
    # Манифест релиза: какая модель, из чего собрана, на чём выбрана, какие файлы — с хешами.
    import hashlib
    import yaml
    sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()[:16]
    cfg = yaml.safe_load((ROOT / "configs/default.yaml").read_text())["ensemble"]
    sel = pd.read_csv(M / "ensemble_selection.csv").iloc[0]
    release = {"model_id": MAIN, "members": sel.members.split("+"), "how": sel.how, "force_include": cfg.get("force_include") or [],
               "select_last_target": str(cfg["select_last_target"]), "report_from": str(cfg["report_from"]),
               "data_last": periods[-1], "forward_origin": periods[-1], "forward_targets": [fwd_targets[0], fwd_targets[-1]] if fwd_targets else [],
               "adjustments": ["рост фактора по недельному ряду РФ со смещением по истории, сила 1: в бэктесте шаги 4—12, вперёд — все шаги с четвёртого (уровень года переносится на следующие)"],
               "intervals": "конформные по лог-остаткам строгого бэктеста, категория × шаг, не убывают с шагом; дальше шага 10 (последний с тремя точками) — q(10)·√(h/10)",
               "adjustment_tested": "сдвиг роста проверен в бэктесте на шагах 4—6 (точки с историей ≥ 3 месяцев); на шагах 7—36 вперёд не проверен",
               "coverage90_by_step": cov90,
               "files": {p: sha(p) for p in ("results/forecasts/ensemble_strict.parquet", "results/forecasts_forward/ensemble_strict.parquet",
                                             "results/metrics/ensemble_selection.csv", "results/metrics/ensemble_strict.csv", "configs/default.yaml")}}

    meta = {
        "periods": periods, "cats": CATS, "origins": origins, "shown": SHOWN, "regions": reg_keys,
        "byH": records(byh[["model", "H", "MAE", "WAPE", "R2", "n"]]),
        "byCat": records(byc[byc.model.isin(SHOWN)][["model", "H", "category", "MAE", "WAPE", "R2"]]),
        "ensemble": records(ens),
        "detect": records(det),
        "detectChoice": json.loads((M / "detect_choice.json").read_text().replace("Infinity", "null")),
        "early": records(pd.read_csv(M / "early_warning.csv")),
        "byMonth": records(pd.read_csv(M / "detect_real_by_month.csv")),
        "major": records(pd.read_csv(M / "news_major_events.csv")),
        "cases": json.loads((M / "real_cases.json").read_text()),
        "groups": gstat,
        "fwdTargets": fwd_targets,
        "fwdModels": [m for m in SHOWN if m in fwd],
        "sensitivity": sens,
        "fwdCheck": check,
        "robustness": rob,
        "horizonErr": herr,
        "interval90": iv,
        "release": release,
        "sources": sources,
    }
    print("meta.json", dump("meta.json", meta))


if __name__ == "__main__":
    main()
