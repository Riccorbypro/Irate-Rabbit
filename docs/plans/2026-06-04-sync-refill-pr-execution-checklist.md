# Sync + Refill Burst Execution Checklist (PR Slices)

Date: 2026-06-04
Status: Ready for implementation
Primary plans:
- `docs/plans/2026-06-04-sync-stability-fixes-plan.md`
- `docs/plans/2026-06-04-long-distance-refill-burst-plan.md`

## 1) Objective

Implement stability fixes first, then long-distance refill burst feature, using small reviewable PRs with strict merge gates.

## 2) PR Sequence and Dependency

- PR-1: Cancel/Unsync safety fixes (must merge first)
- PR-2: BLDC queue timing hardening (depends on PR-1)
- PR-3: Fallback + encoder reset robustness (depends on PR-2)
- PR-4: Long-distance refill burst core (feature-flagged, default off; depends on PR-3)
- PR-5: Enablement, tuning defaults, docs, and runbook (depends on PR-4)

No PR should include unrelated refactors.

## 3) PR-1 Checklist: Cancel/Unsync Safety

Title suggestion: `mmu: immediate unsync on cancel and hard stop on unsync`

### Files in scope

- `extras/mmu/mmu.py`
- `extras/mmu/mmu_gear_bldc.py`

### File-level tasks

- `extras/mmu/mmu.py`
- Update `cmd_MMU_CANCEL_PRINT` to unsync immediately before park/wrapper motion.
- Preserve existing macro ordering around `__CANCEL_PRINT` and end-state handling.
- Keep operation idempotent if already unsynced.

- `extras/mmu/mmu_gear_bldc.py`
- Update `_handle_unsynced` to clear sync-origin queued motion descriptors immediately.
- Stop BLDC promptly after unsync instead of draining old sync queue.
- Ensure standalone non-sync motion path is unchanged.

### Acceptance gates (must pass before merge)

- Functional:
- Cancel during active synced extrusion shows no post-unsync `BLDC_MOTION source=process_move_push` dispatch.
- End-of-print and error paths still complete and leave BLDC stopped.

- Safety:
- No `Timer too close` in cancel stress runs.

- Regression:
- Normal load/unload/toolchange sequences still complete without new faults.

### Log evidence required in PR description

- Before/after snippets for cancel path showing unsync point.
- Proof of no stale sync dispatch after unsync.
- Statement of unchanged standalone move behavior.

## 4) PR-2 Checklist: BLDC Queue Timing Hardening

Title suggestion: `mmu_gear_bldc: coalesce process_move queue and add stale grace pruning`

### Files in scope

- `extras/mmu/mmu_gear_bldc.py`

### File-level tasks

- `extras/mmu/mmu_gear_bldc.py`
- Replace queue-wide deletion of `process_move_push` descriptors with bounded coalescing.
- Keep recent/near-term descriptors; prune only old near-duplicates by time and speed tolerance.
- Replace strict stale prune edge with configurable stale grace window.
- Preserve backlog guard for very old `process_move_push` entries.
- Enforce scheduling invariants so descriptors with `print_time is None` do not enter scheduling min/max decisions.
- Add bounded debug logging counters for coalesced/pruned descriptors.

### Acceptance gates (must pass before merge)

- Functional:
- Dense small-segment extrusion keeps `BLDC_MOTION source=process_move_push` cadence stable.
- Queue depth remains bounded and no starvation windows appear from queue handling.

- Safety:
- No backward-time pin scheduling symptoms.
- No `Timer too close` introduced in dense process_move scenarios.

- Regression:
- Standalone BLDC motion and normal sync tracking remain behaviorally equivalent.

### Log evidence required in PR description

- Coalescing/prune counters from dense run.
- Proof that motion dispatch cadence remains present under load.

## 5) PR-3 Checklist: Fallback Robustness + Encoder Reset Hook

Title suggestion: `sync_feedback: robust starvation fallback with encoder-reset rebase`

### Files in scope

- `extras/mmu/mmu_sync_feedback_manager.py`
- `extras/mmu/mmu.py`

### File-level tasks

- `extras/mmu/mmu_sync_feedback_manager.py`
- Update `_get_sync_state_with_refill_fallback(...)` to allow starvation-triggered virtual tension from non-neutral states.
- Add debounce/cooldown for forced refill events.
- Add/maintain starvation and recovery counters with explicit reset points.
- Add `note_encoder_reset(...)` hook to rebase fallback baseline and clear transient state.

- `extras/mmu/mmu.py`
- Call `sync_feedback_manager.note_encoder_reset(...)` after encoder reset in `_initialize_encoder` path.
- Keep call guarded for manager availability and MMU state.

### Acceptance gates (must pass before merge)

- Functional:
- Sticky tension/compression no longer blocks starvation recovery.
- First sync callback after encoder reset is stable and deterministic.

