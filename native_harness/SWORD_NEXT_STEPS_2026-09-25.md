# SWORD — live navigation feedback and demonstration capture

## Goal and boundaries

Build a sword-fighting bot that can traverse terrain and adapt to opponents.
CLEAR stays frozen. No 051119 DQN is connected to v9. No Native Client was
started, controlled, or used for validation during this change.

The physics engine is useful for checking candidate movements and generating
practice data. It does not itself supply a combat policy, opponent strategy,
human technique timing, or evidence that a live input succeeded.

## Implemented this session

- Grounded airborne-transition edges leave the source ledge before steering
  toward the lower platform. Departure continues until vertical/state evidence
  changes; merely crossing the platform's X boundary does not count as falling.
- Non-executable first edges are skipped in a bounded search. If no complete
  route exists, a usable intermediate hop that improves target distance can be
  selected and is explicitly logged as a partial recovery route.
- A failed edge remains excluded in the same opponent identity/region/ladder
  context for the session. Five seconds passing does not allow another attempt.
  Returning to an earlier failed context retains its exclusion. New room/local
  identity/map-verification contexts reset the session-local guard.
- Only dispatched navigation inputs start transition tracking. Subsequent
  observations distinguish progress, actual ladder state, stable target-support
  contact, wrong-support landing, no progress, and an 8-second deadline.
- An active transition keeps its original destination through flight rather
  than replanning from whichever surface happens to be nearest in midair.
- Paused/unfocused/manual/dead contexts and observed damage cancel the attempt.
  Combat, weapon, or parachute overrides stop navigation tracking. Geometric
  candidates retain `native_required`; live observations do not certify native
  reachability or promote edges to a native-verified route cache.
- Jump inputs release UP after airborne state; roll lock states release route
  inputs. Ladder ascent requests a diagonal exit near the destination support.
- `--record-demonstration` captures v9 local-player and opponent observations
  with named game-key samples before/after each read. It cannot be combined
  with `--act`. F8 starts/pauses capture; F9 stops. It does not train a model.

## Validation

Python: `C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe`

From `native_harness`, `-m unittest discover -s tests -p "test_sword_*.py"`
passes **75 tests** (25 new tests). No emulator ticks or Client startup.
One pre-existing MPC test imported the old location of the horizontal helper;
its import now points to the current navigation module without changing assertions.

The stage07 regression reproduces the trial2 source `(212,736)` with the target
on `surface:50:3-8`. It requests a left ledge departure, then—if subsequent
observations show no progress—excludes that edge and requests a rightward
`safe_drop` via another surface, including after 6.2 and 30 seconds.
This is decision/feedback regression evidence, not a measured new trajectory.

## Next user-run checks

1. Start/select the existing v9 Client on stage07, then run
   `SWORD_navigation_60s.bat`. F8 arms the bot. Test an opponent directly above,
   directly below, and across a ladder; F9 stops early.
2. Inspect `logs/sword_live_closed_loop_trial.jsonl` for
   `navigation_transition_outcome`, `navigation_edge_rejected`,
   `navigation_feedback`, and `navigation_excluded_edges`. Confirm actual
   ladder/landing observations, not just `NAVIGATE` requests.
3. In a separate human-controlled session on this PC, run
   `SWORD_record_demonstration.bat`. Demonstrate ladder exits/front rolls,
   platform jumps, attack approaches, and evades. Pause recording during chat.
   Output: `logs/sword_human_demonstration.jsonl`.

## From demonstration to a fighting policy

1. Collect human state + input + elapsed time + subsequent state. A remote
   opponent's pose/position alone does not expose their actual key presses.
   If the human plays on another PC, capture on that PC too; synchronize by game
   time/session and keep the player identities explicit.
2. Align key samples and state transitions, segment short skills, and label
   outcomes. Keep mistakes as outcomes, not automatic expert actions. Split
   train/evaluation by session/opponent, not adjacent frames from one bout.
3. Train a small policy locally from the demonstrations and evaluate on held-out
   situations. Include observation history, local terrain, relative position,
   weapon, posture, and recent inputs. Re-observe after each short action.
4. Let the user correct situations where the bot fails, record the correction,
   and add it to training. This is the iterative demonstration/correction
   direction described by [DAgger](https://proceedings.mlr.press/v15/ross11a.html).
5. Opponent adaptation should adjust tactical choices from reliable outcomes
   and recent opponent behavior. The existing 0/100/180ms roll-delay memory
   remains a narrow online adaptation, not a learned general combat policy.

Observation-only imitation is possible in research, but requires an additional
model to infer actions from transitions; see
[Behavioral Cloning from Observation](https://arxiv.org/abs/1805.01954).
Direct input capture is the simpler starting point here.

## Remaining limits

- No live landing, ladder-roll technique, speed gain, or fighting strength was
  validated in this session. Short user-run Client validation remains required.
- `GetAsyncKeyState` cannot distinguish a physical key that overlaps a key the
  bot already holds. The old mixed-control trial2 log is not clean demonstration
  data. Use the dedicated mode with no other injector; same-key manual takeover
  during bot control remains a known attribution limitation.
- Demonstration samples are OS key samples, not exact per-game-tick action
  labels. `expert_action_label` stays null until temporal alignment/review.
- No imitation trainer, trained model, or learned ladder-front-roll policy was
  added. The new recorder prepares evidence for that next step.
