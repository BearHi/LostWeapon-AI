"""Metadata for opt-in v9 human demonstrations; no automatic training labels."""


def demonstration_sample(*, armed, focused, map_verified, own, before_keys,
                         after_keys, sample_started, sample_finished,
                         game_tick_advanced):
    eligible_context = bool(armed and focused and map_verified and own and
                            own.get("hp", 0) > 0 and
                            (own.get("state") or {}).get("0xc0", 0) != 6)
    # Never retain key samples from other foreground applications or pauses.
    before = sorted(before_keys) if eligible_context else []
    after = sorted(after_keys) if eligible_context else []
    return {
        "schema": "sword-v9-human-demonstration-v1",
        "capture_enabled": eligible_context,
        "input_source": "foreground_os_key_samples_controller_injection_disabled",
        "keys_before_observation": before,
        "keys_after_observation": after,
        "sample_window_seconds": [sample_started, sample_finished],
        "game_tick_advanced": bool(game_tick_advanced),
        "keys_stable_across_observation": eligible_context and before == after,
        "candidate_for_alignment": bool(eligible_context and before == after and game_tick_advanced),
        "expert_action_label": None,
        "note": "Sampled inputs require temporal alignment and episode review before imitation training.",
    }
