# PR-3 Work Order: Fallback Robustness and Encoder Reset Rebase

Date: 2026-06-04
PR slice: PR-3 from sync/refill execution checklist
Primary objective: Make starvation recovery robust across sensor states and reset fallback baselines correctly after encoder reset.

## 1) Scope Lock

Only edit these files:

- extras/mmu/mmu_sync_feedback_manager.py
- extras/mmu/mmu.py

Do not edit:

- extras/mmu/mmu_gear_bldc.py (except if strictly required for compile-level contract)
- extras/mmu/mmu_sync_controller.py
- klipper/klippy/**
- klipper/src/**

## 2) Problem Statement

Two correctness faults to close in this PR:

1. Neutral-only fallback gating:
- Starvation fallback can be blocked when sensor remains tension/compression.
- Result: no virtual refill pulse despite encoder under-motion.

2. Missing encoder reset hook:
- Fallback baseline may become stale/discontinuous after encoder reset.
- Result: false starvation triggers or blind spots.

## 3) Intended Behavior After PR-3

- Starvation-triggered virtual tension can be injected from non-neutral sensed states under strict criteria.
- Forced pulse behavior is debounced/cooldown-bounded.
- Encoder reset explicitly rebases fallback state and clears transient counters.
- No refill pulse storm during noisy windows.

## 4) File-by-File Implementation Tasks

### A) extras/mmu/mmu_sync_feedback_manager.py

Target functions/areas:

- _get_sync_state_with_refill_fallback
- sync init/reset paths
- new note_encoder_reset hook

Required edits:

1. Expand starvation trigger eligibility.
- Remove hard neutral-only requirement.
- Keep mandatory guards: positive extrusion move, encoder delta threshold, active synced BLDC context.

2. Add debounce/cooldown.
- Track timestamp of last forced pulse.
- Suppress retrigger until cooldown expires.
- Keep event counter behavior deterministic.

3. Add encoder reset rebase hook.
- Implement note_encoder_reset(eventtime=None, reason="") style helper.
- Reset/rebase fallback encoder baseline and starvation counters safely.

4. Add reason-tagged debug logs.
- trigger reason
- suppression reason
- reset/rebase event

Implementation guardrails:

- Preserve existing manager public contracts and command handlers.
- Keep logic inexpensive in high-frequency path.

### B) extras/mmu/mmu.py

Target function:

- _initialize_encoder

Required edits:

1. Call sync feedback manager encoder-reset hook after reset_counts path.
2. Guard call for manager availability.
3. Keep existing encoder dwell behavior unchanged.

## 5) Non-Goals

Do not include in PR-3:

- long-distance burst state machine (PR-4)
- config enablement/tuning defaults (PR-5)
- queue coalescing redesign (PR-2)

## 6) Suggested Commit Message

Title:

sync_feedback: robust starvation fallback and encoder-reset rebase hook

Body:

- allow starvation fallback from non-neutral states with strict guards
- add pulse debounce/cooldown to prevent refill storms
- rebase fallback baseline on encoder reset via mmu hook

## 7) Suggested PR Description Template

## Summary

This PR implements PR-3 robustness updates:

- starvation fallback no longer blocked by non-neutral sensor state
- forced refill pulses debounced via cooldown
- explicit encoder reset hook rebases fallback state

## Why

Prevents starvation recovery blind spots and post-reset transients that can destabilize sync behavior.

## Scope

Changed files:

- extras/mmu/mmu_sync_feedback_manager.py
- extras/mmu/mmu.py

Out of scope:

- long-distance burst feature (PR-4/5)

## Validation Evidence

Attach logs showing:

1. fallback trigger from non-neutral state under starvation
2. cooldown suppression of repeated trigger spam
3. encoder reset rebase event before next sync callback
4. no Timer too close

## Risk Assessment

Medium risk isolated to fallback decision path and encoder reset integration.

## 8) Validation Script Outline (Hardware)

Run sequence:

1. Reproduce known starvation-prone transition.
2. Exercise sticky tension/compression behavior.
3. Trigger encoder reset/reseed transition.
4. Run cancel/end transitions to ensure no pulse spillover.

Collect logs and verify:

- fallback recovers under non-neutral states
- cooldown limits trigger frequency
- post-reset baseline behaves deterministically
- no Timer too close

## 9) Log Review Checklist

Search for:

- Forcing refill pulse
- fallback suppression reason logs
- encoder reset rebase logs
- Timer too close

Pass criteria:

- bounded refill behavior
- deterministic first callback after encoder reset
- zero Timer too close in target runs

## 10) Reviewer Checklist

Reviewer should confirm:

1. Neutral-only gating no longer blocks valid recovery.
2. Cooldown is enforced and configurable with safe default.
3. Encoder reset hook call is correctly placed and guarded.
4. Scope remains PR-3 only.
5. Hardware evidence attached.

## 11) Rollback Instructions

If regressions appear:

1. Revert PR-3 commit.
2. Keep PR-1/PR-2 merged state.
3. Rework fallback thresholds/cooldown with additional logs.
