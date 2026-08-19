import unittest

from crawlkit.classifier import StoryClassifier


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.clf = StoryClassifier()

    def test_source_tag_routes_fantasy(self):
        res = self.clf.classify_fields(
            "A Visit", ["Monster"], ["Fiction"], [], "A visitor arrives."
        )
        self.assertEqual(res["primary_niche"], "fantasy_monster_scifi")
        self.assertEqual(res["target_funnel"], "pod_2_merch_newsletter")
        self.assertIn("monster", res["seo_slug"])

    def test_fallback_when_empty(self):
        res = self.clf.classify_fields(
            "Plain Example", ["Essay"], [], [], "Weather crossed the valley."
        )
        self.assertEqual(res["primary_niche"], "niche_relational_romance")

    def test_tag_weight_beats_body_repetition(self):
        # Even with 100 mentions of 'monster' in the body, body_match_cap caps it to 3 points,
        # while tag 'BDSM' gives 6 points.
        res = self.clf.classify_fields("A Story", ["BDSM"], [], [], "monster " * 100)
        self.assertEqual(res["primary_niche"], "kink_power_dynamics")


if __name__ == "__main__":
    unittest.main()
