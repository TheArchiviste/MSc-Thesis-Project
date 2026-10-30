# Read-only Q runtime metadata probe

Use this probe only to investigate a stage-lock/session inventory mismatch on a preserved, unsealed development acquisition. It does not run the collector or correct records. Keep the original archive, lock, session file and attempt marker intact.

Python package discovery can expose bundled dependencies when an existing directory is appended to `sys.path`. Setuptools documents this behavior in [its maintainer explanation](https://github.com/pypa/setuptools/issues/4516) and implements it in [package initialization](https://github.com/pypa/setuptools/blob/main/setuptools/__init__.py). A dictionary keyed by package name can overwrite an earlier version when enumeration encounters another copy later.

Ray also prepends its `thirdparty_files` directory in [package initialization](https://github.com/ray-project/ray/blob/master/python/ray/__init__.py). Its [build script](https://github.com/ray-project/ray/blob/master/python/setup.py) bundles `psutil` and `colorama` there. Both directory registrations must be represented when testing a process that imports these libraries.

Protocol `rq1-v7-bundled-metadata-probe-v2` verifies the preserved archive, private accepted inspection, acquisition contract, original files and provenance predicates. It requires the current inventory to match the accepted stage inventory. It first appends the installed Setuptools vendor directory, then prepends Ray's installed `thirdparty_files` directory, matching their upstream registration rules. It records both the intermediate and combined inventories and requires the combined inventory to equal the recorded session inventory exactly. It restores the path even if discovery fails, checks the original inventory returns, and compares installed metadata and original file hashes before and after. The proof binds the installed bootstrap-source hashes and the bundled metadata hashes. The probe imports no Q/torch/vLLM/Ray/Setuptools module, loads no weights, downloads nothing, installs no packages and changes no original acquisition records.

From the accepted laptop checkout, after starting the existing VM and reading its current console IP:

```bash
bash ops/rq1_q_vendor_probe.sh \
  CURRENT_VM_PUBLIC_IP \
  PRIVATE_FAILED_Q_ARCHIVE ARCHIVE_SHA256 \
  PRIVATE_ACCEPTED_INSPECTION_ZIP INSPECTION_SHA256
```

The wrapper waits for SSH, updates the clean existing checkout and runs only the probe. It retrieves the private proof and verifies its hash, protocol, code binding and original-file hashes against the laptop archive. Each run creates new proof and summary files and preserves earlier attempts. Stop the VM in its console afterward. Return only the printed `rq1-q-vendor-proof-session-*.summary.json`; keep the proof and raw acquisition archive private.

A failed proof leaves the mismatch unresolved. A passing proof establishes only the metadata-discovery explanation. It does not accept the acquisition, relax the validator, rebind a freeze, authorize another generation attempt or correct session metadata. Any reconciliation must retain the original bytes, bind the proof and pass the unchanged strict validator separately.
