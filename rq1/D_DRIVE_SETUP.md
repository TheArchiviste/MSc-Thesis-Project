# Laptop storage and CPU setup — 28 October 2026

Observed from the user's screenshots: Windows 11, WSL 3.0.3, Ubuntu running on WSL2, Python 3.14.4, Docker Desktop 4.97.0 reachable from Ubuntu, Docker Compose 5.6.1, 15.8 GiB RAM, and a GTX 1660 Ti with 6144 MiB VRAM. C: has 14.6 GiB free. The user reports 849 GB free on D: and requires extensive experiment storage there.

The next checkpoint is **storage placement and the tested Python environment**. No local Q weights, Joern image, or experiment dependencies should be downloaded before their destination is established. These are instructions for the user's machine; no D: folder has been created by the remote workspace.

## Layout

Use `D:\Dissertation-RQ1` as the common bulk-storage root:

| Folder | Contents |
|---|---|
| `wsl\Ubuntu-24.04` | Dedicated Linux filesystem, including the project, Python 3.12 virtual environment, package/tokenizer caches, source checks and run outputs |
| `docker-data` | Docker Desktop disk image: Joern image layers, container filesystems and named CPG volumes |
| `exports` | Copies of reports, result archives and files exchanged with the GPU host |
| `wsl\swap.vhdx` (next memory checkpoint) | WSL swap, configured after reading any existing `.wslconfig` so other settings are preserved |

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

In Docker Desktop, open **Settings → Resources → Advanced → Disk image location**. Select `D:\Dissertation-RQ1\docker-data`, apply the change and let Docker complete its supported disk move/restart. This relocates Docker's shared image/volume store, including any existing Docker workloads; save active work before applying it. Use Docker's relocation control, rather than manually dragging its virtual disks in Explorer.

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

Official references checked for this setup:

- [Microsoft WSL commands: installing with --location](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
- [Microsoft WSL virtual disks and physical storage](https://learn.microsoft.com/en-us/windows/wsl/disk-space)
- [Docker Desktop WSL2 storage location and distribution integration](https://docs.docker.com/desktop/features/wsl/)
