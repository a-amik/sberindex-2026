"""Шаг 20. Гипотеза: сдача жилья меняет расходы территории.

Данные — каталог наш.дом.рф (data/external/domrf: сданные, строящиеся, проблемные
объекты с застройщиком, датой сдачи, площадью и координатами). Объект привязывается
к МО по контуру. «Доза» — сданная жилая площадь, кв. м на жителя МО.

Проверка на прошлом (2023—2024):
  1) Регрессия: прирост отклонения МО от своей группы (категория × город/район)
     за год против сданной за предыдущий год площади на жителя; поправки — размер
     МО и доля горожан, всё внутри субъекта (фиксированные эффекты региона).
  2) Событие: МО, где за квартал сдали больше 0,5 кв. м на жителя, — средний ход
     отклонения за 6 месяцев до и 6 после квартала сдачи против остальных МО.

Если эффект есть, по строящимся объектам считается ожидаемая прибавка расходов
МО на 2025—2027 годы, с поправкой на риск: проблемный объект, сдвиг сроков,
застройщик с проблемными объектами.

Итог — results/metrics/housing.json и web/public/data/housing.json (слой стройки).
    uv run --with geopandas --with pyogrio --with pandas --with pyarrow --with statsmodels python scripts/20_housing.py
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
D = ROOT / "data/external/domrf"


def load(name):
    rows = json.loads((D / f"{name}.json").read_text())
    out = []
    for o in rows:
        dev = o.get("developer") or {}
        out.append({
            "id": o.get("objId") or o.get("problemId") or o.get("hobjId"), "lat": o.get("latitude"), "lon": o.get("longitude"),
            "ready": o.get("objReady100PercDt"), "publ": o.get("objPublDt"), "area": o.get("objSquareLiving") or 0.0,
            "flats": o.get("objElemLivingCnt") or 0, "type": o.get("buildType"), "problem": o.get("problemFlag"),
            "reason": o.get("problemReason"), "escrow": o.get("objGuarantyEscrowFlg"), "dev": dev.get("shortName"),
            "devInn": dev.get("devInn"), "group": dev.get("groupName"), "name": o.get("objCommercNm"), "addr": o.get("shortAddr"),
            "floors": o.get("objFloorMax"), "status": name,
        })
    return pd.DataFrame(out)


def main():
    from sbi import backtest, detect
    from sbi.models import panel as panel_models
    P = ROOT / "data/processed"
    mo = pd.read_parquet(P / "mo.parquet")
    poly = gpd.read_file(ROOT / "data/raw/hackathon/t_dict_municipal_districts_poly.gpkg").to_crs(4326)
    poly = poly[(poly.year_to == 9999)][["territory_id", "geometry"]]
    poly["territory_id"] = poly.territory_id.astype(int)

    objs = pd.concat([load(n) for n in ("done", "building", "problem") if (D / f"{n}.json").exists()], ignore_index=True)
    objs = objs.dropna(subset=["lat", "lon"])
    objs = objs[objs.type.fillna("Жилое").str.startswith("Жил") | (objs.flats > 0)]
    g = gpd.GeoDataFrame(objs, geometry=gpd.points_from_xy(objs.lon, objs.lat), crs=4326)
    g = gpd.sjoin(g, poly, predicate="within", how="inner").drop(columns="index_right")
    g["ready"] = pd.to_datetime(g.ready, errors="coerce")
    print("Объектов к МО:", len(g), g.status.value_counts().to_dict())

    pop = mo.set_index("territory_id")["pop"]
    done = g[g.status == "done"].copy()
    done["q"] = done.ready.dt.to_period("Q").astype(str)
    done["y"] = done.ready.dt.year

    # ── отклонение МО от своей группы по месяцам — тот же сигнал, что у детекторов
    bp = backtest.load_panel(P, "full")
    groups = panel_models.groups(bp.index, mo, "type")
    d = detect.signal(bp.y, groups)
    idx = bp.index.assign(row=np.arange(len(bp.index)))
    res = {"objects": {k: int(v) for k, v in g.status.value_counts().items()}}
    rows = []
    for cat in ("Все категории", "Продовольствие", "Общественное питание", "Маркетплейсы", "Здоровье", "Транспорт"):
        sel = idx[idx.category.astype(str) == cat]
        dd = d[sel.row.to_numpy()]
        tids = sel.territory_id.astype(int).to_numpy()
        # прирост отклонения 2024 к 2023 году против сданного в 2023 году
        delta = dd[:, 12:].mean(axis=1) - dd[:, :12].mean(axis=1)
        a23 = done[done.y == 2023].groupby("territory_id").area.sum()
        a22 = done[done.y == 2022].groupby("territory_id").area.sum()
        df = pd.DataFrame({"tid": tids, "delta": delta * 100})
        df = df.merge(mo[["territory_id", "region_key", "pop", "urban_share"]], left_on="tid", right_on="territory_id")
        df["dose23"] = df.tid.map(a23).fillna(0) / df["pop"]
        df["dose22"] = df.tid.map(a22).fillna(0) / df["pop"]
        df["lpop"] = np.log(df["pop"].clip(lower=500))
        df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["delta", "dose23", "lpop", "urban_share"])
        df = df[df.dose23 < df.dose23.quantile(0.995)]          # выбросы: ошибки площади в каталоге
        m = smf.ols("delta ~ dose23 + dose22 + lpop + urban_share + C(region_key)", data=df).fit(cov_type="cluster", cov_kwds={"groups": df.region_key.astype("category").cat.codes})
        bins = pd.cut(df.dose23, [-0.001, 0, 0.2, 0.5, 1, 100], labels=["нет", "до 0,2", "0,2—0,5", "0,5—1", "больше 1"])
        dose = df.groupby(bins, observed=True).delta.agg(["mean", "count"]).reset_index()
        rows.append({"cat": cat, "coef": float(m.params.dose23), "se": float(m.bse.dose23), "p": float(m.pvalues.dose23),
                     "coef_lag": float(m.params.dose22), "se_lag": float(m.bse.dose22), "n": int(m.nobs),
                     "dose": [[str(r[0]), round(float(r[1]), 2), int(r[2])] for r in dose.itertuples(index=False)]})
        print(f"{cat}: {m.params.dose23:+.2f} ± {m.bse.dose23:.2f} п. п. на 1 кв. м/жителя (p={m.pvalues.dose23:.3f}), n={int(m.nobs)}")
    res["regression"] = rows

    # ── событие: квартал крупной сдачи (> 0,5 кв. м на жителя), ход отклонения ±6 мес.
    sel = idx[idx.category.astype(str) == "Все категории"]
    dd = d[sel.row.to_numpy()] * 100
    tids = sel.territory_id.astype(int).to_numpy()
    qd = done[(done.y >= 2023) & (done.y <= 2024)].groupby(["territory_id", "q"]).area.sum().reset_index()
    qd["dose"] = qd.area / qd.territory_id.map(pop)
    big = qd[qd.dose > 0.5]
    periods = bp.periods
    ev = []
    for r in big.itertuples():
        i = np.where(tids == r.territory_id)[0]
        if not len(i):
            continue
        y, qn = int(r.q[:4]), int(r.q[-1])
        t0 = periods.index(f"{y}-{(qn - 1) * 3 + 1:02d}")
        path = [dd[i[0], t0 + k] - dd[i[0], t0 - 1] if 0 <= t0 + k < len(periods) and t0 >= 1 else np.nan for k in range(-6, 7)]
        ev.append(path)
    ev = np.array(ev, float)
    res["event"] = {"n": int(len(ev)), "k": list(range(-6, 7)), "mean": [None if np.isnan(x) else round(float(x), 2) for x in np.nanmean(ev, axis=0)] if len(ev) else [],
                    "se": [None if np.isnan(x) else round(float(x), 2) for x in (np.nanstd(ev, axis=0) / np.sqrt(np.maximum(1, np.sum(~np.isnan(ev), axis=0))))] if len(ev) else []}
    print("Событий крупной сдачи:", len(ev))

    # ── стройка: слой с риском недостроя
    bld = g[g.status.isin(["building", "problem"])].copy()
    prob_dev = set(g[g.status == "problem"].devInn.dropna())
    today = pd.Timestamp("2026-10-01")
    bld["overdue"] = bld.ready < today
    bld["risk"] = np.select([bld.status == "problem", bld.devInn.isin(prob_dev), bld.overdue], ["проблемный", "застройщик с проблемными", "срок сдачи прошёл"], "обычный")
    coef = next(r for r in rows if r["cat"] == "Все категории")
    txt = lambda x: x if isinstance(x, str) and x else None    # пустые поля каталога приходят NaN, а NaN не JSON
    layer = [[round(r.lon, 4), round(r.lat, 4), txt(r.name) or txt(r.addr), int(r.territory_id), txt(r.dev), txt(r.group), None if pd.isna(r.ready) else r.ready.strftime("%Y-%m"),
              txt(r.publ), round(float(r.area)), int(r.flats), r.risk, txt(r.reason), int(r.escrow or 0)] for r in bld.itertuples()]
    # ожидаемая прибавка МО: площадь к сдаче по годам на жителя × коэффициент, только если он значим
    up = bld[bld.risk != "проблемный"].assign(y=bld.ready.dt.year).groupby(["territory_id", "y"]).area.sum().reset_index()
    up["dose"] = up.area / up.territory_id.map(pop)
    up = up.replace([np.inf, -np.inf], np.nan).dropna(subset=["dose"])     # МО без населения в справочнике
    res["uplift_used"] = bool(coef["p"] < 0.05)
    res["uplift"] = {int(t): {int(y): round(float(v * coef["coef"]), 3) for y, v in zip(gg.y, gg.dose) if 2025 <= y <= 2027} for t, gg in up.groupby("territory_id")} if coef["p"] < 0.05 else {}
    (ROOT / "results/metrics/housing.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    cols = ["lon", "lat", "name", "mo", "dev", "group", "ready", "publ", "area", "flats", "risk", "reason", "escrow"]
    (ROOT / "web/public/data/housing.json").write_text(json.dumps({"cols": cols, "rows": layer, "test": {k: res[k] for k in ("regression", "event", "uplift_used")}, "uplift": res["uplift"]}, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    print("Стройка к МО:", len(layer), bld.risk.value_counts().to_dict())


if __name__ == "__main__":
    main()
