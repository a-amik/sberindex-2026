import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("calibration", Path(__file__).resolve().parents[1] / "scripts/regional_horizon_calibration.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CalibrationTests(unittest.TestCase):
    def test_guard_and_insufficient_origins_return_base(self):
        settings = dict(minimum_regional_gain_pct=1, maximum_municipal_loss_pct=0, minimum_active_origins=2)
        candidate = dict(variant="macro", strength=.25, regional_gain_pct=5, municipal_loss_pct=1,
                         active_origins=3, regional_MAE=10)
        self.assertEqual(m.select_candidates([candidate], settings)["variant"], "base")
        candidate.update(municipal_loss_pct=-1, active_origins=1)
        self.assertEqual(m.select_candidates([candidate], settings)["variant"], "base")

    def test_long_steps_are_unchanged_and_intervals_are_removed(self):
        base = pd.DataFrame(dict(step=range(1, 13), yhat=np.full(12, 100.), q05=90, q95=110))
        raw = dict(macro=base.assign(log_correction=.1))
        selected = dict(one=dict(variant="macro", strength=.25), two_three=dict(variant="macro", strength=.5))
        out = m.apply_choice(base, raw, selected, dict(one=[1], two_three=[2, 3]))
        np.testing.assert_array_equal(out.yhat.iloc[3:], base.yhat.iloc[3:])
        self.assertAlmostEqual(out.yhat.iloc[0], 100*np.exp(.025))
        self.assertNotIn("q05", out)


if __name__ == "__main__":
    unittest.main()
