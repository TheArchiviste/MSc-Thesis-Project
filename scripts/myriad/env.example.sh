# Copy to work/myriad/env.sh. All paths must be absolute; keep this file private.
MYRIAD_ROOT="$HOME/Scratch/llmxcpg"
RUNTIME_SIF="$MYRIAD_ROOT/images/runtime.sif"
JOERN_SIF="$MYRIAD_ROOT/images/joern.sif"
MYRIAD_CONFIG="$MYRIAD_ROOT/config.json"
MYRIAD_HF_CACHE="$MYRIAD_ROOT/huggingface"
# Use a fresh work directory when scientific settings, source or code change.
EXPERIMENT_WORK="$MYRIAD_ROOT/results/main-001"
PROBE_WORK="$MYRIAD_ROOT/results/probe-001"
CALIBRATION_WORK="$MYRIAD_ROOT/results/calibration-001"
# Set these after the pilot and protocol freeze. Paths are inside /repo.
ANALYSIS_MANIFEST=/repo/corpus/cases.jsonl
CALIBRATION_MANIFEST=/repo/corpus/calibration_manifest.jsonl
REPEATS=1
# This deliberately changes the paper's context limit for the development probe.
# Choose and freeze a main-study value after checking source lengths and VRAM.
QUERY_MAX_CONTEXT=4096
QUERY_GPU_MEMORY_UTILIZATION=0.92
# Optional immutable OCI digest, otherwise prepare resolves v4.0.0 once.
JOERN_DIGEST=
# An independently recorded base SHA may be supplied; otherwise it is resolved
# once from the base named in the released adapter config and recorded.
DETECTOR_BASE_REVISION=
