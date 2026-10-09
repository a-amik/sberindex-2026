"""Предсказание шоков: какие признаки дают знать о тревоге за месяц.

Цель — тревога детектора (z-оценка отклонения МО от фактора, порог из
detect_choice.json) в месяце t+1 по признакам месяца t. Базовый классификатор
и протокол — как у раннего предупреждения в 06_real.py: LightGBM, учится на
месяцах до t, проверяется на t+1, цели с января 2024 года. К базе по одной
добавляются группы признаков, затем все вместе:

* ews — признаки критического перехода (Scheffer и др., 2009; Dakos и др., 2012):
  рост дисперсии приростов отклонения, автокорреляция первого порядка, асимметрия,
  частота смены знака за последние 8 месяцев;
* spatial — заражение: средний |z| и тревоги соседей по дороге в t и t−1, доля
  тревог субъекта в t и t−1, сдвиг отклонения субъекта за месяц;
* calendar — повторяемость: тревога и |z| этого ряда и доля тревог субъекта
  в месяце t+1−12, то есть год назад в тот же месяц;
* weekly — опережающий ряд (Kaminsky и др., 1998): ускорение недельного годового
  прироста расходов России в категории ряда за месяц t+1 и по всем категориям;
  допущение о сроках публикации — то же, что у ноукаста;
* telegram — посты каналов властей и МЧС за месяц t о МО и субъекте по типам:
  паводок, бедствие, ЧС, атаки, выплаты, предприятия, сокращения; каналы есть
  у шести субъектов, у остальных нули;
* spread — разброс прогнозов четырёх моделей на шаг 1 из точки t: где модели
  расходятся, ряд ведёт себя неустойчиво.

Отдельная проверка на реальном событии: паводок весны 2024 года — ранг риска
рядов Оренбургской, Курганской и Тюменской областей среди всех рядов в прогнозах
на апрель и май.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import skew
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, detect  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

OUT = ROOT / "results/signal_value"
FIRST_TARGET, TOP_K = "2024-01", 100
FLOOD = ["Оренбургская область", "Курганская область", "Тюменская область"]
WEEKLY = {"Все категории": ["Все категории "], "Продовольствие": ["Продовольственные товары"],
          "Общественное питание": ["Общественное питание"], "Маркетплейсы": ["Маркетплейсы"],
          "Здоровье": ["Лекарства и медицинские товары", "Медицинские услуги"],
          "Транспорт": ["Локальный транспорт", "Такси, каршеринг, аренда автомобилей", "Топливо"]}
TG_TYPES = ["flood", "disaster", "emergency", "attack", "payments", "plant", "layoff"]
SPREAD_MODELS = ["panel_blend_ses_bytype", "lgbm", "chronos2_dev", "panel_blend_sesseas_bytype"]


def neighbours(panel, nb):
    spec = importlib.util.spec_from_file_location("d05", ROOT / "scripts/05_detect.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(m)
    return m.neighbours(panel, nb)


def nb_mean(x: np.ndarray, nb_rows: list) -> np.ndarray:
    return np.array([x[r].mean() if len(r) else 0.0 for r in nb_rows])


def main():
    P = ROOT / "data/processed"
    panel = backtest.load_panel(P, "full")
    mo = pd.read_parquet(P / "mo.parquet")
    idx = panel.index.merge(mo[["territory_id", "region", "mo_type"]], on="territory_id", how="left")
    g = panel_models.groups(panel.index, mo, "type")
    nb_rows = neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))
    ch = json.load(open(ROOT / "results/metrics/detect_choice.json"))
    th = ch["thresholds"]
    per = panel.periods
    d = detect.signal(panel.y, g)
    zs = detect.run_online(d, g, nb_rows, "zscore")
    bs = detect.run_online(d, g, nb_rows, "bocpd")
    a = detect.run_online(d, g, nb_rows, ch["lead"]) > th[ch["lead"]]   # метка — тревога ведущего детектора
    region = idx.region.to_numpy()
    cats = panel.index.category.astype(str).to_numpy()
    urban = idx.mo_type.isin(panel_models.URBAN).to_numpy()
    tid = panel.index.territory_id.to_numpy()

    # недельный ряд: ускорение годового прироста месяца m против трёх предыдущих
    nat = pd.read_parquet(P / "national.parquet").set_index("period")
    wk = pd.DataFrame({c: np.log1p(nat[[f"weekly_yoy:{x}" for x in v]].mean(axis=1) / 100) for c, v in WEEKLY.items()})
    wacc = wk - wk.shift(1).rolling(3).mean()

    # телеграм: посты месяца t о МО (в пределах своего субъекта) и о субъекте
    tg = pd.read_parquet(P / "telegram_annotated.parquet")
    tg["period"] = tg.date.str[:7]
    tg_mo, tg_reg = {}, {}
    for r in tg.itertuples():
        for t in r.types:
            if t not in TG_TYPES:
                continue
            for m in r.mos:
                tg_mo[(m, r.period, t)] = tg_mo.get((m, r.period, t), 0) + 1
            if r.region != "*":
                tg_reg[(r.region, r.period, t)] = tg_reg.get((r.region, r.period, t), 0) + 1

    # разброс прогнозов на шаг 1 из точки t
    fs = [pd.read_parquet(ROOT / f"results/forecasts/{m}.parquet", columns=["row", "origin", "step", "yhat"])
          .query("step == 1").set_index(["row", "origin"]).yhat.rename(m) for m in SPREAD_MODELS]
    spread = np.log(pd.concat(fs, axis=1).clip(lower=1e-9)).std(axis=1)

    rows = []
    for t in range(max(detect.MIN_HIST + 1, 8), len(per) - 1):
        x = d[:, : t + 1]
        dx = np.diff(x, axis=1)
        reg_al = pd.Series(a[:, t]).groupby(region).transform("mean").to_numpy()
        reg_al1 = pd.Series(a[:, t - 1]).groupby(region).transform("mean").to_numpy()
        reg_dd = pd.Series(d[:, t] - d[:, t - 1]).groupby(region).transform("median").to_numpy()
        last8 = dx[:, -8:]
        c8 = last8 - last8.mean(axis=1, keepdims=True)
        ac1 = (c8[:, 1:] * c8[:, :-1]).mean(axis=1) / np.where(c8.var(axis=1) > 0, c8.var(axis=1), np.nan)
        ly = t + 1 - 12
        nxt = per[t + 1]
        f = {
            "t": t, "row": np.arange(len(d)), "label": a[:, t + 1].astype(int),
            # база — как в 06_real.py
            "z_now": zs[:, t], "z_max3": zs[:, t - 2:t + 1].max(axis=1), "b_now": bs[:, t],
            "alarm_now": a[:, t].astype(int), "nb_alarm": nb_mean(a[:, t].astype(float), nb_rows), "region_alarm": reg_al,
            "vol6": np.diff(x[:, -7:], axis=1).std(axis=1), "trend3": x[:, -1] - x[:, -4],
            "category": pd.Categorical(cats).codes, "district": (~urban).astype(int), "target_month": int(nxt[5:7]),
            # ews
            "ews_var_ratio": dx[:, -4:].var(axis=1) / np.maximum(dx[:, -8:-4].var(axis=1), 1e-9),
            "ews_ac1": ac1, "ews_skew": skew(last8, axis=1),
            "ews_flicker": (np.diff(np.sign(last8), axis=1) != 0).sum(axis=1),
            # spatial
            "sp_nb_absz": nb_mean(np.abs(zs[:, t]), nb_rows), "sp_nb_absz1": nb_mean(np.abs(zs[:, t - 1]), nb_rows),
            "sp_nb_alarm1": nb_mean(a[:, t - 1].astype(float), nb_rows), "sp_reg_alarm1": reg_al1, "sp_reg_dd": reg_dd,
            # calendar
            "cal_alarm_ly": a[:, ly].astype(int) if ly >= 0 else np.zeros(len(d)),
            "cal_absz_ly": np.abs(zs[:, ly]) if ly >= 0 else np.zeros(len(d)),
            "cal_reg_alarm_ly": (pd.Series(a[:, ly]).groupby(region).transform("mean").to_numpy() if ly >= 0 else np.zeros(len(d))),
            # weekly
            "wk_acc_cat": np.array([wacc.at[nxt, c] if nxt in wacc.index else np.nan for c in cats]),
            "wk_acc_all": np.full(len(d), wacc.at[nxt, "Все категории"] if nxt in wacc.index else np.nan),
            # spread
            "spread": spread.reindex(pd.MultiIndex.from_arrays([np.arange(len(d)), np.full(len(d), per[t])])).to_numpy(),
        }
        f["wk_abs_cat"] = np.abs(f["wk_acc_cat"])
        for ty in TG_TYPES:
            f[f"tg_mo_{ty}"] = np.array([tg_mo.get((m, per[t], ty), 0) for m in tid])
            f[f"tg_reg_{ty}"] = np.array([tg_reg.get((r, per[t], ty), 0) for r in region])
        rows.append(pd.DataFrame(f))
    ds = pd.concat(rows, ignore_index=True)
    base = ["z_now", "z_max3", "b_now", "alarm_now", "nb_alarm", "region_alarm", "vol6", "trend3", "category", "district", "target_month"]
    groups = {
        "ews": [c for c in ds if c.startswith("ews_")], "spatial": [c for c in ds if c.startswith("sp_")],
        "calendar": [c for c in ds if c.startswith("cal_")], "weekly": [c for c in ds if c.startswith("wk_")],
        "telegram": [c for c in ds if c.startswith("tg_")], "spread": ["spread"],
    }
    variants = {"база": base, **{f"база + {k}": base + v for k, v in groups.items()},
                "база + всё": base + [c for v in groups.values() for c in v]}

    flood = np.isin(region, FLOOD)
    res, flood_rank = [], []
    for name, feats in variants.items():
        for t in sorted(ds.t.unique()):
            if per[t + 1] < FIRST_TARGET:
                continue
            tr, te = ds[ds.t < t], ds[ds.t == t]
            if tr.label.sum() < 20 or te.label.sum() == 0:
                continue
            m = lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=15, min_data_in_leaf=200,
                               feature_fraction=0.8, verbose=-1, seed=42), lgb.Dataset(tr[feats], tr.label), num_boost_round=150)
            p = m.predict(te[feats])
            y = te.label.to_numpy()
            top = np.argsort(-p)[:TOP_K]
            res.append({"variant": name, "target": per[t + 1], "positives": int(y.sum()),
                        "auc": roc_auc_score(y, p), "ap": average_precision_score(y, p),
                        "prec_top100": float(y[top].mean()), "rule_auc": roc_auc_score(y, te.z_max3)})
            if per[t + 1] in ("2024-04", "2024-05"):
                rank = pd.Series(p).rank(pct=True).to_numpy()
                flood_rank.append({"variant": name, "target": per[t + 1], "flood_rank_mean": float(rank[flood].mean()),
                                   "flood_alarm_rank_mean": float(rank[flood & (y == 1)].mean()) if (flood & (y == 1)).any() else np.nan,
                                   "flood_in_top5pct": float((rank[flood] > 0.95).mean())})
        print(name, "готово", flush=True)
    res = pd.DataFrame(res)
    res.to_csv(OUT / "shock_prediction_by_month.csv", index=False)
    summ = res.groupby("variant").agg(auc=("auc", "mean"), ap=("ap", "mean"), prec_top100=("prec_top100", "mean"),
                                      rule_auc=("rule_auc", "mean"), months=("auc", "size"))
    b = res[res.variant == "база"].set_index("target")
    summ["auc_vs_base"] = [float((res[res.variant == v].set_index("target").auc - b.auc).mean()) for v in summ.index]
    summ["months_better"] = [int(((res[res.variant == v].set_index("target").auc - b.auc) > 0).sum()) for v in summ.index]
    summ["base_rate_pct"] = float(res.positives.sum() / (len(d) * res.target.nunique()) * 100 / len(variants))
    summ.to_csv(OUT / "shock_prediction.csv")
    fr = pd.DataFrame(flood_rank)
    fr.to_csv(OUT / "shock_prediction_flood.csv", index=False)
    pd.set_option("display.width", 220)
    print(summ.sort_values("auc", ascending=False).round(4).to_string())
    print(fr.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
