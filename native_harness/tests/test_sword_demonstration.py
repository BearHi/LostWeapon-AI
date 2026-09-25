import unittest

from sword_demonstration import demonstration_sample


class DemonstrationTests(unittest.TestCase):
    def sample(self, **overrides):
        args = dict(armed=True, focused=True, map_verified=True,
                    own={"hp": 100, "state": {"0xc0": 0}},
                    before_keys=["RIGHT", "DOWN"], after_keys=["DOWN", "RIGHT"],
                    sample_started=1.0, sample_finished=1.002, game_tick_advanced=True)
        return demonstration_sample(**{**args, **overrides})

    def test_stable_keys_are_alignment_candidates_not_automatic_expert_labels(self):
        sample = self.sample()
        self.assertTrue(sample["candidate_for_alignment"])
        self.assertIsNone(sample["expert_action_label"])
        self.assertEqual(sample["keys_before_observation"], ["DOWN", "RIGHT"])

    def test_focus_pause_and_map_gates_remove_key_samples(self):
        for gate in ("focused", "armed", "map_verified"):
            with self.subTest(gate=gate):
                sample = self.sample(**{gate: False})
                self.assertFalse(sample["candidate_for_alignment"])
                self.assertEqual(sample["keys_before_observation"], [])
                self.assertEqual(sample["keys_after_observation"], [])

    def test_input_change_during_read_and_repeated_game_tick_are_not_candidates(self):
        self.assertFalse(self.sample(after_keys=["RIGHT"])["candidate_for_alignment"])
        self.assertFalse(self.sample(game_tick_advanced=False)["candidate_for_alignment"])

    def test_local_player_absence_death_and_jaja_are_excluded(self):
        for own in (None, {"hp": 0}, {"hp": 100, "state": {"0xc0": 6}}):
            self.assertFalse(self.sample(own=own)["candidate_for_alignment"])


if __name__ == "__main__":
    unittest.main()
