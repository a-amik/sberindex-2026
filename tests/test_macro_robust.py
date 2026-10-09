import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from test_regional_signals import fixture
from sbi.models.macro_components import MacroComponents

spec = importlib.util.spec_from_file_location("robust", Path(__file__).resolve().parents[1] / "scripts/regional_macro_robust.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RobustTests(unittest.TestCase):
    def test_one_good_policy_cannot_admit_bad_or_missing_policy(self):
        s = dict(policies=dict(standard={}, older={}), minimum_regional_gain_pct=1,
                 maximum_municipal_loss_pct=0, minimum_active_origins=2)
        row = dict(variant="macro", strength=.25, policy="standard", regional_MAE=10,
                   regional_gain_pct=10, municipal_loss_pct=-2, active_origins=3)
        self.assertEqual(m.choose_robust([row], s)["variant"], "base")
        older = dict(row, policy="older", regional_gain_pct=-1)
        self.assertEqual(m.choose_robust([row, older], s)["variant"], "base")
        older.update(regional_gain_pct=2, regional_MAE=11)
        self.assertEqual(m.choose_robust([row, older], s)["variant"], "macro")

    def test_nominal_income_does_not_depend_on_cpi_and_rate_does_not_depend_on_lags(self):
        c = fixture();c.__class__ = MacroComponents
        t = c.panel.pos("2024-06")
        before = c.features(t, 1).copy()
        c.regional.loc[:, "cpi_total"] *= 2
        c.regional.loc[:, "cpi_food"] *= 2
        c.settings["release_lags"] = dict(c.settings["release_lags"], cpi=3, wage=4)
        c.feature_cache.clear()
        after = c.features(t, 1)
        pd.testing.assert_frame_equal(before.filter(regex="^rate_"), after.filter(regex="^rate_"))
        c.settings["release_lags"]["wage"] = 3
        c.feature_cache.clear()
        pd.testing.assert_frame_equal(before.filter(regex="^income_"), c.features(t, 1).filter(regex="^income_"))

    def test_unavailable_macro_values_do_not_change_components(self):
        c = fixture();c.__class__ = MacroComponents
        t = c.panel.pos("2024-06")
        before = c.features(t, 1).copy()
        p = c.regional.index.get_level_values("period")
        c.regional.loc[p > "2024-04", ["cpi_total", "cpi_food", "cpi_nonfood", "cpi_services"]] = 900
        c.regional.loc[p > "2024-03", "wage"] = 1e9
        c.feature_cache.clear()
        pd.testing.assert_frame_equal(before, c.features(t, 1))


if __name__ == "__main__":
    unittest.main()
