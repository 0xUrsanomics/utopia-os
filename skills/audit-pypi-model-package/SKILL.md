---
name: audit-pypi-model-package
description: Decide whether a PyPI package that downloads or loads model weights is safe to install, and clean it up if it loses the bench. Covers the stand-down check, the age gate, a digest match, a source read for unsafe loads and open binds, its own pinned venv, and a removal path.
trigger: install this pypi package, pip install a model library, try this open model package, is this package safe to install, bench a new python model package
linter_ack: ["dynamic-exec: lists eval/exec as strings to search for in third-party source, not code to run", "pkg-install: the trigger phrase names the install this skill gates"]
---

# Audit a PyPI model package before installing it

Scope: one sub-procedure, the audit and the cleanup around an install. The bench itself is `skills/shadow-test-local-classifier/SKILL.md`.

## Steps

1. Run the stand-down check first: `python3 scripts/security/check_standdown.py <package>`. Block means refuse and say why. Warn means proceed only after the operator re-confirms, citing the reason. Registry format: `memory/state/standdowns.example.json`.
2. Read the registry record at `https://pypi.org/pypi/<package>/json`. Note the exact release date, the maintainers, the project URLs and the download figure if shown. Apply the 7-day gate to the repo AND to the exact release: if the newest release is one day old, pick the newest release that is at least 7 days old and pin it. Flag under 1K weekly downloads or a last release more than 12 months old.
3. Fetch the artifact without installing it. Take the sdist or wheel URL from the JSON and download it with curl into a new empty directory. Do not use `pip download` for an sdist: pip may run the package's build code to read its metadata. Compare `sha256sum` of the file with `urls[].digests.sha256` from the same JSON. A mismatch ends the audit.
4. Unpack into its own new empty directory and read the files as text from a different working directory. If any Python reads them, run it with `python3 -I`. Never run anything inside the extracted tree. `scripts/security/safe_unzip.sh` handles zip archives.
5. Answer three questions from the source before any install:
   - How are weights loaded? Look for `pickle`, `torch.load`, `trust_remote_code`, `eval(`, `exec(`. Safetensors with an `allow_patterns` filter is the good case.
   - What does it do on the network? Look for `requests`, `urlopen`, `socket`, `snapshot_download`, `hf_hub_download`, and any telemetry.
   - What does it bind or run on its own? Look for `0.0.0.0` (a bundled server that binds all interfaces by default is common, even when unused), entry points, and post-install hooks.
   Anything that touches credentials or files outside its own cache gets read in full.
6. Write the verdict block before installing: package, version and release date, digest match yes or no, weight loading, network behaviour, binds, install path, decision.
7. Install into its own venv under `~/tools/<name>` with the exact pinned version, never into the agent's main venv. Add a GPU build of torch only if the bench needs one.
8. Bench against the incumbent on the incumbent's own fixed held-out splits, under a shared GPU lock if the GPU is shared. A vendor benchmark decides nothing: a candidate can beat the incumbent on its own report and lose most tasks on yours.
9. If the candidate loses: archive its script and report to `sandbox/archive/<name>-bench-<date>/`, then delete the venv and the model cache. Size the cache with `du -shL`: plain `du -sh` does not follow the cache's symlinks and can report a few MB for a blob of several hundred MB. Ask once before deleting. Record the install, the result and the removal in `Decisions.md`.

## Output

A memo in `outputs/raw/<persona>/` led by the verdict block from step 6, followed by the bench table.

## Caveats

- A digest match proves the file is the one PyPI serves. It does not prove the code is benign, and the grep list in step 5 is a prompt for reading, not a scanner verdict.
- Weights fetched on first run are a second download. Pin the revision or restrict the files, and read the model repo's file list.
- Related: `knowledge/llm-supply-chain-security.md`, `scripts/security/osv_check.py` for known CVEs in the dependency tree.
