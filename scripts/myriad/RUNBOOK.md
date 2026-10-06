# Run the dissertation on UCL Myriad

Reviewed against UCL's public documentation on 6 October 2026. These are
prepared job templates, not evidence of a successful run on your account.
Your allocation, queue access, drivers and available modules are verified by
the first scheduled doctor job.

## Cluster decision

| Service | Fit for this experiment | Decision |
| --- | --- | --- |
| Myriad U/V | A100 80 GB, single-node jobs, general-purpose access, Joern and Q on one node | Primary choice: one GPU per job |
| Myriad L | A100 40 GB | Insufficient for the current single-GPU unquantized 32B Q probe; using two GPUs requires a separately recorded configuration |
| Myriad E/F | V100; older GPU architecture | Does not satisfy this probe's BF16/VRAM checks |
| Kathleen | Designed for MPI and multi-node work; currently RHEL9/Slurm | No benefit for this single-node pipeline |
| Young | Materials/modelling access; A100 40 GB nodes, migration to Slurm on Young-ng | Possible alternative with approved access and multi-GPU setup; extra complexity for this dissertation |

This is a workload recommendation, not a claim that U/V currently has the
shortest queue. There are only three documented U/V nodes. Start with one
pilot, then inspect queue waits and measured runtime before scaling.

Myriad uses **Grid Engine** (`qsub`, `qstat`), whereas the newer Kathleen and
Young-ng services use Slurm. Do not submit these scripts with `sbatch`.
The GPU template requests `gpu=1`, `allow=UV`, 16 cores, **8 GB per core**
(128 GB total), 50 GB job-local storage and four hours. The CPU template
requests eight cores and 32 GB total. Preparation requests eight cores,
64 GB total and 200 GB job-local storage. These are initial requests; revise
wall time and resources using measured job usage, below Myriad's 48-hour
multicore limit.

