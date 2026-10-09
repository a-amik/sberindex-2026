"""Проверки временной доступности и географии региональных сигналов."""
import sys
import unittest
import importlib.util
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from sbi.backtest import Panel
from sbi.models.regional_signals import RegionalContext, month, prepare_regional

spec = importlib.util.spec_from_file_location("regional_experiment", Path(__file__).resolve().parents[1] / "scripts" / "09_regional_signals.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def fixture():
    periods = pd.period_range("2023-01", "2024-12", freq="M").astype(str).tolist()
    index = pd.DataFrame([(i, cat) for i in range(6) for cat in ("a", "b")], columns=["territory_id", "category"])
    mo = pd.DataFrame({"territory_id": range(6), "region_key": ["r0", "r0", "r1", "r1", "r2", "r2"]})
    y = (np.arange(12)[:, None] + 10) * np.exp(np.arange(24)[None, :] * 0.02)
    panel = Panel(y, periods, index)
    frames = []
    for t in range(11, 23):
        for h in range(1, min(12, 23-t) + 1):
            frames.append(pd.DataFrame({"row": np.arange(12), "origin": periods[t], "step": h,
                                        "target": periods[t+h], "y": y[:, t+h], "y_origin": y[:, t],
                                        "yhat": y[:, t] * np.exp(h*0.01)}))
    regional, weather, news = [], [], []
    dates = pd.period_range("2018-01", "2024-12", freq="M").astype(str).tolist()
    for r in range(3):
        for j, p in enumerate(dates):
            regional.append({"region_key": f"r{r}", "period": p, "cpi_total": 100.5+r*.1,
                             "cpi_food": 100.4, "cpi_nonfood": 100.2, "cpi_services": 100.8,
                             "wage": 10000*np.exp(j*.01)})
            news.append({"region_key": f"r{r}", "period": p, "flood": j%3})
    for i in range(6):
        for j, p in enumerate(dates):
            weather.append({"territory_id": i, "period": p, "T2M": np.sin(j/12*2*np.pi)*10+i,
                            "PRECTOTCORR": 2+i/10})
    nat = pd.DataFrame({"period": dates, "key_rate_end": 8, "days": 30, "workdays": 21, "holidays": 1, "weekends": 8})
    settings = {"release_lags": {"cpi": 2, "wage": 3, "weather": 2, "news": 0}, "ridge_alpha": 100,
                "min_training_origins": 2, "min_training_examples": 2, "correction_cap": .15, "seed": 42}
    return RegionalContext(panel, mo, pd.concat(frames, ignore_index=True), pd.DataFrame(regional),
                           pd.DataFrame(weather), nat, pd.DataFrame(news), settings)


class AvailabilityTests(unittest.TestCase):
    def test_unavailable_observations_cannot_change_forecast(self):
        c = fixture()
        t, h = c.panel.pos("2024-06"), 3
        original = c.features(t, h).copy()
        forecast, _ = c.predict(t, 6, ["macro", "weather", "calendar", "news"], "ridge")
        c.panel.y[:, t+1:] *= 1000
        for col in ("cpi_total", "cpi_food", "cpi_nonfood", "cpi_services"):
            c.regional.loc[c.regional.index.get_level_values("period") > month("2024-06", -2), col] = 900
        c.regional.loc[c.regional.index.get_level_values("period") > month("2024-06", -3), "wage"] = 1e9
        c.weather.loc[c.weather.index.get_level_values("period") > month("2024-06", -2), :] = 10000
        c.news.loc[c.news.index.get_level_values("period") > "2024-06", :] = 100000
        c.national.loc[c.national.index > "2024-06", "key_rate_end"] = 99
        c.feature_cache.clear()
        pd.testing.assert_frame_equal(original, c.features(t, h))
        altered, _ = c.predict(t, 6, ["macro", "weather", "calendar", "news"], "ridge")
        np.testing.assert_allclose(forecast, altered)

    def test_available_observation_changes_its_feature(self):
        c = fixture()
        t = c.panel.pos("2024-06")
        old = c.features(t, 1).macro_cpi_total_m.copy()
        c.regional.loc[("r0", "2024-04"), "cpi_total"] += 1
        c.feature_cache.clear()
        new = c.features(t, 1).macro_cpi_total_m
        self.assertTrue((new != old).any())

    def test_training_labels_never_cross_cutoff(self):
        c = fixture()
        for cutoff in range(11, 23):
            self.assertTrue(all(t+h <= cutoff for t, h in c.training_pairs(cutoff)))
        with self.assertRaises(ValueError):
            c.labels(15, 3, cutoff=17)

    def test_no_training_returns_base_correction(self):
        c = fixture()
        correction, _ = c.predict(11, 12, ["macro"], "ridge")
        np.testing.assert_array_equal(correction, np.zeros((6, 12)))

    def test_geography_selects_region_without_autonomous_areas(self):
        cpi = pd.DataFrame({"region_key": ["тюменская"]*2, "period": ["2024-01"]*2, "kind": ["region"]*2,
                            "region": ["Тюменская область", "Тюменская область (кроме автономных округов)"],
                            "cpi_total": [105, 101], "cpi_food": [105, 101], "cpi_nonfood": [105, 101], "cpi_services": [105, 101]})
        wage = pd.DataFrame({"region_key": ["тюменская"]*2, "period": ["2024-01"]*2,
                             "region": ["Тюменская область", "Тюменская область без авт. округов"], "wage": [100000, 60000]})
        r = prepare_regional(cpi, wage)
        self.assertEqual(len(r), 1)
        self.assertEqual(r.iloc[0].cpi_total, 101)
        self.assertEqual(r.iloc[0].wage, 60000)

    def test_region_is_population_weighted_and_excludes_unknown_population(self):
        panel = Panel(np.ones((3, 2)), ["2023-12", "2024-01"],
                      pd.DataFrame({"territory_id": [1, 2, 3], "category": ["a"]*3}))
        mo = pd.DataFrame({"territory_id": [1, 2, 3], "region_key": ["r"]*3, "pop": [1, 3, np.nan]})
        frame = pd.DataFrame({"row": [0, 1, 2], "origin": ["2023-12"]*3, "step": [1]*3,
                              "target": ["2024-01"]*3, "y": [10, 20, 1000], "yhat": [12, 18, 999], "y_origin": [8]*3})
        region = experiment.regional_frame(frame, panel, mo)
        self.assertEqual(region.iloc[0].y, 17.5)
        self.assertEqual(region.iloc[0].yhat, 16.5)
        self.assertEqual(region.iloc[0].n_mo, 2)

    def test_selection_contains_no_report_targets(self):
        from sbi.config import load
        settings = load(Path(__file__).resolve().parents[1] / "configs" / "regional_signals.yaml")["regional_signals"]
        frame = pd.DataFrame({"origin": ["2024-04", "2024-04", "2024-06"], "target": ["2024-05", "2024-06", "2024-07"], "step": [1, 2, 1]})
        choice = experiment.selected_rows(frame, settings)
        self.assertEqual(choice.target.to_list(), ["2024-05"])


if __name__ == "__main__":
    unittest.main()
