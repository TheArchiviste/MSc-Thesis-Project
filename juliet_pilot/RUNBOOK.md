# Four-case real-run setup

This runbook has two hosts. The Windows laptop (GTX 1660 Ti, 6 GB VRAM,
16 GB RAM) runs the CPU checks, Joern, and the simulated smoke test. A Linux
university GPU node runs the released Q checkpoint and real Joern. Keep their
`work/` directories separate. The first real probe is **Q → Joern only**;
it does not execute D or estimate RQ1–RQ3.

## Laptop: WSL 2 and Docker

Install [WSL 2](https://learn.microsoft.com/windows/wsl/install) with Ubuntu,
then [Docker Desktop with WSL integration](https://docs.docker.com/desktop/features/wsl/use-wsl/).
Keep the checkout in the Ubuntu filesystem, for example `~/MSc-Thesis-Project`.
In a PowerShell window (only if WSL is not already installed):

```powershell
wsl --install -d Ubuntu
```

In Ubuntu, after Docker Desktop has started and WSL integration is enabled:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip gcc
git clone https://github.com/TheArchiviste/MSc-Thesis-Project.git
cd MSc-Thesis-Project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/pilot_setup.py init
docker pull ghcr.io/joernio/joern:v4.0.0
JOERN_IMAGE="$(docker image inspect ghcr.io/joernio/joern:v4.0.0 --format '{{index .RepoDigests 0}}')"
JOERN_DIGEST="${JOERN_IMAGE##*@}"
python scripts/pilot_setup.py pin-joern --digest "$JOERN_DIGEST"
JOERN_IMAGE="$JOERN_IMAGE" docker compose -f docker/docker-compose.yml up -d
python scripts/pilot_setup.py doctor --profile local
python juliet_pilot/witness.py
python juliet_pilot/smoke.py --work work/local-smoke
```

`doctor` imports a tiny C file through the *actual* Joern client, checks that
the server sees the mounted source, and verifies the running Docker image
against the config digest. A TCP-open check alone cannot establish any of
those properties. Fix any failed required check before proceeding. The
simulated smoke report is a wiring test, not a model result. The laptop's
6 GB GPU cannot load the released Q or D checkpoints.

## University: GPU node

Ask the university how to request a Linux node with an NVIDIA BF16 GPU with
around 80 GB VRAM, at least 32 GB system RAM, and substantial scratch storage.
One 80 GB GPU is a *trial configuration*, not a promise that 32K context and
the current vLLM memory setting will fit. The current probe uses one GPU
(`tensor_parallel_size=1`); memory across multiple cards is not automatically
combined. Obtain the site's allowed container runtime (Docker or Apptainer),
GPU allocation command, wall time, and scratch path before starting a download.

On the allocated node, make a fresh checkout in a persistent project location.
Use a job scratch filesystem for the Hugging Face cache with at least 100 GiB
free (more is prudent if retaining both Q and D). From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[inference]'
python -m pip install bitsandbytes
export HF_HOME=/path/to/allocated/scratch/huggingface
mkdir -p "$HF_HOME"
python scripts/pilot_setup.py init
```

If Docker is allowed, start Joern with the same `docker pull`, `JOERN_IMAGE`,
`pin-joern`, and `docker compose` commands from the laptop section. Then:

```bash
python scripts/pilot_setup.py doctor --profile gpu
python juliet_pilot/real_probe.py --config work/real_probe.json
python juliet_pilot/real_probe.py --config work/real_probe.json --work work/real-probe
python -m pip freeze > work/real-probe-packages.txt
nvidia-smi > work/real-probe-gpu.txt
```

The two checks before the last probe do **not** download model weights. The
probe does, and its output should have 12 query rows and 12 slice rows. Check
`work/real-probe/probe_summary.json`, `queries.jsonl`, and `slices.jsonl` for
failures rather than treating a completed process as a valid result. Keep
the raw files and environment records together. The `work/` tree is ignored
by Git, so copy results to university persistent storage before a scratch
allocation expires. Do not commit checkpoints, local configs, or raw results.

### If the university uses Apptainer instead of Docker

Use the same `ghcr.io/joernio/joern@sha256:...` OCI image digest and bind the
repo's `work/joern-inputs` to `/analysis/inputs` read-only. The server and
Python client must share the node and port 8080. For an interactive allocation,
set `JOERN_DIGEST` to the full `sha256:...` value recorded on the laptop (or
obtain the exact image digest through the university's OCI registry tooling).
The shape of the command is:

```bash
mkdir -p work/joern-inputs work/joern-server
apptainer exec \
  --bind "$PWD/work/joern-inputs:/analysis/inputs:ro" \
  --bind "$PWD/work/joern-server:/workspace" \
  "docker://ghcr.io/joernio/joern@${JOERN_DIGEST}" \
  joern --server --server-host 127.0.0.1 --server-port 8080
```

Run that server in a separate terminal or job step, pin the exact digest with
`python scripts/pilot_setup.py pin-joern --digest "$JOERN_DIGEST"`, and use
`python scripts/pilot_setup.py doctor --profile gpu --apptainer` in the client
step. The Apptainer flag still performs the real CPG import but reports image
provenance as **unverified**: check the OCI reference and site cache policy
yourself. The site's bind rules and network namespaces may need adjustments.
See the [Apptainer bind documentation](https://apptainer.org/docs/user/main/bind_paths_and_mounts.html).

## Scope after the first probe

The D publication is an adapter, not a standalone 2 GB classifier. Before a
Q → Joern → D run, pin its named 4-bit base snapshot and verify adapter load,
Yes/No token head, and outputs on a small labeled sanity set. Calibrate any
threshold on a separate mixed-label cohort; `0.5` in the exploratory config
is a placeholder. The four pilot cases cannot calibrate and evaluate their
own detector. Valid RQ2 needs admissible target/control transforms and RQ1
needs independent adequacy review. Do not label this four-case probe as final
RQ evidence.
