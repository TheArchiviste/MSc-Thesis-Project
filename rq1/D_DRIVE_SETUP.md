# Laptop storage and CPU setup — 28 October 2026

Observed from the user's screenshots: Windows 11, WSL 3.0.3, Ubuntu running on WSL2, Python 3.14.4, Docker Desktop 4.97.0 reachable from Ubuntu, Docker Compose 5.6.1, 15.8 GiB RAM, and a GTX 1660 Ti with 6144 MiB VRAM. C: has 14.6 GiB free. The user reports 849 GB free on D: and requires extensive experiment storage there.

The returned preparation log confirms **Ubuntu-24.04/Python 3.12.3 and all 15 current U/F witness pairs passing on the user's laptop** at commit `272b82e9ce465a32b460d7dcf522eb17c6d7c625`. The registered filesystem path is on D:. The latest screenshot reports 7.8 GiB WSL RAM (6.6 GiB available) and 4 GiB swap. The returned Windows storage check verifies Docker data at `D:\Dissertation-RQ1\DockerDesktopWSL\disk\docker_data.vhdx` (8.05 GiB), its supporting filesystem on D:, the dedicated Ubuntu filesystem on D: (2.18 GiB), and swap on D:. The older separate `Ubuntu` installation remains on C: and is left intact. The current checkpoint is **section 6: rerun the CPU prompt-token audit after the Jinja dependency fix**. Folder creation, configuration and commands on the user's machine are performed by the user; the remote workspace prepares and checks the code. The first real Joern readiness attempt was blocked during startup; the corrected second attempt passed all 8 checks, including staged C import/query, with the greeting received after 13.431 seconds. Q and experiment slicing have not run. The laptop token audit then exposed a missing Jinja dependency; the next action is its corrected rerun.

## Layout

Use `D:\Dissertation-RQ1` as the common bulk-storage root:

| Folder | Contents |
|---|---|
| `wsl\Ubuntu-24.04` | Dedicated Linux filesystem, including the project, Python 3.12 virtual environment, package/tokenizer caches, source checks and run outputs |
| `DockerDesktopWSL` | Verified Docker Desktop disk images: Joern image layers, container filesystems and named CPG volumes |
| `exports` | Copies of reports, result archives and files exchanged with the GPU host |
| `wsl\swap.vhdx` | 4 GiB WSL swap under the supplied `.wslconfig` |

The dedicated Ubuntu 24.04 distribution matches the tested Python 3.12 setup. The currently installed `Ubuntu` distribution reports Python 3.14.4; do not assume its `python3` matches the tested runtime. Creating the project distribution directly on D: avoids relocating an existing user's Linux installation. Its Linux home and caches are physically on D: inside its virtual disk. Keep the repository inside that Linux filesystem for builds and Docker staging.

## 1. Create the destination and install Ubuntu 24.04 on D:

In Windows PowerShell:

```powershell
$rq1Root = 'D:\Dissertation-RQ1'
New-Item -ItemType Directory -Force -Path $rq1Root, "$rq1Root\wsl", "$rq1Root\docker-data", "$rq1Root\exports" | Out-Null
Get-Volume -DriveLetter D | Select-Object DriveLetter, FileSystem, SizeRemaining, Size
wsl --install -d Ubuntu-24.04 --location "$rq1Root\wsl\Ubuntu-24.04"
```

Complete the first-run Linux username/password prompts. When Ubuntu opens, type `exit` to return to PowerShell. If a command fails, retain its output and pause. Installation must report the intended D: destination; do not silently fall back to a C: installation. If Ubuntu-24.04 already exists, inspect its registered location instead of deleting or reinstalling it.

## 2. Place Docker's disk image on D:

This checkpoint has passed. The active Docker data disk is verified at `D:\Dissertation-RQ1\DockerDesktopWSL\disk\docker_data.vhdx`; the supporting distribution is also on D:. The earlier suggested folder name `docker-data` was only a proposed destination. The actual `DockerDesktopWSL` directory satisfies the storage requirement; no further move or deletion is needed. For a fresh installation, use Docker Desktop's **Settings → Resources → Advanced → Disk image location** control to choose a D: location, rather than manually moving virtual disks.

