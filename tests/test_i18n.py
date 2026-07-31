import unittest

from gacha_i18n import LANGUAGE_NAMES, POLICY_LABELS, TEXTS, tr


class I18nTests(unittest.TestCase):
    def test_languages_have_the_same_keys(self):
        self.assertEqual(set(TEXTS["zh"]), set(TEXTS["en"]))
        self.assertEqual(set(POLICY_LABELS["zh"]), set(POLICY_LABELS["en"]))
        self.assertEqual(set(LANGUAGE_NAMES), {"zh", "en"})

    def test_sale_income_wording_excludes_wheelspin_cr(self):
        self.assertIn("重复车出售", tr("zh", "stat_sale_income"))
        self.assertIn("Duplicate-car sale", tr("en", "stat_sale_income"))
        self.assertIn("暂不统计", tr("zh", "income_note"))
        self.assertIn("not counted", tr("en", "income_note"))

    def test_unknown_language_falls_back_to_chinese(self):
        self.assertEqual(tr("unknown", "status_ready"), tr("zh", "status_ready"))


if __name__ == "__main__":
    unittest.main()
