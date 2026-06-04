# Sync Stability Hardening Plan (Cancel, Queueing, Fallback, Encoder Reset)

Date: 2026-06-04
Owner: Happy-Hare BLDC / Sync stack
Status: Planned

## 1) Goal

Stabilize BLDC sync behavior and eliminate known regressions in cancel/unsync flow, process-move queue handling, stale descriptor pruning, refill fallback gating, and encoder reset integration.

This plan addresses the six findings previously identified:

1. Cancel path unsync ordering risk.
2. `process_move_push` queue replacement starvation risk.
3. Strict stale-prune timing-edge risk.
4. Neutral-only refill fallback risk.
5. Missing explicit encoder-reset to sync-feedback rebase hook.
6. Unsync drain-before-stop behavior risk.

## 2) Constraints and Guardrails

- Keep changes within Happy-Hare repo only.
- Do not modify Klipper core (`klipper/klippy/**`, `klipper/src/**`).
- Preserve sync mode contracts (`gear`, `extruder`, `gear+extruder`, `extruder+gear`) and concurrent behavior in combined modes.
- Keep BLDC logic in `extras/mmu/mmu_gear_bldc.py`; keep orchestration in `extras/mmu/mmu.py`.
- Preserve `lookup_object(...)` contract names.
- For BLDC behavior acceptance, require real hardware validation and log inspection.

## 3) Scope

In scope:

- `extras/mmu/mmu.py`
- `extras/mmu/mmu_gear_bldc.py`
- `extras/mmu/mmu_sync_feedback_manager.py`
- Optional small config additions in `printer_data/config/mmu/base/mmu_parameters.cfg` and docs if needed.

Out of scope:

- Full controller algorithm rewrite in `extras/mmu/mmu_sync_controller.py`.
- Klipper-side scheduler changes.

## 4) Fix Strategy by Finding

### Finding 1: Cancel path unsync ordering risk

Target:

- `extras/mmu/mmu.py`, `cmd_MMU_CANCEL_PRINT`

Implementation:

- Unsync immediately when MMU is enabled and currently synced, before park/wrapper moves.
- Use explicit unsync path that guarantees BLDC sync callbacks are deactivated before any cancel park kinematics.
- Keep operation idempotent: if already unsynced, no-op.
- Preserve existing user-visible cancel semantics and macro call ordering around `__CANCEL_PRINT`.

Acceptance:

- No BLDC sync dispatch logs generated after immediate cancel unsync point.
- No MMU MCU timer-too-close triggered during cancel in stress runs.

### Finding 2: `process_move_push` queue replacement starvation risk

Target:

- `extras/mmu/mmu_gear_bldc.py`, `queue_trapzoid_move`

Implementation:

- Remove wholesale deletion of existing `process_move_push` descriptors.
- Replace with bounded coalescing:
  - Keep near-term descriptors inside a short lookback horizon.
  - Drop only older near-duplicates by time and speed tolerance.
- Preserve descriptor ordering by `print_time`.

Acceptance:

- During dense extrusion, queue depth remains bounded without starvation.
- `BLDC_MOTION: source=process_move_push` remains present at steady cadence.

### Finding 3: Strict stale-prune timing-edge risk

Target:

- `extras/mmu/mmu_gear_bldc.py`, `_motion_timer_callback`

Implementation:

- Replace hard `>= current_print_time - EPSILON` prune with guarded stale window:
  - Keep descriptors newer than `current_print_time - stale_grace_s`.
  - Use a dedicated grace constant tuned for mmu MCU timing jitter.
- Continue backlog guard for very old `process_move_push` entries.
- Ensure no descriptor with `print_time is None` enters scheduling min/max paths.

Acceptance:

- Fewer dispatch gaps around timing boundaries.
- No growth of stale backlog.
- No backward-time pin scheduling.

### Finding 4: Neutral-only refill fallback risk

Target:

- `extras/mmu/mmu_sync_feedback_manager.py`, `_get_sync_state_with_refill_fallback`

Implementation:

- Allow starvation-triggered virtual tension pulse from any sensed state (not only neutral), with guardrails:
  - Positive extruder move required.
  - Encoder movement below starvation threshold required.
  - Debounce/cooldown between forced pulses.
- Keep starvation event counting and reset behavior robust for noisy sensors.

