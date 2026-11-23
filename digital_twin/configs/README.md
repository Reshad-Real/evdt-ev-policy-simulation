# Configuration

The model is configured in code rather than in external files, because every
parameter carries a unit, a provenance note and a type. The authoritative
definitions are:

| What | Where |
|---|---|
| Power-semiconductor devices | `evdt/config.py` → `DEVICE_LIBRARY` |
| Battery chemistries | `evdt/config.py` → `BATTERY_LIBRARY` |
| Vehicle segments | `evdt/config.py` → `VEHICLE_LIBRARY` |
| Charging equipment classes | `evdt/config.py` → `CHARGER_LIBRARY` |
| Distribution feeder | `evdt/config.py` → `FeederConfig` |
| Country archetypes | `evdt/scenarios.py` → `UNDERDEVELOPED`, `DEVELOPING`, `DEVELOPED` |
| Policy levers | `evdt/policy.py` → `LEVERS` |
| Policy packages | `evdt/scenarios.py` → `_UD`, `_DG`, `_DV` |
| Switching frequencies | `evdt/powerelectronics.py` → `FREQUENCY_MAP` |
| Indicator set and weights | `evdt/metrics.py` → `INDICATORS` |
| Uncertain parameters | `evdt/uncertainty.py` → `UNCERTAIN` |
| Run seeds and sample sizes | the `run_*.py` scripts |

Every run archives the complete resolved configuration to
`results/model_configuration.json`, which contains the full device, battery,
vehicle, charger and feeder libraries, all three archetype definitions, the
simulation horizon and the random seed. That file — not this directory — is the
record of what a given set of results was produced from.

`generated/` holds the archived configuration of the most recent run, copied
here by `run_deterministic.py` for convenience.
