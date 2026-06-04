# Long-Distance Refill Burst Plan (BLDC Sync Recovery)

Date: 2026-06-04
Owner: Happy-Hare BLDC / Sync-feedback
Status: Planned

## 1) Goal

Implement long-distance refill bursts that recover filament slack/tension mismatch quickly during BLDC synced printing, while keeping scheduler load bounded and avoiding pulse storms.

This feature is a resilience/performance layer. It complements, but does not replace, core cancel/queue/unsync fixes.

## 2) Mitigation Coverage

Expected impact on previously identified findings:

- Finding 4 (neutral-only fallback): strong mitigation.
- Finding 2 (queue replacement starvation): partial mitigation.
- Finding 3 (stale-prune edge losses): partial mitigation.
- Finding 5 (encoder reset transient): partial mitigation.
- Finding 1 (cancel unsync ordering): little or no mitigation.
- Finding 6 (unsync drain-before-stop): little or no mitigation.

## 3) Design Principles

- Use existing two-level tension pulse architecture as base path.
- Keep bursts bounded by distance, time, and cooldown.
- Keep behavior deterministic under noisy sensors and intermittent encoder reads.
- Avoid adding high-frequency pin scheduling paths outside existing queued BLDC dispatch.
- Preserve sync-mode contracts and current Happy-Hare integration boundaries.

## 4) Existing Mechanisms to Extend

Current foundation already supports short refill behavior:

- `SyncController._twolevel_tension_pulse_remaining_mm`
- Config fields:
  - `twolevel_tension_pulse_mm`
  - `twolevel_tension_pulse_strength`
- Manager-side starvation fallback that can inject virtual tension state.

Plan extends this into controlled long-distance bursts with explicit arming, sustain, and cooldown semantics.

## 5) Proposed Feature Behavior

### Burst state machine

Add a lightweight state machine in sync-feedback manager/controller interaction:

- `IDLE`: no active burst.
- `ARMED`: starvation criteria met and cooldown satisfied.
- `ACTIVE`: burst budget is being consumed while `d_ext > 0`.
- `COOLDOWN`: burst complete; re-entry blocked until minimum interval elapsed.

Transitions:

- `IDLE -> ARMED`: starvation evidence threshold reached.
- `ARMED -> ACTIVE`: next positive extrusion tick.
- `ACTIVE -> COOLDOWN`: distance/time budget exhausted or sensor recovery sustained.
- `COOLDOWN -> IDLE`: cooldown timer elapsed.

### Burst trigger criteria

Require all:

- BLDC gear active and synced.
- Positive extrusion movement (`d_ext > 0`).
- Encoder delta below starvation threshold ratio for `N` consecutive events.
- Not in cooldown.
- Not in print-end/cancel/error teardown path.

Optional stricter gate:

- Suppress trigger when extruder speed is below a low-motion floor to avoid noise-triggering at near-zero flow.

### Burst execution model

Primary implementation path (recommended):

- Use existing two-level pulse mechanism but allow larger configurable pulse budget.
- Re-arm pulse while on tension side when starvation persists.
- Consume budget only on positive extrusion movement.
- Clamp RD target to existing envelope (`rd_min`/`rd_max`) through controller pipeline.

Secondary safety guard:

- Global manager-side debounce interval between burst arms.
- Maximum burst runtime cap to prevent prolonged aggressive feed in anomalous states.

### Burst completion criteria

Any of:

- Burst distance budget consumed.
- Encoder recovery is sustained for `M` events.
- Max active duration exceeded.
- Sync disabled / unsync event / print cancel path entered.

## 6) Configuration Additions

Add new guarded parameters in `mmu_parameters.cfg` (or MMU config pipeline):

- `sync_feedback_refill_burst_mm` (float, default conservative).
- `sync_feedback_refill_burst_strength` (0..1).
- `sync_feedback_refill_burst_events` (consecutive starvation events).
- `sync_feedback_refill_burst_cooldown` (seconds, default >= 0.5).
- `sync_feedback_refill_burst_max_active_time` (seconds).
- `sync_feedback_refill_burst_min_speed` (mm/s, optional).

Compatibility mapping:

- Keep existing `sync_feedback_tension_pulse_mm` and `sync_feedback_tension_pulse_strength`.
- If new burst params are unset, preserve current behavior.
- Optionally alias new params to existing pulse fields during migration to avoid duplicated semantics.

## 7) Code-Level Implementation Plan

### A) Manager-level starvation and debounce logic

