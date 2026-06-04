# PR-5 Work Order: Burst Enablement, Tuning Defaults, and Operator Docs

Date: 2026-06-04
PR slice: PR-5 from sync/refill execution checklist
Primary objective: Enable long-distance refill burst with validated conservative defaults and publish operational guidance.

## 1) Scope Lock

Only edit these files:

- printer_data/config/mmu/base/mmu_parameters.cfg
- docs/cfs.md
- docs/plans/2026-06-04-long-distance-refill-burst-plan.md
- optional link update in README.md if needed

Do not edit:

- motion logic code in extras/mmu/** (unless a blocking defect is discovered and moved to a separate hotfix PR)
- klipper/klippy/**
- klipper/src/**

## 2) Problem Statement

After PR-4 framework lands, production use requires:

- safe default enablement
- reproducible tuning workflow
- operator-visible troubleshooting and rollback guidance

## 3) Intended Behavior After PR-5

- Burst feature enabled with conservative tested values.
- Starvation windows reduced measurably in target scenarios.
- No timer-too-close regressions.
- Operators can tune safely and rollback quickly.

## 4) File-by-File Implementation Tasks

### A) printer_data/config/mmu/base/mmu_parameters.cfg

Required edits:

1. Enable burst flag for production profile.
2. Set validated conservative defaults for:
- burst distance
- burst strength
- starvation events threshold
- cooldown
- max active time
- optional min-speed gate
3. Add concise comments on expected impact and safe tuning order.
4. Add clearly marked rollback values.

### B) docs/cfs.md

Required edits:

1. Add section: long-distance refill burst behavior and intent.
2. Add tuning workflow:
- increase distance first, then strength
- hold cooldown initially
- stop criteria for oscillation/scheduler stress
3. Add troubleshooting signatures:
- starvation persists
- overfeed/compression oscillation
- scheduler pressure indicators
4. Add rollback procedure for quick disable.

### C) docs/plans/2026-06-04-long-distance-refill-burst-plan.md

Required edits:

1. Append final tuned values and rationale.
2. Record validation matrix outcomes.
3. Record residual risks and monitoring notes.

## 5) Non-Goals

Do not include in PR-5:

- new controller/manager algorithm changes
- queue/cancel/fallback bugfix changes from earlier PRs

## 6) Suggested Commit Message

Title:

config/docs: enable refill burst with tuned defaults and operator runbook

Body:

- enable long-distance refill burst using validated conservative values
- document tuning order, failure signatures, and rollback steps
- append measured outcomes to planning doc

## 7) Suggested PR Description Template

## Summary

This PR enables long-distance refill burst in production config and documents operational tuning/rollback guidance.

## Why

Moves feature from framework-only state to controlled production usage with reproducible operator workflow.

## Scope

Changed files:

- printer_data/config/mmu/base/mmu_parameters.cfg
- docs/cfs.md
- docs/plans/2026-06-04-long-distance-refill-burst-plan.md
- optional README link

Out of scope:

- core motion logic changes

## Validation Evidence

Attach:

1. scenario matrix results before/after enablement
2. final tuned parameter set
3. no Timer too close evidence
4. rollback demonstration

## Risk Assessment

Medium operational risk managed by conservative defaults and explicit rollback path.

## 8) Validation Script Outline (Hardware)

Run matrix:

1. purge-to-print handoff
2. dense small-segment extrusion
3. sustained moderate flow
4. low-flow false-trigger check
5. cancel/end transition safety check

Collect and compare:

- starvation duration/frequency
- scheduler faults (must remain zero)
- stability after burst completion

## 9) Log Review Checklist

Search for:

- refill burst lifecycle logs
- BLDC motion cadence markers
- Timer too close
- cancel/end transition markers

Pass criteria:

- starvation reduction is measurable and repeatable
- zero Timer too close
- no new load/unload/toolchange regressions

## 10) Reviewer Checklist

Reviewer should confirm:

1. Enabled defaults are conservative and evidence-backed.
2. Docs are sufficient for safe operator tuning.
3. Rollback values and procedure are explicit.
4. Scope is config/docs only.

## 11) Rollback Instructions

If production regressions appear:

1. Restore documented rollback values in mmu_parameters.cfg.
2. Disable burst feature switch.
3. Re-run baseline scenarios to confirm recovery.
4. Open follow-up tuning issue with attached logs.
