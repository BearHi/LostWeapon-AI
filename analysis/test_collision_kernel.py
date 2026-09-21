"""Synthetic geometry tests, NOT game-playability validation."""
import unittest
from collision_kernel import Body, Rect, sweep_rect, trace_polyline


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.body = Body(.8, 1.8)  # Synthetic test dimensions, not measured.
        self.floor = Rect(0, 10, 10, 11)

    def test_standing_contact_allowed(self):
        self.assertIsNone(sweep_rect((5,10), (5,10), self.body, self.floor))

    def test_walking_on_floor_allowed(self):
        self.assertIsNone(sweep_rect((2,10), (8,10), self.body, self.floor))

    def test_jump_away_from_floor_allowed(self):
        self.assertIsNone(sweep_rect((5,10), (5,5), self.body, self.floor))

    def test_land_exactly_on_floor_allowed(self):
        self.assertIsNone(sweep_rect((5,5), (5,10), self.body, self.floor))

    def test_one_1024_cell_penetration_detected(self):
        self.assertIsNotNone(sweep_rect((5,5), (5,10+1/1024), self.body, self.floor))

    def test_penetration_at_start_detected(self):
        self.assertIsNotNone(sweep_rect((5,10+1/1024), (5,5), self.body, self.floor))

    def test_early_wall_not_skipped(self):
        hit = sweep_rect((0,5), (20,5), self.body, Rect(.5,3,.6,6))
        self.assertIsNotNone(hit)
        self.assertLess(hit['exit_t'], .08)

    def test_late_wall_not_skipped(self):
        hit = sweep_rect((0,5), (20,5), self.body, Rect(19.8,3,19.9,6))
        self.assertIsNotNone(hit)
        self.assertGreater(hit['entry_t'], .92)

    def test_thin_wall_no_tunneling(self):
        hit = sweep_rect((0,5), (100,5), self.body, Rect(50,3,50.001,6))
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit['entry_t'], .496)

    def test_reverse_path_same_contact(self):
        wall = Rect(5,3,6,6)
        forward = sweep_rect((0,5), (10,5), self.body, wall)
        reverse = sweep_rect((10,5), (0,5), self.body, wall)
        self.assertAlmostEqual(forward['entry_t'], 1-reverse['exit_t'])

    def test_two_cell_passage(self):
        obstacles = [Rect(0,8,10,9), Rect(0,11,10,12)]
        self.assertFalse(trace_polyline([(0,1,11),(1,9,11)], self.body, obstacles)['hits'])

    def test_one_cell_passage(self):
        ceiling = Rect(0,9,10,10)
        self.assertIsNotNone(sweep_rect((1,11), (9,11), self.body, ceiling))

    def test_one_cell_landing_width_allowed(self):
        self.assertIsNone(sweep_rect((5.5,5), (5.5,10), self.body, Rect(5,10,6,11)))

    def test_ceiling_detected(self):
        self.assertIsNotNone(sweep_rect((5,10), (5,8), self.body, Rect(0,6,10,7)))

    def test_side_touch_no_penetration(self):
        self.assertIsNone(sweep_rect((3,5),(3,6),Body(2,2),Rect(4,2,5,9)))

    def test_single_corner_touch_no_penetration(self):
        # Expanded obstacle for bottom-center is (3,6) x (4,7).
        # Path only touches its lower-left corner at (3,7).
        self.assertIsNone(sweep_rect((2,6),(4,8),Body(2,2),Rect(4,4,5,5)))

    def test_timed_segments(self):
        result = trace_polyline([(2,0,5),(4,10,5)], self.body, [Rect(5,3,6,6)])
        self.assertAlmostEqual(result['hits'][0]['entry_time'], 2.92)
        self.assertFalse(result['engine_clear_certified'])

    def test_clear_does_not_certify_game(self):
        result = trace_polyline([(0,0,0),(1,0,-1)],self.body,[])
        self.assertEqual(result['status'], 'supplied_geometry_clear')
        self.assertFalse(result['engine_clear_certified'])

    def test_bad_inputs_rejected(self):
        for width, height in [(0,1),(-1,1),(1,float('nan'))]:
            with self.assertRaises(ValueError): Body(width,height)
        with self.assertRaises(ValueError): Rect(0,0,0,1)
        with self.assertRaises(ValueError): trace_polyline([(1,0,0),(1,0,1)],self.body,[])
        with self.assertRaises(ValueError): sweep_rect((float('nan'),0),(0,0),self.body,self.floor)


if __name__ == '__main__':
    unittest.main()
