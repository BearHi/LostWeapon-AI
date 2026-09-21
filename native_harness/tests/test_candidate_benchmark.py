from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from candidate_benchmark import safe_to_promote


class PromotionGuard(unittest.TestCase):
    def row(self,**kwargs):
        return dict(groups=500,mean_utility=.8,random_mean_utility=.3,
                    selected_reset_rate=.03,random_reset_rate=.04,**kwargs)

    def test_better_selection_is_eligible(self):
        self.assertTrue(safe_to_promote(self.row(),self.row()))

    def test_more_risky_than_random_is_rejected(self):
        a=self.row();a['selected_reset_rate']=.05
        self.assertFalse(safe_to_promote(a,None))

    def test_safety_regression_against_incumbent_is_rejected(self):
        old=self.row();old['selected_reset_rate']=.01
        self.assertFalse(safe_to_promote(self.row(),old))

    def test_selection_regression_against_incumbent_is_rejected(self):
        old=self.row();old['mean_utility']=.9
        self.assertFalse(safe_to_promote(self.row(),old))

    def test_insufficient_comparisons_do_not_promote(self):
        a=self.row();a['groups']=20
        self.assertFalse(safe_to_promote(a,None))


if __name__=='__main__':unittest.main()
