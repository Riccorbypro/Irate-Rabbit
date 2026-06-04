# PR-1 Work Order: Cancel/Unsync Safety Hardening

Date: 2026-06-04
PR slice: PR-1 from sync/refill execution checklist
Primary objective: Remove cancel/unsync race windows that keep BLDC sync motion alive after cancel/unsync starts.

## 1) Scope Lock

Only edit these files:

- extras/mmu/mmu.py
- extras/mmu/mmu_gear_bldc.py

Do not edit:

- klipper/klippy/**
- klipper/src/**
- extras/mmu/mmu_sync_controller.py
- config defaults (this PR is behavior safety, not tuning)

## 2) Problem Statement

Two high-severity risks to close in this PR:

1. Cancel path ordering risk:
- MMU cancel currently parks/wraps before explicit unsync in end-state path.
- Result: sync callbacks may continue dispatching BLDC motion during cancel transition.

2. Unsync drain-before-stop risk:
- BLDC unsync handler can defer stop while queued sync descriptors drain.
- Result: stale sync-origin motion can execute after unsync intent.

## 3) Intended Behavior After PR-1

- Cancel should unsync immediately before any cancel park/wrapper motion begins.
- Unsync should immediately prevent further sync-origin dispatch and stop BLDC promptly.
- Standalone non-sync motion semantics remain unchanged.
- User-facing cancel macro behavior remains intact.

## 4) File-by-File Implementation Tasks

### A) extras/mmu/mmu.py

Target function:

- cmd_MMU_CANCEL_PRINT

Required edits:

1. Insert immediate unsync step at the top of enabled cancel path, before park/wrapper call.
2. Keep idempotence:
- If already unsynced, unsync call must no-op safely.
3. Preserve existing flow:
- keep _fix_started_state
- keep dialog cleanup
- keep __CANCEL_PRINT wrapper call
- keep _on_print_end("cancelled")
4. Do not change external command names or wrapper command identity.

Implementation guardrails:

- Do not alter behavior when MMU is disabled.
- Do not move or remove user macro wrapper call.
- Do not introduce new config keys in this PR.

### B) extras/mmu/mmu_gear_bldc.py

Target function:

- _handle_unsynced

Required edits:

1. On unsync, clear queued sync-origin descriptors immediately.
- Sync-origin means queue entries from sync callback sources.
- Keep non-sync standalone descriptors untouched unless stop path already requires full clear.
2. Do not return early to drain sync queue.
3. Stop BLDC promptly after purge decision.
4. Keep monitor deactivate behavior intact.

Implementation guardrails:

- Preserve logging style and existing debug level conventions.
- Preserve sync monitor activation/deactivation contracts.
- Do not introduce timer-loop redesign in this PR.

## 5) Non-Goals

Do not include in PR-1:

- process_move coalescing redesign
- stale grace prune logic changes
- fallback debounce or burst logic
- encoder reset hook wiring
- config tuning changes

Those belong to PR-2 and PR-3+.

## 6) Suggested Commit Message

Title:

mmu: unsync immediately on cancel and stop sync queue on unsync

Body:

- unsync MMU before cancel park/wrapper movement to prevent stale sync dispatch
- clear sync-origin queued BLDC motion on unsync and stop promptly
- preserve standalone motion and existing cancel macro flow

## 7) Suggested PR Description Template

## Summary

This PR implements PR-1 safety hardening:

- immediate unsync at cancel entry before park/wrapper motion
- immediate sync-origin queue purge and stop behavior on unsync

## Why

Fixes high-severity race windows where BLDC sync motion can continue after cancel/unsync intent, increasing risk of tension and scheduler pressure.

## Scope

Changed files:

- extras/mmu/mmu.py
- extras/mmu/mmu_gear_bldc.py

Out of scope:

- queue coalescing and stale grace (PR-2)
- fallback and encoder-reset robustness (PR-3)
- long-distance burst feature (PR-4/5)

## Validation Evidence

Attach log snippets for:

1. cancel during active sync:
- no BLDC_MOTION source=process_move_push after unsync point

2. unsync transition:
- queue purge and stop occurs immediately

3. scheduler safety:
- no Timer too close in cancel stress runs

## Risk Assessment

Low/medium risk to cancel transition ordering and unsync flow only.
Standalone motion and non-cancel print behavior intentionally preserved.

## 8) Validation Script Outline (Hardware)

Run sequence (manual/hardware):

1. Start scenario with active synced extrusion (known to produce process_move callbacks).
2. Trigger MMU cancel while synced motion is active.
3. Repeat cancel test multiple times under dense motion conditions.

Collect logs and verify:

- no post-unsync sync-origin BLDC motion dispatch
- unsync path reports immediate stop behavior
- no MMU Timer too close fault

## 9) Log Review Checklist

Search for:

- BLDC_SYNC: unsynced
- BLDC_MOTION: source=process_move_push
- MMU_CANCEL_PRINT wrapper called
- Timer too close

Pass criteria:

- zero sync-origin dispatch after unsync event in cancel run
- zero Timer too close in target runs

## 10) Reviewer Checklist

Reviewer should confirm:

1. Cancel flow still calls wrapper macro exactly once.
2. Immediate unsync happens before park/wrapper motion.
3. Unsync path does not drain stale sync queue.
4. No unrelated behavior or config changes included.
5. Log evidence is attached and sufficient.

## 11) Rollback Instructions

If regressions appear:

1. Revert PR-1 commit.
2. Re-run baseline cancel scenario to confirm regression source.
3. Keep execution checklist sequence intact before attempting rework.