- Safety:
- Forced refill events are bounded by cooldown and do not spam.
- No `Timer too close` introduced by fallback behavior.

- Regression:
- Existing sync-feedback behavior remains unchanged when starvation condition is not present.

### Log evidence required in PR description

- Forced pulse trigger and suppression examples.
- Encoder reset hook log and baseline rebase confirmation.

## 6) PR-4 Checklist: Long-Distance Refill Burst Core (Feature Flag Off)

Title suggestion: `sync_feedback: add long-distance refill burst state machine (disabled by default)`

### Files in scope

- `extras/mmu/mmu_sync_feedback_manager.py`
- `extras/mmu/mmu_sync_controller.py`
- `printer_data/config/mmu/base/mmu_parameters.cfg` (or equivalent config source used for defaults)

### File-level tasks

- `extras/mmu/mmu_sync_feedback_manager.py`
- Add burst state tracking: idle/armed/active/cooldown metadata.
- Add trigger criteria evaluation using starvation evidence and cooldown.
- Add burst abort conditions for unsync/cancel/error/print-end transitions.
- Expose burst status fields for diagnostics if status path allows.

- `extras/mmu/mmu_sync_controller.py`
- Extend controller config with long-burst parameters and validation.
- Keep `_twolevel_rd_target(...)` as single RD decision owner.
- Ensure burst budget consumption only on positive extrusion deltas.
- Preserve pulse budget across zero/retract ticks unless explicit abort reason occurs.

- `printer_data/config/mmu/base/mmu_parameters.cfg`
- Add guarded default parameters for burst distance/strength/events/cooldown/max-active-time/min-speed.
- Keep defaults conservative and feature disabled by default.

### Acceptance gates (must pass before merge)

- Functional:
- With feature flag off, behavior is unchanged from PR-3 baseline.
- State machine transitions are correct in logs when feature is enabled for test.

- Safety:
- Cooldown and max-active-time limits are enforced.
- No burst activity occurs after unsync/cancel/error begins.

- Regression:
- No performance degradation in non-starvation print phases.

### Log evidence required in PR description

- Burst armed/active/complete/suppressed samples.
- Explicit statement proving no-change behavior with flag off.

## 7) PR-5 Checklist: Controlled Enablement and Tuning Runbook

Title suggestion: `docs/config: enable long-distance refill burst with tuned defaults`

### Files in scope

- `printer_data/config/mmu/base/mmu_parameters.cfg`
- `docs/cfs.md`
- `docs/plans/2026-06-04-long-distance-refill-burst-plan.md` (append final tuning outcomes)
- Optional: `README.md` section link if needed

### File-level tasks

- `printer_data/config/mmu/base/mmu_parameters.cfg`
- Enable burst feature with conservative initial values.
- Record tuned values and rationale comments.

- `docs/cfs.md`
- Add operator guidance: symptoms, parameters, safe tuning order, rollback values.
- Add troubleshooting signatures for overfeed oscillation vs starvation persistence.

- `docs/plans/2026-06-04-long-distance-refill-burst-plan.md`
- Append final validated defaults and acceptance summary.

### Acceptance gates (must pass before merge)

- Functional:
- Measurable reduction in starvation duration/frequency on target scenarios.

- Safety:
- No timer-too-close regressions in all validation scenarios.
- No persistent compression/overfeed oscillation after burst completion.

- Regression:
- No degradation in load/unload/toolchange reliability.

### Evidence required in PR description

- Scenario matrix results and final tuned values.
- Clear rollback values and disable switch.

## 8) Common Verification Commands (for every PR touching motion)

- Search MMU logs for key signals:
- `BLDC_PROCESS_MOVE`
- `BLDC_MOTION`
- `Forcing refill pulse`
- `refill_burst_` state logs
- `unsynced`
- `Timer too close`

- Plot PWM traces when needed:
- `utils/plot_bldc_pwm.py` against latest `klippy.log`/`mmu.log` capture.

## 9) Non-Negotiable Merge Policy

- Do not merge a PR lacking required hardware evidence for its scope.
- Do not combine multiple PR scopes to "save time".
- Do not enable long-distance burst by default before PR-1/2/3 are merged and validated.
- Any timer-too-close reappearance blocks merge until root cause is proven and fixed.

## 10) Rollback Plan

- PR-1/2/3 regressions: revert offending PR immediately; keep earlier merged safety PRs if unaffected.
- PR-4 regressions: disable burst feature flag and keep code in place for debugging.
- PR-5 regressions: revert tuned enablement values to conservative disabled baseline.

## 11) Definition of Done (Program Level)

All items below must be true:

- PR-1 through PR-5 merged in order.
- No MMU timer-too-close in validation matrix.
- Starvation recovery improved with burst enabled and bounded.
- Cancel/end/error paths remain safe and deterministic.
- Docs include tuning and rollback guidance for operators.
