# PR-4 Work Order: Long-Distance Refill Burst Core (Flag Off)

Date: 2026-06-04
PR slice: PR-4 from sync/refill execution checklist
Primary objective: Add long-distance refill burst machinery behind a feature flag with default-off behavior parity.

## 1) Scope Lock

Only edit these files:

- extras/mmu/mmu_sync_feedback_manager.py
- extras/mmu/mmu_sync_controller.py
- printer_data/config/mmu/base/mmu_parameters.cfg (defaults and comments only; feature disabled)

Do not edit:

- extras/mmu/mmu_gear_bldc.py
- cancel/unsync flow in extras/mmu/mmu.py
- klipper/klippy/**
- klipper/src/**

## 2) Problem Statement

Need a controlled resilience layer for prolonged starvation windows during synced BLDC print motion, without reintroducing scheduler pressure or pulse storms.

## 3) Intended Behavior After PR-4

- Burst framework exists but is disabled by default.
- With flag off: runtime behavior matches PR-3 baseline.
- With flag on (test only): burst state machine can arm/activate/cooldown with strict guards.
- All burst paths abort cleanly on unsync/cancel/error.

## 4) File-by-File Implementation Tasks

### A) extras/mmu/mmu_sync_feedback_manager.py

Target areas:

- fallback trigger pipeline
- burst bookkeeping and state transitions
- reset/abort integration paths

Required edits:

1. Add burst state machine fields.
- IDLE, ARMED, ACTIVE, COOLDOWN state tracking.
- timestamps/counters for arm, start, complete, cooldown.

2. Add trigger eligibility checks.
- synced BLDC active
- positive extrusion
- starvation threshold evidence
- not in cooldown
- feature flag enabled

3. Add abort paths.
- unsync, cancel, error, print-end transitions
- encoder reset rebase integration

4. Add burst status exposure where feasible.
- active flag
- remaining distance budget
- cooldown remaining

5. Add reason-tagged debug logs for full lifecycle.

### B) extras/mmu/mmu_sync_controller.py

Target areas:

- config object for burst parameters
- two-level pulse/budget integration
- _twolevel_rd_target behavior

Required edits:

1. Extend SyncControllerConfig with burst parameters and safe bounds.
2. Keep _twolevel_rd_target as single RD decision owner.
3. Ensure burst budget consumed only on positive d_ext.
4. Preserve budget across zero/retract ticks unless explicit abort.
5. Clamp through existing rd_min/rd_max envelope.

### C) printer_data/config/mmu/base/mmu_parameters.cfg

Required edits:

1. Add burst-related parameter entries with conservative defaults.
2. Keep feature disabled by default.
3. Add concise comments about safe tuning order.

## 5) Non-Goals

Do not include in PR-4:

- turning burst on in production defaults (PR-5)
- queue/cancel/fallback fixes already handled in PR-1..PR-3

## 6) Suggested Commit Message

Title:

sync_feedback: add long-distance refill burst framework (default off)

Body:

- add burst state machine and guarded trigger criteria
- extend controller config and pulse budget handling
- add config keys with conservative disabled defaults

## 7) Suggested PR Description Template

## Summary

This PR introduces long-distance refill burst core logic behind a default-off flag.

## Why

Provides a controlled path to recover prolonged starvation windows while preserving scheduler safety.

## Scope

Changed files:

- extras/mmu/mmu_sync_feedback_manager.py
- extras/mmu/mmu_sync_controller.py
- printer_data/config/mmu/base/mmu_parameters.cfg

Out of scope:

- enabling burst in production config (PR-5)

## Validation Evidence

Attach:

1. parity run with flag off (no behavior change)
2. test run with flag on showing state transitions
3. abort behavior on unsync/cancel/error
4. no Timer too close

## Risk Assessment

Medium/high risk isolated to feature-gated logic; mitigated by default-off rollout.

## 8) Validation Script Outline (Hardware)

Run sequence:

1. Baseline parity run with flag off.
2. Enable flag with conservative values.
3. Exercise starvation-prone purge-to-print and dense segment runs.
4. Trigger cancel/end transitions while burst eligible.

Collect logs and verify:

- correct state transitions and bounded cooldown
- clean abort behavior
- no scheduler faults

## 9) Log Review Checklist

Search for:

- refill burst armed/active/complete/suppressed
- BLDC_MOTION stability markers
- unsync/cancel abort markers
- Timer too close

Pass criteria:

- no change with feature flag off
- bounded behavior with flag on
- zero Timer too close in target runs

## 10) Reviewer Checklist

Reviewer should confirm:

1. Feature flag truly gates all burst behavior.
2. Flag-off path is behaviorally equivalent to PR-3.
3. Burst budget and cooldown constraints are enforced.
4. Controller remains sole RD target authority.
5. Scope remains limited to PR-4 files.

## 11) Rollback Instructions

If regressions appear:

1. Disable burst flag in config immediately.
2. Revert PR-4 commit if needed.
3. Preserve PR-1..PR-3 safety fixes.