File:

- `extras/mmu/mmu_sync_feedback_manager.py`

Work:

- Add burst bookkeeping fields:
  - last burst timestamp
  - active/cooldown flags
  - starvation consecutive counter
  - recovery consecutive counter
- Extend `_get_sync_state_with_refill_fallback(...)`:
  - allow virtual tension trigger from any sensed state
  - enforce cooldown/debounce
  - emit reason-tagged debug logs
- Add reset paths on sync start, sync end, print end, and encoder reset hook.

### B) Controller pulse/burst integration

File:

- `extras/mmu/mmu_sync_controller.py`

Work:

- Keep `_twolevel_rd_target(...)` as sole owner of RD target decision.
- Add explicit long-burst parameters into controller config and validation.
- Ensure pulse re-arm semantics remain valid while already on tension level.
- Preserve pulse budget across zero/retract ticks unless explicit abort condition occurs.
- Consume remaining burst budget only on positive extrusion deltas.

### C) Config initialization correctness

Files:

- `extras/mmu/mmu_sync_feedback_manager.py`

Work:

- Ensure `_init_controller()` passes active two-level speed/boost multipliers and pulse/burst settings, not only `_reset_controller()`.
- Keep runtime update path (`MMU_SYNC_FEEDBACK`) consistent with startup initialization.

### D) Encoder reset integration

Files:

- `extras/mmu/mmu.py`
- `extras/mmu/mmu_sync_feedback_manager.py`

Work:

- Add `note_encoder_reset(...)` call from encoder reset path.
- Rebase burst/fallback baselines and clear unsafe residual state.

## 8) Performance and Safety Requirements

- No new direct `set_pwm`/`set_digital` calls outside queue callbacks.
- No increase in high-frequency descriptor churn beyond bounded coalescing.
- No burst-arm frequency above configured cooldown.
- No burst activity after unsync/cancel/error transition starts.
- Keep scheduler headroom with current schedule margin floor.

## 9) Telemetry and Debugability

Add explicit logs (debug level):

- Burst armed, with trigger metrics (move, encoder delta, threshold, count).
- Burst active progress (remaining budget, elapsed time).
- Burst complete reason (budget, recovery, timeout, unsync).
- Burst suppressed reason (cooldown, low speed, non-printing, disabled).

Add status exposure (if feasible through existing status path):

- `refill_burst_active`
- `refill_burst_remaining_mm`
- `refill_burst_cooldown_remaining`
- `refill_starvation_events`

## 10) Validation Plan (Hardware First)

### Scenario matrix

1. Purge-to-print handoff with known starvation tendency.
2. Dense small-segment extrusion (skirt/brim style).
3. Sustained moderate-flow infill.
4. Very low-flow movement (confirm no false burst storms).
5. Encoder reset/reseed during operational transitions.
6. Cancel and print-end transitions (confirm immediate burst abort).

### Required outcomes

- Starvation windows shorten measurably versus baseline.
- No timer-too-close events introduced by burst logic.
- No persistent overfeed after burst completion.
- No regressions in normal non-starvation print phases.

### Tuning workflow

1. Start with conservative burst distance and strength.
2. Increase distance first, then strength, in small increments.
3. Keep cooldown fixed initially.
4. Validate each step against logs and filament behavior.
5. Stop tuning if overfeed oscillation or scheduler pressure appears.

## 11) Rollout Plan

Phase 1: Internal feature flag (disabled by default).

- Land code paths and logging with flag off.
- Validate no behavior change with default config.

Phase 2: Conservative enablement.

- Enable on test rig with low burst distance/strength.
- Tune cooldown and event thresholds.

Phase 3: Production profile adoption.

- Promote tuned defaults to CFS config profiles.
- Document parameter guidance and failure signatures.

## 12) Risks and Mitigations

Risk: Burst overcorrects and causes compression oscillation.
Mitigation: Clamp strength, add recovery-based early exit, enforce cooldown.

Risk: Burst storms under encoder noise/failure.
Mitigation: Consecutive event threshold, cooldown, max active time, encoder-discontinuity rebase.

Risk: Feature masks core queue/cancel bugs.
Mitigation: Treat this as additive only; merge after stability-fix plan milestones.

## 13) Exit Criteria

- Burst feature can be enabled without timer-too-close regressions.
- Demonstrated reduction in starvation duration/frequency in target scenarios.
- No cancel/end-state safety regressions.
- Docs and config references updated with safe default/tuning guidance.
