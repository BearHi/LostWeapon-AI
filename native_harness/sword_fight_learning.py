"""Timestamp-aligned, scored two-player experience from sent Client actions."""
from __future__ import annotations


class SwordFightLearningRecorder:
    """Append transition samples; never changes the live combat policy.

    At each newly observed game time, pair the previous observation with the
    last input actually sent during that frame, then score the observed HP
    balance change. Multiplayer and missing control/target evidence are dropped.
    """

    def __init__(self, session_id, *, max_gap_ms=300):
        self.session_id = str(session_id)
        self.max_gap_ms = int(max_gap_ms)
        self.previous = None
        self.last_game_ms = None
        self.bout_index = 0
        self.bout_score = 0.0
        self.bout_samples = 0
        self.counts = {"transitions": 0, "wins": 0, "losses": 0,
                       "draws": 0, "excluded": 0}

    @staticmethod
    def _state(player, *keys, default=None):
        raw = player.get("state") or {}
        for key in keys:
            if key in raw:
                return raw[key]
        return default

    @classmethod
    def _features(cls, own, target):
        ox, oy = map(float, own["pos"])
        tx, ty = map(float, target["pos"])
        return {
            "relative_position": [round(tx - ox, 1), round(ty - oy, 1)],
            "own_hp": round(float(own["hp"]), 1),
            "target_hp": round(float(target["hp"]), 1),
            "own_weapon": own.get("weapon"), "target_weapon": target.get("weapon"),
            "own_state38": cls._state(own, "0x38", "38", "state38"),
            "target_state38": cls._state(target, "0x38", "38", "state38"),
            "own_state74": cls._state(own, "0x74", "74", "state74", default=-1),
            "target_state74": cls._state(target, "0x74", "74", "state74", default=-1),
            "own_dc": cls._state(own, "0xdc", "dc", default=0),
            "target_dc": cls._state(target, "0xdc", "dc", default=0),
        }

    def _reset_segment(self):
        self.previous = None
        self.last_game_ms = None

    def observe(self, *, game_ms, room_index, local_slot, own, target,
                eligible_opponent_count, active_player_count, controlled,
                mode, keys_sent):
        """Return at most one transition or terminal bout event for this poll."""
        if (own is None or target is None or eligible_opponent_count != 1 or
                active_player_count != 2 or not controlled):
            if self.previous is not None:
                self.counts["excluded"] += 1
            if (target is None or eligible_opponent_count != 1 or
                    active_player_count != 2):
                if self.bout_samples:
                    self.bout_index += 1
                self.bout_score = 0.0
                self.bout_samples = 0
            self._reset_segment()
            return None
        target_id = (target.get("identity_key") or
                     f"{target.get('global_user_index')}:{target.get('nickname', '')}")
        context = (room_index, local_slot, target_id)
        current = {"game_ms": int(game_ms), "context": context,
                   "own": self._features(own, target),
                   "own_hp": float(own["hp"]),
                   "target_hp": float(target["hp"]),
                   "mode": str(mode), "keys": sorted(keys_sent or ())}
        if self.previous is None:
            self.previous, self.last_game_ms = current, int(game_ms)
            return None
        previous = self.previous
        if context != previous["context"] or int(game_ms) < previous["game_ms"]:
            self.counts["excluded"] += 1
            if self.bout_samples:
                self.bout_index += 1
            self.bout_score = 0.0
            self.bout_samples = 0
            self._reset_segment()
            self.previous, self.last_game_ms = current, int(game_ms)
            return None
        if int(game_ms) == previous["game_ms"]:
            # Keep the final actually-sent action held at this game timestamp;
            # the next observation closes that transition.
            previous.update({"mode": str(mode), "keys": sorted(keys_sent or ())})
            return None
        gap = int(game_ms) - previous["game_ms"]
        self.previous, self.last_game_ms = current, int(game_ms)
        if gap > self.max_gap_ms:
            self.counts["excluded"] += 1
            return None
        # Positive HP jumps are respawns/refills. Never mislabel them as
        # rewards for the preceding action.
        if (current["own_hp"] > previous["own_hp"] + 1 or
                current["target_hp"] > previous["target_hp"] + 1):
            self.counts["excluded"] += 1
            return None
        own_loss = max(0.0, previous["own_hp"] - current["own_hp"])
        target_loss = max(0.0, previous["target_hp"] - current["target_hp"])
        reward = (target_loss - own_loss) / 100.0
        terminal = None
        if current["own_hp"] <= 0 or current["target_hp"] <= 0:
            if current["own_hp"] <= 0 and current["target_hp"] <= 0:
                terminal = "draw"
            elif current["target_hp"] <= 0:
                terminal = "win"
            else:
                terminal = "loss"
            reward += {"win": 1.0, "loss": -1.0, "draw": 0.0}[terminal]

        self.bout_score += reward
        self.bout_samples += 1
        self.counts["transitions"] += 1
        transition = {
            "type": "fight_transition", "schema": 1,
            "session_id": self.session_id,
            "bout_id": f"{self.session_id}-{self.bout_index}",
            "room_index": int(room_index), "local_slot": local_slot,
            "game_ms": previous["game_ms"], "next_game_ms": int(game_ms),
            "observed_game_gap_ms": gap,
            "state": previous["own"],
            "action": {"mode": previous["mode"], "keys_sent": previous["keys"]},
            "next_state": current["own"],
            "reward": round(reward, 4),
            "reward_parts": {"opponent_hp_loss": round(target_loss, 2),
                             "own_hp_loss": round(own_loss, 2),
                             "terminal": terminal},
            "reward_meaning": "relative_duel_hp_change; causal_attack_attribution_unverified",
        }
        if terminal:
            result_key = {"win": "wins", "loss": "losses", "draw": "draws"}[terminal]
            self.counts[result_key] += 1
            outcome = {"type": "fight_bout_outcome", "schema": 1,
                       "session_id": self.session_id,
                       "bout_id": transition["bout_id"], "outcome": terminal,
                       "observed_hp": {"own": current["own_hp"],
                                       "target": current["target_hp"]},
                       "cumulative_reward": round(self.bout_score, 4),
                       "transition_count": self.bout_samples,
                       "evidence": "observed_hp_zero_in_two_player_room"}
            self.bout_index += 1
            self.bout_score = 0.0
            self.bout_samples = 0
            return {"transition": transition, "outcome": outcome}
        return {"transition": transition, "outcome": None}
