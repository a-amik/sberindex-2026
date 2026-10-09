"""Поисковые прокси и анонсы, ограниченные точкой прогноза."""
import numpy as np
import pandas as pd

from sbi.models.regional_signals import RegionalContext, month


def announced_features(events, origin, target, regions):
    cutoff = pd.Period(origin, "M").end_time.tz_localize("Europe/Moscow")
    known = [e for e in events if pd.Timestamp(e["announced_at"]) <= cutoff]
    latest = {}
    for e in sorted(known, key=lambda e: pd.Timestamp(e["announced_at"])):
        latest[e["id"]] = e
    types = ("insurance_pension", "monthly_cash_benefits")
    f = {}
    for typ in types:
        pulse, increase = np.zeros(len(regions)), np.zeros(len(regions))
        for e in latest.values():
            if e["type"] != typ or e["status"] != "confirmed":
                continue
            start = e["start"][:7]
            scope = np.array([e["region_key"] in ("*", r) for r in regions])
            if start == target:
                pulse[scope] += e["magnitude_pct"] / 100
            if origin < start <= target:
                increase[scope] += e["magnitude_pct"] / 100
        f[f"events_{typ}_pulse"] = pulse
        f[f"events_{typ}_future_increase"] = increase
    return pd.DataFrame(f)


class ProspectiveContext(RegionalContext):
    search_data = None
    event_data = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search = self.search_data.set_index(["region_key", "category", "period"])["share_pct"]
        if self.search.index.duplicated().any():
            raise ValueError("Поисковый ряд имеет дубли")

    def search_values(self, region_keys, period):
        values = []
        for region, category in zip(region_keys, self.cells.category):
            if category == "Все категории":
                subset = self.search_data[(self.search_data.region_key == region) & (self.search_data.period == period)]
                a = subset.share_pct.to_numpy()
                values.append(np.mean(np.log(a[a > 0])) if len(a[a > 0]) == 5 else np.nan)
            else:
                a = self.search.get((region, category, period), np.nan)
                values.append(np.log(a) if a > 0 else np.nan)
        return np.array(values)

    def features(self, t, h):
        f = super().features(t, h)
        if "search_national_yoy" in f:
            return f
        origin = self.panel.periods[t]
        period = month(origin, -self.settings["release_lags"]["search"])
        for level, keys in (("national", ["russia"] * len(self.cells)), ("regional", self.cells.region_key)):
            current = self.search_values(keys, period)
            f[f"search_{level}_yoy"] = current - self.search_values(keys, month(period, -12))
            f[f"search_{level}_g3"] = current - self.search_values(keys, month(period, -3))
        f["search_regional_relative_yoy"] = f.search_regional_yoy - f.search_national_yoy
        e = announced_features(self.event_data, origin, month(origin, h), self.cells.region_key)
        for col in e:
            f[col] = e[col].to_numpy()
        self.feature_cache[t, h] = f
        return f

    def predict(self, cutoff, steps, signals, estimator):
        prediction, audit = super().predict(cutoff, steps, signals, estimator)
        prediction[:, 3:] = 0
        return prediction, audit
