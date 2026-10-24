# Local AI Coding Evaluation — October 22, 2026

## Purpose

Evaluate a locally hosted AI coding model on GeoClimateBench's
Daily Temperature QC task.

These are exploratory results, not statistically reliable pass rates.

## Environment

- Model: Qwen2.5-Coder 3B
- Model runner: Ollama (local inference)
- Agent framework: Harbor 0.24.0, Terminus 2
- Hardware: NVIDIA GTX 1650 Max-Q, 4 GB VRAM
- Platform: Windows 10 and Docker Desktop
- Verification: Independent scientific tests in Docker

The Terminus 2 experiments used a temporary task copy with
additional terminal dependencies. The benchmark's scientific
requirements and verifier were not modified.

## Independent agent trials

| Trial | Maximum turns | Reward | Exceptions |
|---|---:|---:|---:|
| 2026-10-22__09-51-38 | 8 | 0.0 | 0 |
| 2026-10-22__10-06-02 | 20 | 0.0 | 0 |

Both trials failed to submit the required /app/solve.py.

Observed behaviors included incorrect file placement, incomplete
code generation, and unnecessary attempts to install packages
in a network-isolated environment.

Each configuration was run once.

## Direct code-generation experiment

Qwen was also asked to generate a solution directly from the
public Daily QC instructions, without the Terminus 2 agent.

Initial generations were truncated or repetitive.

A compact generation finished, but the code failed to execute
successfully and violated several scientific requirements:

- Temperature units were read from the wrong metadata location.
- UTC metadata was read incorrectly.
- Geographic coordinate checks were incorrect.
- Invalid temperature measurements were rejected instead of masked.
- Daily maxima were not calculated correctly per grid cell.
- Output variables did not match the required structure.

This original AI-generated solution did not pass verification.

## Human-assisted diagnostic repair

A separate copy of the generated program was corrected manually.

The assisted version passed the independent scientific verifier:

- Submitted NetCDF output validation
- Two unseen valid input cases
- Invalid-input rejection checks

Final verifier output:

ALL SCIENTIFIC CHECKS PASSED

This was a HUMAN-ASSISTED result, not an independent Qwen success.

## Interpretation

The local evaluation workflow successfully exposed coding and
scientific errors in an AI-generated solution.

These results do not establish the difficulty of GeoClimateBench
for larger models or provide reliable comparative pass rates.

The previously validated Oracle, Nop, and fault-injection
controls remain separate from these model experiments.

## Next milestone

Develop a third Harbor benchmark covering station-grid matching,
Haversine distance, observation exclusions, and error statistics.