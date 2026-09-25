import unittest

from sword_fight_learning import SwordFightLearningRecorder


def player(identity, hp, x, *, state38=7, weapon=1):
    return {"identity_key": identity, "global_user_index": 0, "nickname": identity,
            "pos": [x, 100], "hp": hp, "weapon": weapon,
            "state": {"0x38": state38, "0x74": -1, "0xdc": 0}}


class FightLearningRecorderTests(unittest.TestCase):
    def setUp(self):
        self.r = SwordFightLearningRecorder("session")
        self.own = player("bot", 100, 100)
        self.target = player("practice", 100, 180, weapon=2)

    def observe(self, ms, **kw):
        args = dict(game_ms=ms, room_index=2, local_slot=0, own=self.own,
                    target=self.target, eligible_opponent_count=1,
                    active_player_count=2, controlled=True, mode="COMBAT_ATTACK",
                    keys_sent=["Z"])
        return self.r.observe(**{**args, **kw})

    def test_action_uses_next_game_observation_and_shaped_hp_reward(self):
        self.observe(1000)
        self.target["hp"] = 75
        self.own["hp"] = 90
        item = self.observe(1016)["transition"]
        self.assertEqual((item["game_ms"], item["next_game_ms"]), (1000, 1016))
        self.assertEqual(item["action"], {"mode": "COMBAT_ATTACK", "keys_sent": ["Z"]})
        self.assertEqual(item["reward"], .15)
        self.assertEqual(item["reward_parts"]["opponent_hp_loss"], 25)
        self.assertIn("causal_attack_attribution_unverified", item["reward_meaning"])

    def test_same_game_time_uses_last_input_at_that_frame(self):
        self.observe(1000)
        self.observe(1000, mode="COMBAT_EVADE", keys_sent=["LEFT", "DOWN"])
        self.own["pos"] = [90, 100]
        sample = self.observe(1016)["transition"]
        self.assertEqual(sample["action"]["mode"], "COMBAT_EVADE")
        self.assertEqual(sample["action"]["keys_sent"], ["DOWN", "LEFT"])

    def test_opponent_hp_zero_creates_terminal_win_event(self):
        self.observe(1000)
        self.target["hp"] = 0
        event = self.observe(1016)
        self.assertEqual(event["outcome"]["outcome"], "win")
        self.assertEqual(event["outcome"]["observed_hp"], {"own": 100, "target": 0})
        self.assertEqual(self.r.counts["wins"], 1)

    def test_local_hp_zero_creates_loss_and_simultaneous_zero_draw(self):
        self.observe(1000)
        self.own["hp"] = 0
        self.assertEqual(self.observe(1016)["outcome"]["outcome"], "loss")
        self.own["hp"] = 100
        self.target["hp"] = 100
        self.observe(1032)
        self.own["hp"] = 0
        self.target["hp"] = 0
        self.assertEqual(self.observe(1048)["outcome"]["outcome"], "draw")

    def test_no_sample_without_bot_control_or_with_multiplayer_attribution(self):
        self.observe(1000)
        self.assertIsNone(self.observe(1016, controlled=False))
        self.observe(1032)
        self.assertIsNone(self.observe(1048, active_player_count=3))
        self.assertEqual(self.r.counts["transitions"], 0)

    def test_refill_is_excluded_as_reward(self):
        self.own["hp"] = 20
        self.observe(1000)
        self.own["hp"] = 100
        self.assertIsNone(self.observe(1016))
        self.assertEqual(self.r.counts["transitions"], 0)

    def test_observation_gap_over_300ms_is_excluded(self):
        self.observe(1000)
        self.assertIsNone(self.observe(1400))
        self.assertEqual(self.r.counts["transitions"], 0)

    def test_target_switch_starts_new_aligned_sequence(self):
        self.observe(1000)
        new_target = player("second", 80, 200)
        self.assertIsNone(self.observe(1016, target=new_target))
        self.assertIsNone(self.observe(1032))
        self.assertIsNone(self.observe(1048)["outcome"])
        self.assertEqual(self.r.counts["transitions"], 1)


if __name__ == "__main__":
    unittest.main()