Then open **Settings → Resources → WSL Integration**, enable **Ubuntu-24.04**, and apply. Record the displayed disk-image location in the returned output or a screenshot. Moving only the repository would leave Docker image layers and CPG volumes on the old drive.

## 3. Verify, then pause

In PowerShell:

```powershell
wsl --list --verbose
wsl -d Ubuntu-24.04 -- python3 --version
wsl -d Ubuntu-24.04 -- free -h
wsl -d Ubuntu-24.04 -- docker version
wsl -d Ubuntu-24.04 -- docker compose version
Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' | Get-ItemProperty | Where-Object DistributionName -eq 'Ubuntu-24.04' | Select-Object DistributionName, BasePath | Format-List
Get-Volume -DriveLetter D | Select-Object DriveLetter, FileSystem, SizeRemaining, Size
if (Test-Path "$env:USERPROFILE\.wslconfig") { Get-Content "$env:USERPROFILE\.wslconfig" } else { 'No existing .wslconfig' }
```

Expected: Ubuntu-24.04 uses WSL2; Python is 3.12.x; Docker and Compose work from that distribution; the registered `BasePath` begins with `D:\Dissertation-RQ1\wsl\Ubuntu-24.04`; Docker's displayed disk image location is on D:. Linux `df` alone does not prove the backing Windows drive has free space: WSL virtual disks can advertise a larger maximum capacity.

Return these results and pause before repository installation or Joern image pulls. The assistant will inspect the actual WSL memory allowance and existing `.wslconfig` before finalising the Joern resource budget and placing WSL's swap file on D:. Ubuntu and Docker disk placement alone does not relocate Windows' default WSL swap file.

## CPU work after this checkpoint

| Stage | Execution resource |
|---|---|
| Corpus/reference checks and source mapping | Local CPU |
| GCC/AddressSanitizer U/F witnesses | Local CPU |
| Pinned tokenizer and prompt-size audit | Local CPU; downloads tokenizer files only |
| Real Joern parsing, CPG construction and slicing | Local CPU, subject to the development memory/import test |
| Packet preparation, AI-assisted matching, statistics and readable reports | Local CPU; the assistant supplies explained judgement when actual excerpts exist |
| Original full-precision Q generation | Separate sufficiently large GPU host; no allocation started |

The original Q checkpoint does not fit in this laptop's physical RAM or VRAM under the prepared full-precision runtime. A smaller or quantized model would be a different evaluated configuration. No local D inference or training is required for RQ1.

After storage verification, continue checkpoint 2 of `RUNBOOK.md` **inside Ubuntu-24.04**, with the repository under `~/projects`. That path, its `.venv`, work outputs and Linux caches will be backed by the D: virtual disk. Before main inference, use a separate GPU acceptance checkpoint; a university cluster is optional for the next local steps.

## 4. Completed checkpoint: memory, swap and CPU preparation

Use 8 GiB total WSL memory, shared by the Linux distributions and Docker backend, plus 4 GiB swap on D:. Joern's provisional container limit is now 6 GiB and its Java heap limit is 4 GiB. This leaves WSL headroom for Ubuntu, the Python client and native parsing. The real development import will test this budget; these settings have not been accepted on Joern hardware yet.

Save active Linux work, close Ubuntu terminals and quit Docker Desktop before the WSL restart. In PowerShell, create the config only if it is still absent:

```powershell
$rq1Config = Join-Path $env:USERPROFILE '.wslconfig'
if (Test-Path $rq1Config) {
    throw 'A .wslconfig now exists. Preserve it and return its contents before making changes.'
} else {
@'
[wsl2]
memory=8GB
swap=4GB
swapFile=D:\\Dissertation-RQ1\\wsl\\swap.vhdx
'@ | Set-Content -Path $rq1Config -Encoding ascii
    wsl --set-default Ubuntu-24.04
    wsl --shutdown
}
```

