import copy
from pathlib import Path
import sys
import unittest
import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared_physics_model import features, plan_tokens, OutcomeModel, PAD


class SharedModelContracts(unittest.TestCase):
    def context(self):
        return {"grid":[[[0,0,0,0] for x in range(9)] for y in range(9)],
                "objects":[[49,0,0],[3,0,0]],"player":{"38":9,"b0":0,"motion58":-12},
                "held":["RIGHT"],"subcell":[1,2],"goal_delta":[10,0]}

    def test_map_identity_and_goal_coordinates_are_not_prediction_inputs(self):
        a=self.context();b=copy.deepcopy(a);b['goal_delta']=[100,-200];b['map']='different_map'
        for x,y in zip(features(a),features(b)):np.testing.assert_array_equal(x,y)

    def test_overlapping_object_ids_stay_separate(self):
        _,obj,_=features(self.context())
        self.assertEqual(obj[4,4,:2].tolist(),[49,3])

    def test_order_duration_and_conditional_chute_are_encoded(self):
        a=plan_tokens([(2,3),(9,2),("chute_RIGHT",4)])
        self.assertEqual(a[:9].tolist(),[2,2,2,9,9,22,22,22,22])
        self.assertTrue((a[9:]==PAD).all())
        self.assertFalse(np.array_equal(a,plan_tokens([(9,2),(2,3),("chute_RIGHT",4)])))
        self.assertEqual(sum(plan_tokens([(2,1000)],7)!=PAD),7)

    def test_state_and_local_geometry_change_features(self):
        a=self.context();b=copy.deepcopy(a);b['player']['b0']=1;b['grid'][4][4][1]=7
        ga,_,sa=features(a);gb,_,sb=features(b)
        self.assertFalse(np.array_equal(ga,gb));self.assertFalse(np.array_equal(sa,sb))

    def test_model_has_trainable_finite_shared_output(self):
        torch.set_num_threads(1)
        grid,obj,scalar=features(self.context())
        model=OutcomeModel()
        args=[torch.from_numpy(x[None]) for x in (grid,obj,scalar,plan_tokens([(2,8)]))]
        result=model(*args)
        self.assertEqual(tuple(result.shape),(1,4))
        result.square().sum().backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))


if __name__=='__main__':unittest.main()
