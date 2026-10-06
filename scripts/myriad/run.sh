#!/bin/bash
# Called from gpu.sge or cpu.sge. Never launch model phases on login nodes.
set -euo pipefail
: "${JOB_ID:?Use qsub, not bash, to launch this script}"
: "${TMPDIR:?The job must request tmpfs}"
phase="${1:?Choose doctor, probe, verify, validate, query, slice, score-calibration, detect, packets or analyze}"
shift
case "$phase" in
    doctor|probe|verify|validate|query|slice|score-calibration|detect|packets|analyze) ;;
    *) echo "Unsupported phase: $phase" >&2; exit 2 ;;
esac
source work/myriad/env.sh
module load apptainer
export APPTAINER_TMPDIR="$TMPDIR"
export APPTAINER_CACHEDIR="$MYRIAD_ROOT/apptainer-cache"
export APPTAINERENV_HF_HOME="$MYRIAD_HF_CACHE"
export APPTAINERENV_HF_HUB_OFFLINE=1
export APPTAINERENV_TRANSFORMERS_OFFLINE=1
export APPTAINERENV_OMP_NUM_THREADS="${NSLOTS:-1}"
export APPTAINERENV_JOB_ID="$JOB_ID"
export APPTAINERENV_VLLM_WORKER_MULTIPROC_METHOD=spawn
gpu=()
case "$phase" in
    doctor|probe|query|score-calibration|detect)
        : "${CUDA_VISIBLE_DEVICES:?Scheduler GPU mask missing; ask UCL support before running models}"
        export APPTAINERENV_CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES"
        gpu=(--nv)
        ;;
esac
work="$EXPERIMENT_WORK"
[[ "$phase" == probe || "$phase" == doctor ]] && work="$PROBE_WORK"
[[ "$phase" == score-calibration ]] && work="$CALIBRATION_WORK"
mkdir -p "$work/jobs/$JOB_ID" "$TMPDIR/llmxcpg-inputs" "$TMPDIR/llmxcpg-joern"
logdir="$work/jobs/$JOB_ID"
exec 9>"$work/writer.lock"
flock -n 9 || { echo "Another job is writing to $work" >&2; exit 1; }
sha256sum --check "$MYRIAD_ROOT/images/SHA256SUMS" > "$logdir/images.log"
runtime=(apptainer exec --cleanenv "${gpu[@]}" --bind "$PWD:/repo" \
    --bind "$MYRIAD_ROOT:$MYRIAD_ROOT" --bind "$TMPDIR/llmxcpg-inputs:/analysis/inputs" "$RUNTIME_SIF")
# Loopback plus a fresh port permits several independent jobs on one node.
port=$("${runtime[@]}" python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
config="$logdir/config.json"
render=(python /repo/scripts/myriad/manage.py render --config "$MYRIAD_CONFIG" --output "$config" --port "$port")
[[ "$phase" == doctor || "$phase" == probe ]] && render+=(--probe)
[[ "$phase" == detect ]] && render+=(--calibration "$CALIBRATION_WORK/calibration.json")
"${runtime[@]}" "${render[@]}"
# Compare the config's runtime identity too, so a replaced image cannot silently
# reuse locks even if someone regenerated SHA256SUMS.
"${runtime[@]}" python -c 'import json,sys; from scripts.myriad.manage import sha256; from pathlib import Path; c=json.load(open(sys.argv[1])); p=json.load(open(sys.argv[3])); assert c["runtime_image_sha256"]==sha256(Path(sys.argv[2]))==p["runtime_sha256"], "Runtime differs from frozen config"; assert c["joern_digest"]==p["joern_digest"], "Joern digest differs from prepared image"' "$config" "$RUNTIME_SIF" "$MYRIAD_ROOT/images/provenance.json"
joern_pid=
cleanup() {
    status=$?
    trap - EXIT
    if [[ -n "$joern_pid" ]]; then kill "$joern_pid" 2>/dev/null || true; wait "$joern_pid" 2>/dev/null || true; fi
    printf '%s\n' "$status" > "$logdir/exit_code"
    if [[ "$status" == 0 ]]; then printf '%s\n' "$JOB_ID" > "$work/$phase.completed"; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
if [[ "$phase" == doctor || "$phase" == probe || "$phase" == slice || "$phase" == score-calibration ]]; then
    apptainer exec --cleanenv --pwd /workspace \
        --bind "$TMPDIR/llmxcpg-joern:/workspace" \
        --bind "$TMPDIR/llmxcpg-inputs:/analysis/inputs:ro" \
        "$JOERN_SIF" env JAVA_TOOL_OPTIONS=-Xmx16g \
        joern --server --server-host 127.0.0.1 --server-port "$port" \
        > "$logdir/joern.log" 2>&1 &
    joern_pid=$!
    "${runtime[@]}" python /repo/scripts/myriad/manage.py wait-joern --port "$port"
    check=(python /repo/scripts/myriad/manage.py doctor --config "$config")
    [[ "${#gpu[@]}" -gt 0 ]] && check+=(--gpu)
    "${runtime[@]}" "${check[@]}" > "$logdir/doctor.json"
fi
if [[ "$phase" == query || "$phase" == detect ]]; then
    "${runtime[@]}" python /repo/scripts/myriad/manage.py doctor --config "$config" \
        --gpu --without-joern > "$logdir/doctor.json"
fi
case "$phase" in
    doctor) cat "$logdir/doctor.json" ;;
    probe)
        "${runtime[@]}" python /repo/juliet_pilot/prepare.py
        "${runtime[@]}" python /repo/juliet_pilot/real_probe.py --config "$config" \
            --work "$work" --include-fixed-controls "$@"
        ;;
    *)
        options=(--manifest "$ANALYSIS_MANIFEST" --config "$config" --work "$work" --repeats "${REPEATS:-1}")
        [[ "$phase" == score-calibration ]] && options+=(--calibration-manifest "$CALIBRATION_MANIFEST")
        [[ "$phase" == detect ]] && options+=(--calibration "$CALIBRATION_WORK/calibration.json")
        "${runtime[@]}" python -m evidence_experiment "$phase" "${options[@]}" "$@"
        ;;
esac