Restart Docker Desktop, then run `wsl -d Ubuntu-24.04` in PowerShell. Inside Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv gcc libc6-dev
mkdir -p ~/projects
cd ~/projects
git clone --branch codex/rq1-execution https://github.com/TheArchiviste/MSc-Thesis-Project.git
cd MSc-Thesis-Project
set -o pipefail
bash rq1/local_prepare.sh 2>&1 | tee /mnt/d/Dissertation-RQ1/exports/local-prepare.log
free -h
```

This checks the tested Python version, creates `.venv`, installs local dependencies, verifies the corpus and performs real U/F compiler/sanitizer checks. Existing configs/witnesses are preserved; a failed or stale existing witness blocks completion instead of being silently replaced. Large intentional sanitizer core dumps are disabled for the validation subprocesses. No Docker image, original Q weights, tokenization model or GPU packages are downloaded by this script.

The readable result is `work/rq1/local-preparation.md`, also copied to `D:\Dissertation-RQ1\exports\local-preparation.md` when that folder is available. The complete command log is `D:\Dissertation-RQ1\exports\local-prepare.log`. A fresh success should show development 3 cases/6 U/F sources and main 12 cases/24 U/F sources with current witnesses PASS, and zero Q/slice records.

Return the report/log, the new `free -h` output, and Docker Desktop's displayed disk-image location. Pause before pulling Joern or running queries. If a command fails, return its error log; do not delete outputs or reset failure records.

## 5. Completed checkpoint: real CPU Joern acceptance

CPU preparation and the memory/storage checkpoint have passed. The first Joern attempt reached only Docker's open port; the returned log shows an early WebSocket failure while Joern was still starting. The corrected helper waits for Joern's actual greeting before attempting import; the existing image and all earlier records are retained. Update the existing branch without recreating the environment or rerunning the compiler witnesses. In Ubuntu-24.04:

```bash
cd ~/projects/MSc-Thesis-Project
git pull --ff-only origin codex/rq1-execution
.venv/bin/python -m pip install --no-cache-dir -r rq1/requirements-local.txt
bash rq1/local_joern.sh
```

The helper starts the digest-pinned official image, waits for the real WebSocket greeting, records the running digest and checks a real staged C import/query. It uses the existing `.venv` directly. Its unique attempt directory preserves reports and diagnostics on success or failure, and a ZIP is copied to `D:\Dissertation-RQ1\exports`. Return the ZIP whose path is printed and pause before further execution. This uses the CPU and reuses the existing Joern image on D:. The explicitly pinned HTTP/WebSocket dependencies match the versions in the earlier preparation log. A fresh installation would download approximately 2.2 GiB of compressed image layers plus extraction space, under the verified D: storage. No model weights, Q generation, GPU or cluster is involved. See RUNBOOK section 3 for image provenance and acceptance limits.

## 6. Current checkpoint: CPU prompt-token audit

Joern smoke acceptance has passed. The missing Jinja2 dependency is now pinned to 3.1.6 in both the tokenizer and candidate GPU requirements. The corrected audit was run here on a CPU with no PyTorch: all 30 prompts fit, using 406–570 prompt tokens and at most 2618 tokens including the 2048-token generation allowance, below the 8192-token context. This workspace check does not replace the requested laptop result.

With Joern already stopped, run in Ubuntu-24.04:

```bash
cd ~/projects/MSc-Thesis-Project &&
git pull --ff-only origin codex/rq1-execution &&
.venv/bin/python -m pip install --no-cache-dir -r rq1/requirements-tokenizer.txt &&
set -o pipefail &&
.venv/bin/python -m rq1.setup token-audit 2>&1 |
    tee /mnt/d/Dissertation-RQ1/exports/token-audit-fixed.log &&
cp work/rq1-token-audit.json /mnt/d/Dissertation-RQ1/exports/rq1-token-audit.json
```

Return `rq1-token-audit.json` and `token-audit-fixed.log` from the D: exports folder, then pause. Preserve the earlier failed `token-audit.log`. The warning about missing model backends is expected for this CPU-only audit. Do not install PyTorch or rerun the compiler witnesses/Joern check to resolve the missing template dependency.

Official references checked for this setup:

- [Microsoft WSL commands: installing with --location](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
- [Microsoft WSL virtual disks and physical storage](https://learn.microsoft.com/en-us/windows/wsl/disk-space)
- [Docker Desktop WSL2 storage location and distribution integration](https://docs.docker.com/desktop/features/wsl/)
- [Microsoft .wslconfig memory and escaped swap-file paths](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
