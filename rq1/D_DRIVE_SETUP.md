# Existing D: storage and local CPU checkpoint

The user's Ubuntu-24.04 distribution is registered on the D: virtual disk at
`D:\Dissertation-RQ1\wsl\Ubuntu-24.04`. Its Linux repository under
`~/projects/MSc-Thesis-Project`, virtual environments and work outputs are
therefore D-backed. Docker Desktop's verified data disk is
`D:\Dissertation-RQ1\DockerDesktopWSL\disk\docker_data.vhdx`.
These locations were checked in earlier user outputs; no further disk move,
unregistration or deletion is required. The older separate Ubuntu on C: is
not the distribution used for this checkpoint.

The new local scripts explicitly place Hugging Face cache files in
`D:\Dissertation-RQ1\huggingface` and return ZIPs in
`D:\Dissertation-RQ1\exports`. They disable pip's download cache. Docker
images and named volumes use the already configured D-backed Docker disk.
They preserve old `work/rq1` files and write new records in `work/rq1-v5`.

Open **Ubuntu-24.04**, not PowerShell or the older Ubuntu distribution, then
run checkpoint 1 in [RUNBOOK.md](RUNBOOK.md). It uses the CPU for compilation,
token counting, full synthetic selector acceptance and reporting. It neither
starts a cloud GPU nor downloads the original Q weights. Return its ZIP and
pause before any Nebius step.

For a future fresh machine, verify the WSL base path and Docker disk image
location in Windows/Docker settings before large downloads. Do not manually
move live virtual disks or delete a distribution as part of experiment setup.
