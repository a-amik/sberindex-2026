import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("release_audit", Path(__file__).resolve().parents[1] / "scripts/audit_macro_releases.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReleaseExtractionTests(unittest.TestCase):
    def test_wrapped_labels_and_reference_columns_are_not_mixed(self):
        text = """Индексы потребительских цен на товары и услуги
Индекс потребительских
цен 100.28 105.49
продовольственные
товары 1 99.81 104.16
непродовольственные
товары 100.39 104.17
услуги 100.64 109.18
Индексы цен на отдельные
"""
        result = m.cpi_from_text(text, "krasnodar", 0)
        self.assertEqual(result, dict(cpi_total=100.28, cpi_food=99.81, cpi_nonfood=100.39, cpi_services=100.64))

    def test_petersburg_uses_requested_month_and_excludes_subgroup(self):
        text = """Потребительские товары и услуги 100,77 100,86 100,52 100,62 100,49 103,30
 продовольственные товары 100,96 100,79 100,11 100,77 99,79 102,43
 без овощей, картофеля и фруктов 100,38 100,22 100,77 101,05 100,49 102,93
 непродовольственные товары 100,76 100,38 100,30 100,47 100,12 102,04
 услуги 100,55 101,52 101,29 100,62 101,77 105,88
Ниже приведены"""
        self.assertEqual(m.cpi_from_text(text, "petersburg", 4), dict(cpi_total=100.49, cpi_food=99.79, cpi_nonfood=100.12, cpi_services=101.77))


if __name__ == "__main__":
    unittest.main()