Sources: [Myriad](https://www.rc.ucl.ac.uk/docs/Clusters/Myriad/),
[job requests](https://www.rc.ucl.ac.uk/docs/Experienced_Users/),
[Apptainer](https://www.rc.ucl.ac.uk/docs/Software_Guides/Singularity/),
[Kathleen](https://www.rc.ucl.ac.uk/docs/Clusters/Kathleen/),
[Young](https://www.rc.ucl.ac.uk/docs/Clusters/Young/).

## 1. Log in and obtain a full checkout

From your computer, using UCL VPN or the documented SSH gateway if necessary:

```bash
ssh YOUR_UCL_USERNAME@myriad.rc.ucl.ac.uk
mkdir -p ~/Scratch
cd ~/Scratch
git clone https://github.com/TheArchiviste/MSc-Thesis-Project.git
cd MSc-Thesis-Project
# Before this PR is merged, switch to the branch containing this runbook.
git switch codex/myriad-experiment-readiness
git rev-parse HEAD
git diff --exit-code 7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b -- llmxcpg/prompts.py llmxcpg/inference/query_generator.py llmxcpg/joern llmxcpg/slicing
gquota
mkdir -p work/myriad
cp scripts/myriad/env.example.sh work/myriad/env.sh
```

After merge, use `main` instead of the PR branch. Avoid shallow clones: the
experiment must be able to verify the original Q/Joern code pin. Capture the
actual dissertation checkout SHA as well. Submit all jobs from this repository
root, and keep the checkout unchanged while a run is queued or running.

Edit `work/myriad/env.sh` if storage paths differ. The initial 4096-token Q
context is a **development configuration change** from the paper's 32768,
recorded in each run. It is not truncation: oversized prompts fail closed.
Choose the main-study context after inspecting source lengths and pilot VRAM,
then freeze it before acquiring main evidence or calibrating D. The main
config intentionally has no threshold until calibration supplies one.

## 2. Prepare the images and model cache in a scheduled CPU job

```bash
qsub scripts/myriad/prepare.sge
qstat -u "$USER"
```

Wait for the job to finish and check its `.oJOB_ID` and `.eJOB_ID` files in the
repository root. The successful output says `Preparation complete`. Then:

```bash
source work/myriad/env.sh
cat "$MYRIAD_CONFIG"
cat "$MYRIAD_ROOT/images/provenance.json"
sha256sum --check "$MYRIAD_ROOT/images/SHA256SUMS"
gquota
```

Preparation builds a Python 3.11 inference SIF with the candidate pinned
runtime, checks pip dependency consistency, resolves Joern v4.0.0 to an OCI
digest, pulls that digest into a separate SIF, and downloads the released Q,
D adapter and D base at immutable revisions. It obtains the base name from
the released adapter rather than guessing it. Set `DETECTOR_BASE_REVISION`
before preparation if you already have an independently established base pin;
otherwise the current base revision is resolved once and recorded. This does
not establish which base revision was used during original training.

The SIF checksum and retained `pip-freeze.txt` freeze transitive dependencies
for the actual run. The build recipe is a candidate until the GPU doctor and
pilot pass; wheel and driver compatibility cannot be established locally.
Use the same images for acquisition, calibration and detection. Main jobs run
with the Hugging Face cache offline, so missing weights fail before inference.

Allow roughly **250–350 GB free quota** initially for models, images, package
caches and outputs; actual use depends on repository files and caching. Do
not download weights or build images on login nodes. If compute-node outbound
downloads are restricted for your account, prepare these same images and
snapshots elsewhere and transfer them with `rsync`; preserve their checksums
and recorded revisions. No host `sudo` or Docker daemon is required. UCL
documents `apptainer build --fakeroot`; if it is unavailable on the selected
node, build the SIF on another permitted machine and transfer it.

A failed build may leave `.partial` files. Inspect the error before removing
only those incomplete files and resubmitting. Existing complete images and
configs are retained by preparation. To change the runtime, use a new
`MYRIAD_ROOT`, config and experiment directories.

## 3. Run the allocation, CUDA and Joern checks

```bash
qsub scripts/myriad/gpu.sge doctor
```

Inspect `$PROBE_WORK/jobs/JOB_ID/doctor.json`, `joern.log`, `images.log` and
`exit_code`. Success requires exit code zero and `$PROBE_WORK/doctor.completed`.
The check verifies the original pipeline pin, exactly one visible assigned
GPU with at least 70 GiB VRAM and BF16, an actual BF16 CUDA operation, native
model-library imports, and a C source import/query through the Joern mount.

The wrapper preserves the scheduler's `CUDA_VISIBLE_DEVICES` inside
Apptainer. Public UCL documentation does not specify the mask implementation.
If it is missing or more than one device is visible, the job stops: ask UCL
support how assigned devices are exposed in your account. Do not guess a GPU
ID or expose all four GPUs for a one-GPU request. The doctor result is the
first live resource evidence; a public hardware listing alone is insufficient.

Joern listens on loopback at a fresh port and uses a private `$TMPDIR` workspace
per job. Both containers see staged source at `/analysis/inputs`; Joern's mount
is read-only. The wrapper removes the server on completion or termination.
Do not expose a shared Joern server over the network or share one mutable
workspace between workers.

## 4. Run the four-case development probe

```bash
qsub scripts/myriad/gpu.sge probe
```

Expected: four original cases, each queried three times, plus one fixed decoy
per case: **16 query rows and 16 slice rows**. Inspect `probe_summary.json`,
`probe_readouts.json`, raw query/slice JSONL and retained Joern errors. The
summary must say `research_results: false`, `detector_executed: false` and
`adequacy_assessed: false`. Query/slice failures remain observations rather
than being replaced by fabricated successes.

You can test infrastructure and mechanical coverage while human review is
deferred. Evidence adequacy and final RQ1/RQ2 estimates still require the
specified independent ratings and referent adjudications. Keep this pilot's
clusters outside the main analysis, calibration and specificity sets.

## 5. Freeze the protocol and prepare the main manifest

Follow [NEXT_ACTIONS.md](../../evidence_experiment/NEXT_ACTIONS.md), steps 2–4:
census the eligible template clusters, freeze sampling and analysis seeds,
define source-first transformation placement, annotate referents and mappings,
and retain the required validation outputs. Do not construct final data by
copying mock pilot outputs. Set `ANALYSIS_MANIFEST`, `CALIBRATION_MANIFEST` and
`REPEATS` in `work/myriad/env.sh` to the frozen corpus paths and repeat count.
Use a new root/config if you change context or any other scientific setting.

Manifest verification and the existing corpus validation use scheduled CPU
jobs. Submit validation after verification succeeds:

```bash
qsub scripts/myriad/cpu.sge verify
qsub scripts/myriad/cpu.sge validate --witness-plan /repo/corpus/witness_plan.jsonl
```

The query/slice phases refuse admissible pairs
without their retained validation checks.

## 6. Acquire main evidence and issue the masked review queue

Submit each command after the previous job has exited successfully:

```bash
qsub scripts/myriad/gpu.sge query
qsub scripts/myriad/cpu.sge slice
qsub scripts/myriad/cpu.sge packets --duplicate-fraction 0.1 --review-seed FROZEN_SEED
```

Replace `FROZEN_SEED` with the protocol's integer. Inspect the per-job exit
code, scheduler log and query/slice status counts. A completed scheduler job
is not proof of scientific success. Grid Engine `-hold_jid` waits for completion
even when the predecessor failed; manual success checks are deliberate here.

The wrapper serializes writers within each work directory. Acquisition locks
permit different local ports and staging directories between jobs, while
freezing sources, code, model settings, runtime and repeat count. After a
timeout, resubmit the same phase with the same inputs to resume retained rows.
Any scientific/code change needs a new work directory. Do not run arrays
against a single work directory; shard manifests and use private directories
before introducing parallel workers.

## 7. Review evidence and run the evidence-only analysis

Supply only the masked packets to independent assessors. Keep the review key
private; collect two ratings, disagreement resolutions and referent matches.
Then submit, replacing the paths and integer seed with your actual files:

```bash
qsub scripts/myriad/cpu.sge analyze --evidence-only --assessments /repo/corpus/reviews.jsonl --adjudications /repo/corpus/matches.jsonl --resolutions /repo/corpus/resolutions.jsonl --analysis-seed FROZEN_SEED
```

Alternatively run analysis locally with the same manifest/config/work data.
Analysis does not require a GPU or reuse detector failures as evidence labels.
Missing human ratings remain uncertain; they must not be replaced by model
ratings for dissertation conclusions.

## 8. Calibrate D separately and add detector results

Populate the disjoint mixed-label calibration and safe specificity manifest,
with clusters excluded from the pilot and main study. Predeclare the
`detector_calibration_abstentions` policy: the default is `fail`; `exclude`
requires reporting scored and abstained samples by split/label. Change this
policy before calibration, not after looking at its result, and use a new
calibration directory if changing it.

```bash
qsub scripts/myriad/gpu.sge score-calibration
```

This loads Q first, releases it, then loads the pinned D adapter/base. Inspect
the calibration stage traces, score/failure rows, class token IDs in the log,
specificity and usability gate before proceeding. A pilot D result or paper
threshold is not a substitute for disjoint local calibration. If GPU memory
is not reclaimed after Q, retain the traces and diagnose the runtime before
rerunning; do not silently change models or quantization.

```bash
qsub scripts/myriad/gpu.sge detect
qsub scripts/myriad/cpu.sge analyze --assessments /repo/corpus/reviews.jsonl --adjudications /repo/corpus/matches.jsonl --resolutions /repo/corpus/resolutions.jsonl --analysis-seed FROZEN_SEED
```

`detect` renders the calibrated threshold into its per-job config and passes
the calibration file explicitly. It refuses mismatched Q/D/base revisions,
context, scoring code/runtime, image identity, input lock, trace hashes or
analysis population. D outcomes supplement the evidence estimates. If D's
usability gate fails, retain the evidence-only results and report that limit.

## 9. Archive results and report the RQs

Retain the protocol, manifests, validation outputs, exact config/revisions,
image checksums, package freeze, experiment/calibration/detector locks, phase
logs, raw outputs, review provenance and final `analysis.json`. Report RQ1's
full original denominator; RQ2's eligible and unresolved counts, predetermined
cluster representatives, Newcombe method 10 interval and sensitivity results;
RQ3's stage traces and diagnostic probes; reviewer agreement and decoy results;
and calibration abstentions/usability. Hardware success does not establish
scientific validity.

Use `qstat -u "$USER"`, retained `.o/.e` logs and `jobhist` (where available)
to measure wall time and peak memory before enlarging jobs. GPU wall time
starts after scheduling; check queue delays separately. Myriad's default home
quota is 1 TB and is also considered scratch. Monitor `gquota` and back up
essential outputs outside the cluster, such as institutional research storage.
Completed JSONL/logs are written outside `$TMPDIR`; job-local Joern graphs and
staged inputs are disposable and reconstructed when resuming.
