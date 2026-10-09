import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sbi.models.prospective_signals import ProspectiveContext, announced_features
from test_regional_signals import fixture


class ProspectiveTests(unittest.TestCase):
    def test_late_announcement_and_late_cancellation_do_not_rewrite_past(self):
        event = dict(id="p", type="insurance_pension", announced_at="2023-12-27T11:56:00+03:00",
                     start="2024-01-01", region_key="r0", magnitude_pct=7.5, status="confirmed")
        invisible = announced_features([event], "2023-11", "2024-01", ["r0", "r1"])
        self.assertEqual(invisible.to_numpy().sum(), 0)
        visible = announced_features([event], "2023-12", "2024-01", ["r0", "r1"])
        self.assertEqual(visible.iloc[0, 0], .075)
        self.assertEqual(visible.iloc[1].sum(), 0)
        cancel = dict(event, announced_at="2024-01-10T00:00:00+03:00", status="cancelled")
        pd.testing.assert_frame_equal(visible, announced_features([event, cancel], "2023-12", "2024-01", ["r0", "r1"]))
        self.assertEqual(announced_features([event, cancel], "2024-01", "2024-01", ["r0", "r1"]).to_numpy().sum(), 0)

    def test_search_future_values_do_not_change_forecast(self):
        context = fixture()
        context.__class__ = ProspectiveContext
        rows = []
        for region in ("russia", "r0", "r1", "r2"):
            for category in ("a", "b"):
                for i, period in enumerate(pd.period_range("2022-01", "2024-12", freq="M").astype(str)):
                    rows.append(dict(region_key=region, category=category, period=period, share_pct=1+i*.03))
        context.search_data = pd.DataFrame(rows)
        context.search = context.search_data.set_index(["region_key", "category", "period"])["share_pct"]
        context.event_data = []
        context.settings["release_lags"]["search"] = 1
        t = context.panel.pos("2024-06")
        before, _ = context.predict(t, 6, ["search"], "ridge")
        context.search.loc[context.search.index.get_level_values("period") > "2024-05"] = 10000
        context.feature_cache.clear()
        after, _ = context.predict(t, 6, ["search"], "ridge")
        np.testing.assert_allclose(before, after)
        np.testing.assert_array_equal(after[:, 3:], 0)


if __name__ == "__main__":
    unittest.main()
