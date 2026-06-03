# Agent Instructions

This repository is a Creality CFS adaptation of Happy Hare. Read
`docs/ai-agent-onboarding.md` and `docs/cfs.md` before making CFS-related code,
configuration, or documentation changes.

## Priority Files

- `docs/cfs.md`
- `TODO.md`
- `printer_data/config/mmu/base/mmu_hardware.cfg`
- `printer_data/config/mmu/base/mmu_parameters.cfg`
- `printer_data/config/variables.cfg`
- `extras/mmu/mmu.py`
- `extras/mmu/mmu_gear_bldc.py`
- `extras/mmu_espooler.py`
- `utils/plot_bldc_pwm.py`

## Working Rules

- Start from the current printer config under `printer_data/config/` when it is
  available.
- Include `variables.cfg` in any calibration or behavior diagnosis.
- Use `codegraph` for code search. Make sure to run `codegraph sync` when changes have been made to the worktree.
- Preserve user-provided logs and configs. Do not clean or regenerate them
  unless explicitly asked.
- Do not revert unrelated worktree changes.
- For CFS movement bugs, inspect logs before proposing code changes.

## Common Debug Commands

```powershell
rg -n "BLDC_|ESPOOLER|MMU_TEST_MOVE|encoder|rotation_distance|sync_feedback" printer_data\logs\mmu.log
python utils\plot_bldc_pwm.py printer_data\logs\mmu.log
rg -n "encoder_bounded_bldc|bldc_encoder|_wrap_espooler|mmu_gear_bldc|VARS_MMU_BLDC_MAP" extras
```

