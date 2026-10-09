"""Общая региональная поправка к готовому муниципальному прогнозу."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def month(period: str, delta: int) -> str:
    return str(pd.Period(period, "M") + delta)


def prepare_regional(cpi, wages):
    def unique_region(frame):
        d = frame[~frame.region.str.contains("федеральный округ", case=False, regex=False)].copy()
        separate = d.region_key.isin(["архангельская", "тюменская"])
        exclusion = d.region.str.contains("кроме|без авт", case=False, regex=True)
        d = d[~separate | exclusion]
        if d.duplicated(["region_key", "period"]).any():
            raise ValueError("Неоднозначная география регионального источника")
        return d
    c = unique_region(cpi[cpi.kind == "region"])
    w = unique_region(wages)
    return c[["region_key", "period", "cpi_total", "cpi_food", "cpi_nonfood", "cpi_services"]].merge(
        w[["region_key", "period", "wage"]], on=["region_key", "period"], how="outer", validate="one_to_one")


class RegionalContext:
    def __init__(self, panel, mo, base, regional, weather, national, news, settings):
        self.panel, self.settings = panel, settings
        mapping = panel.index.merge(mo[["territory_id", "region_key"]], on="territory_id",
                                    how="left", validate="many_to_one")
        if mapping.region_key.isna().any():
            raise ValueError("У ряда нет субъекта")
        self.cells = (mapping[["region_key", "category"]].drop_duplicates()
                      .sort_values(["region_key", "category"]).reset_index(drop=True))
        self.cells["category"] = self.cells.category.astype(str)
        keys = list(zip(mapping.region_key, mapping.category.astype(str)))
        lookup = {tuple(r): i for i, r in enumerate(self.cells.itertuples(index=False, name=None))}
        self.cell_of_row = np.array([lookup[k] for k in keys])
        self.rows = [np.flatnonzero(self.cell_of_row == i) for i in range(len(self.cells))]
        self.regions = sorted(self.cells.region_key.unique())
        self.regional = regional.set_index(["region_key", "period"]).sort_index()
        self.national = national.set_index("period").sort_index()
        self.news = news.set_index(["region_key", "period"]).sort_index()
        self.news_types = sorted(set(news.columns) - {"region_key", "period"})
        weather = weather.merge(mo[["territory_id", "region_key"]], on="territory_id",
                                how="left", validate="many_to_one")
        self.weather = (weather.groupby(["region_key", "period"])[["T2M", "PRECTOTCORR"]]
                        .mean().sort_index())
        self.category_codes = {c: i for i, c in enumerate(sorted(self.cells.category.unique()))}
        self.base = {}
        for origin, frame in base.groupby("origin", sort=True):
            t = panel.pos(origin)
            pred = frame.pivot(index="row", columns="step", values="yhat").reindex(
                index=range(len(panel.y)))
            if pred.isna().any().any() or not (pred.to_numpy() > 0).all():
                raise ValueError("Неполный или неположительный базовый прогноз")
            expected_steps = list(range(1, min(12, len(panel.periods) - 1 - t) + 1))
            if list(pred.columns) != expected_steps:
                raise ValueError("Неполный набор шагов базового прогноза")
            for h, g in frame.groupby("step"):
                g = g.sort_values("row")
                if not np.array_equal(g.row, np.arange(len(panel.y))):
                    raise ValueError("Индексы базового прогноза не совпали")
                if not np.allclose(g.y, panel.y[:, t + h]) or not np.allclose(g.y_origin, panel.y[:, t]):
                    raise ValueError("Базовый прогноз относится к другой панели")
            self.base[t] = pred.to_numpy()
        self.feature_cache = {}

    def aggregate(self, values):
        return np.array([np.median(values[r], axis=0) for r in self.rows])

    def _values(self, source, column, period, zero=False):
        index = pd.MultiIndex.from_arrays([self.cells.region_key, [period] * len(self.cells)])
        if column not in source:
            return np.zeros(len(self.cells)) if zero else np.full(len(self.cells), np.nan)
        v = source[column].reindex(index).to_numpy(float)
        return np.nan_to_num(v) if zero else v

    def _relative(self, values):
        out = values.copy()
        for cat in self.category_codes:
            ix = self.cells.category.to_numpy() == cat
            if np.isfinite(values[ix]).any():
                out[ix] -= np.nanmedian(values[ix])
        return out

    def _climate(self, variable, upto, target_month):
        w = self.weather.reset_index()
        # Норма 2018–2022 предшествует каждой точке эксперимента.
        w = w[(w.period <= min(upto, "2022-12")) & (w.period.str[5:7] == target_month)]
        return w.groupby("region_key")[variable].mean().reindex(self.cells.region_key).to_numpy()

    def features(self, t, h):
        if (t, h) in self.feature_cache:
            return self.feature_cache[t, h]
        p, y = self.panel.periods, self.panel.y[:, :t + 1]
        origin, target = p[t], month(p[t], h)
        lg = np.log(y)
        regional_level = self.aggregate(lg)
        cat_level = np.empty_like(regional_level)
        for cat in self.category_codes:
            rows = self.panel.index.category.astype(str).to_numpy() == cat
            cat_level[self.cells.category.to_numpy() == cat] = np.median(lg[rows], axis=0)
        dev = regional_level - cat_level
        target_last_year = t + h - 12
        if target_last_year < 0 or target_last_year > t:
            raise ValueError("Прошлогодний месяц вне истории")
        f = pd.DataFrame(index=range(len(self.cells)))
        f["ctl_h"] = h / 12
        f["ctl_target_sin"] = np.sin(2 * np.pi * int(target[5:7]) / 12)
        f["ctl_target_cos"] = np.cos(2 * np.pi * int(target[5:7]) / 12)
        f["ctl_dev"] = dev[:, -1]
        f["ctl_dev_g3"] = dev[:, -1] - dev[:, -4]
        f["ctl_dev_std6"] = dev[:, -6:].std(axis=1)
        f["ctl_dev_season"] = dev[:, target_last_year] - dev[:, -12:].mean(axis=1)
        f["ctl_base_growth"] = self.aggregate(np.log(self.base[t][:, h - 1])) - regional_level[:, -1]
        errors = []
        for j in range(max(11, t - 3), t):
            errors.append(self.aggregate(np.log(y[:, j + 1]) - np.log(self.base[j][:, 0])))
        f["ctl_last_error"] = errors[-1] if errors else np.nan
        f["ctl_error3"] = np.mean(errors, axis=0) if errors else np.nan

        lag = self.settings["release_lags"]
        cp, wp = month(origin, -lag["cpi"]), month(origin, -lag["wage"])
        cpi_groups = ["cpi_total", "cpi_food", "cpi_nonfood", "cpi_services"]
        for col in cpi_groups:
            f[f"macro_{col}_m"] = self._values(self.regional, col, cp) - 100
            for window in (3, 12):
                a = np.stack([self._values(self.regional, col, month(cp, -j)) for j in range(window)])
                growth = np.log(a / 100).sum(axis=0)
                f[f"macro_{col}_{window}"] = growth
                f[f"macro_{col}_{window}_relative"] = self._relative(growth)
        wage = self._values(self.regional, "wage", wp)
        growth = np.log(wage / self._values(self.regional, "wage", month(wp, -12)))
        old = np.log(self._values(self.regional, "wage", month(wp, -3)) /
                     self._values(self.regional, "wage", month(wp, -15)))
        f["macro_wage_yoy"] = growth
        f["macro_wage_yoy_relative"] = self._relative(growth)
        f["macro_wage_acceleration"] = growth - old
        f["macro_real_wage_yoy"] = growth - f.macro_cpi_total_12
        # Ставка известна к концу месяца; будущие решения ЦБ не подставляются.
        rate = self.national.key_rate_end
        f["macro_key_rate"] = rate.get(origin, np.nan)
        f["macro_key_rate_change3"] = rate.get(origin, np.nan) - rate.get(month(origin, -3), np.nan)

        weather_period = month(origin, -lag["weather"])
        for col in ("T2M", "PRECTOTCORR"):
            current = self._values(self.weather, col, weather_period)
            norm = self._climate(col, weather_period, weather_period[5:7])
            anomaly = current - norm
            if col == "PRECTOTCORR":
                anomaly = np.log1p(current) - np.log1p(norm)
            f[f"weather_{col}_anomaly"] = anomaly
            past = []
            for j in range(3):
                q = month(weather_period, -j)
                a, n = self._values(self.weather, col, q), self._climate(col, q, q[5:7])
                past.append(a - n if col == "T2M" else np.log1p(a) - np.log1p(n))
            f[f"weather_{col}_anomaly3"] = np.mean(past, axis=0)
            future_norm = self._climate(col, weather_period, target[5:7])
            f[f"weather_{col}_climate_target"] = future_norm
            f[f"weather_{col}_climate_change"] = future_norm - self._climate(col, weather_period, origin[5:7])

        for col in ("days", "workdays", "holidays", "weekends"):
            calendar = self.national[col]
            f[f"calendar_{col}"] = calendar.get(target, np.nan)
            f[f"calendar_{col}_yoy"] = calendar.get(target, np.nan) - calendar.get(month(target, -12), np.nan)
        np0 = month(origin, -lag["news"])
        for col in self.news_types:
            f[f"news_{col}"] = np.log1p(self._values(self.news, col, np0, zero=True))
            counts = sum(self._values(self.news, col, month(np0, -j), zero=True) for j in range(3))
            f[f"news_{col}_3m"] = np.log1p(counts)
        f = f.replace([np.inf, -np.inf], np.nan)
        self.feature_cache[t, h] = f
        return f

    def labels(self, t, h, cutoff):
        if t + h > cutoff:
            raise ValueError("Обучающая цель лежит после точки прогноза")
        return self.aggregate(np.log(self.panel.y[:, t + h]) - np.log(self.base[t][:, h - 1]))

    def training_pairs(self, cutoff):
        return [(t, h) for t in sorted(self.base) if t < cutoff
                for h in range(1, self.base[t].shape[1] + 1) if t + h <= cutoff]

    def predict(self, cutoff, steps, signals, estimator):
        pairs = self.training_pairs(cutoff)
        if len({t for t, h in pairs}) < self.settings["min_training_origins"]:
            return np.zeros((len(self.cells), steps)), {"training_examples": 0, "training_origins": len({t for t, h in pairs})}
        X = pd.concat([self.features(t, h) for t, h in pairs], ignore_index=True)
        Y = np.concatenate([self.labels(t, h, cutoff) for t, h in pairs])
        categories = np.tile(self.cells.category.to_numpy(), len(pairs))
        columns = [c for c in X if c.startswith("ctl_") or any(c.startswith(s + "_") for s in signals)]
        X = X[columns]
        future = pd.concat([self.features(cutoff, h)[columns] for h in range(1, steps + 1)], ignore_index=True)
        pred = np.zeros(len(future))
        if estimator == "ridge":
            for cat in self.category_codes:
                ix = categories == cat
                select = np.tile(self.cells.category.to_numpy() == cat, steps)
                if ix.sum() < self.settings["min_training_examples"]:
                    continue
                model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                                      StandardScaler(), Ridge(alpha=self.settings["ridge_alpha"]))
                model.fit(X.loc[ix], Y[ix])
                pred[select] = model.predict(future.loc[select])
        elif estimator == "lgbm":
            X = X.assign(category_code=[self.category_codes[c] for c in categories])
            future = future.assign(category_code=np.tile(self.cells.category.map(self.category_codes), steps))
            model = lgb.train(dict(objective="regression_l1", learning_rate=0.05, num_leaves=7,
                                   min_data_in_leaf=80, lambda_l2=20, verbose=-1, num_threads=4,
                                   seed=self.settings["seed"], deterministic=True, force_col_wise=True),
                              lgb.Dataset(X, label=Y, categorical_feature=["category_code"]), num_boost_round=80)
            pred = model.predict(future)
        else:
            raise ValueError(estimator)
        cap = self.settings["correction_cap"]
        result = np.clip(pred.reshape(steps, len(self.cells)).T, -cap, cap)
        audit = {"training_examples": len(Y), "training_origins": len({t for t, h in pairs}),
                 "latest_training_target": self.panel.periods[max(t + h for t, h in pairs)],
                 "features": columns}
        return result, audit