Acceptance:

- Sticky tension/compression states do not block starvation recovery.
- Forced refill events are bounded and not spammy.

### Finding 5: Missing explicit encoder-reset hook

Target:

- `extras/mmu/mmu.py`, `_initialize_encoder`
- `extras/mmu/mmu_sync_feedback_manager.py`, new `note_encoder_reset(...)`

Implementation:

- Add manager hook method to reset/rebase refill fallback baseline and counters.
- Invoke hook immediately after encoder reset in MMU encoder initialization path.
- Keep hook safe when manager not yet initialized.

Acceptance:

- Encoder reset windows do not cause false starvation spikes or stale baseline use.
- First sync callback after reset behaves deterministically.

### Finding 6: Unsync drain-before-stop risk

Target:

- `extras/mmu/mmu_gear_bldc.py`, `_handle_unsynced`

Implementation:

- On unsync event, clear sync-origin queued motion descriptors immediately.
- Stop BLDC promptly instead of draining prior sync queue.
- Keep standalone non-sync moves unaffected.

Acceptance:

- No post-unsync dispatch of stale sync descriptors.
- Reduced cancel/end-of-print scheduler pressure.

## 5) Cross-Cutting Hardening

### Queue and scheduling invariants

Enforce and verify invariants:

- All queued descriptors used for scheduling have non-`None` `print_time`.
- Pin writes maintain monotonic print-time ordering.
- Sync descriptor coalescing cannot remove all near-future eligible descriptors.

### Runtime observability

Add structured debug logs (behind existing debug levels) for:

- Unsync immediate queue purge counts by source.
- Stale prune counts and grace window usage.
- Refill fallback trigger reason and cooldown suppression reason.
- Encoder reset hook invocation and baseline rebase events.

## 6) Recommended Tunables

Introduce/confirm conservative defaults:

- BLDC schedule margin floor: at least `0.10s` (consider `0.15s` if pressure persists).
- Refill fallback minimum pulse interval (new): `0.50s` default.
- Process-move coalescing horizon (new): `0.08s` to `0.15s` initial range.

All new tunables should have safe bounds and explicit comments.

## 7) Implementation Order

Phase 1 (state safety first):

- Fix cancel immediate unsync.
- Fix unsync immediate queue purge/stop.

Phase 2 (queue and timing hygiene):

- Replace queue replacement with bounded coalescing.
- Add stale grace pruning and invariant checks.

Phase 3 (fallback robustness):

- Remove neutral-only gating with debounce.
- Add encoder reset rebase hook and call path.

Phase 4 (instrumentation and tuning):

- Add logs and counters.
- Tune defaults from hardware runs.

## 8) Validation Plan (Hardware Required)

### Functional scenarios

1. Print start and purge transition:
- Verify no sustained tension state with extruder skipping.

2. Dense small-segment extrusion (skirt/brim style):
- Verify stable sync cadence and no queue starvation.

3. Cancel during active sync motion:
- Verify immediate unsync, no stale BLDC dispatch after cancel trigger.

4. Encoder reset and re-init windows:
- Verify no false refill storms or starvation blind spots.

5. End-of-print and error paths:
- Verify clean unsync and BLDC stop semantics.

### Log checks

Use mmu log grep checks for:

- `BLDC_PROCESS_MOVE`
- `BLDC_MOTION`
- `MmuSyncFeedbackManager: Forcing refill pulse`
- `unsynced` / queue purge logs
- `Timer too close`

Pass criteria:

- Zero MMU MCU timer-too-close in target scenarios.
- No long starvation windows (extruder move with near-zero encoder motion) without bounded recovery.

## 9) Risks and Mitigations

Risk: Over-aggressive coalescing hides necessary motion updates.
Mitigation: Keep narrow horizon, include speed threshold, and log dropped counts.

Risk: More permissive fallback creates pulse storms.
Mitigation: Enforce cooldown and event threshold; include suppression logging.

Risk: Immediate unsync on cancel alters expected macro side effects.
Mitigation: Keep wrapper command flow intact and validate macro behavior explicitly.

## 10) Exit Criteria

- All six findings have explicit code fixes merged.
- Hardware validation scenarios pass with no timer-too-close.
- No regression in normal load/unload/toolchange paths.
- Documentation updated for any added tunables and debug semantics.
