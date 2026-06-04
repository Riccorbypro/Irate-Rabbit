# PR-2 Work Order: BLDC Queue Timing Hardening

Date: 2026-06-04
PR slice: PR-2 from sync/refill execution checklist
Primary objective: Prevent BLDC sync starvation and timing-edge losses by hardening process-move queue handling.

## 1) Scope Lock

Only edit these files:

- extras/mmu/mmu_gear_bldc.py

Do not edit:

- extras/mmu/mmu.py
- extras/mmu/mmu_sync_feedback_manager.py
- extras/mmu/mmu_sync_controller.py
- config defaults (except comments if strictly necessary)
- klipper/klippy/**
- klipper/src/**

## 2) Problem Statement

Two queue/timing faults to close in this PR:

1. Process-move queue replacement starvation:
- New process_move_push can replace/drop previously queued sync descriptors too aggressively.
- Result: BLDC can under-dispatch relative to extruder motion.

2. Strict stale-prune timing edge:
- Tight stale cutoffs can remove still-relevant descriptors at scheduler boundary.
- Result: dispatch holes and unstable sync cadence.

## 3) Intended Behavior After PR-2

- Process-move descriptors are coalesced, not wholesale replaced.
- Queue remains bounded under dense segment streams.
- Stale pruning uses grace window suitable for mmu MCU jitter.
- Scheduling invariants hold and dispatch cadence remains steady.

## 4) File-by-File Implementation Tasks

### A) extras/mmu/mmu_gear_bldc.py

Target functions/areas:

- queue_trapzoid_move
- _motion_timer_callback
- queue invariants/helpers

Required edits:

1. Replace full process_move_push queue replacement with bounded coalescing.
- Keep near-term descriptors.
- Drop only old near-duplicates by time and speed tolerance.
- Preserve ordering by print_time.

2. Add stale grace pruning.
- Replace strict stale cutoff with configurable grace window.
- Continue backlog guard for very old process_move_push entries.

3. Maintain scheduling safety invariants.
- Exclude descriptors with print_time=None from min/max scheduling decisions.
- Keep timer callback robust under mixed descriptor states.

4. Add bounded debug telemetry.
- Coalesced count.
- Stale-pruned count.
- Backlog-guard-pruned count.

Implementation guardrails:

- No redesign of full motion state machine in this PR.
- No behavior changes to standalone move mode beyond invariant safety.
- Keep existing log style and verbosity gating.

## 5) Non-Goals

Do not include in PR-2:

- cancel unsync ordering changes (PR-1)
- fallback/debounce logic (PR-3)
- encoder reset hook (PR-3)
- long-distance refill burst state machine (PR-4)
- feature enablement/tuning defaults (PR-5)

## 6) Suggested Commit Message

Title:

mmu_gear_bldc: coalesce process_move queue and add stale grace pruning

Body:

- replace process_move queue replacement with bounded coalescing
- add stale grace window and preserve backlog guard
- enforce descriptor scheduling invariants and add debug counters

## 7) Suggested PR Description Template

## Summary

This PR implements PR-2 queue/timing hardening:

- bounded coalescing for process_move_push descriptors
- stale grace pruning to avoid timing-edge descriptor loss
- queue scheduling invariants for robust dispatch

## Why

Fixes starvation and timing-boundary issues that can cause BLDC under-dispatch and instability in dense process_move traffic.

## Scope

Changed files:

- extras/mmu/mmu_gear_bldc.py

Out of scope:

- fallback robustness and encoder reset handling (PR-3)
- refill burst feature (PR-4/5)

## Validation Evidence

Attach log snippets for:

1. dense segment run
- stable BLDC_MOTION source=process_move_push cadence

2. queue hygiene
- bounded coalescing and stale prune counters

3. scheduler safety
- no Timer too close and no dispatch gaps

## Risk Assessment

Medium risk to queue selection/pruning behavior only; isolated to BLDC queue path.

## 8) Validation Script Outline (Hardware)

Run sequence:

1. Execute dense small-segment extrusion scenario.
2. Execute moderate continuous flow scenario.
3. Repeat with cancel near high descriptor density.

Collect logs and verify:

- BLDC_MOTION process_move cadence remains present
- coalescing/pruning bounded and not over-aggressive
- no Timer too close

## 9) Log Review Checklist

Search for:

- BLDC_PROCESS_MOVE
- BLDC_MOTION: source=process_move_push
- coalesce/prune debug counters
- Timer too close

Pass criteria:

- steady dispatch in dense runs
- no starvation windows caused by queue logic
- zero Timer too close in targeted runs

## 10) Reviewer Checklist

Reviewer should confirm:

1. No wholesale replacement of process_move queue remains.
2. Grace-based stale pruning is bounded and safe.
3. Invariants prevent None-time scheduling hazards.
4. Scope is isolated to BLDC queue file only.
5. Hardware log evidence is sufficient.

## 11) Rollback Instructions

If regressions appear:

1. Revert PR-2 commit.
2. Re-run PR-1 baseline scenario.
3. Adjust coalescing/grace thresholds in follow-up only after evidence.
