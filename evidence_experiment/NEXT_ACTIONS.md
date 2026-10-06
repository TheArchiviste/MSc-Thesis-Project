# Execution sequence for the evidence experiment

Run from the repository root. Keep the four `_01` pilot cases and their fixed
controls in a development work directory; do not reuse their template clusters
in the final analysis or either calibration split. Every phase records the
checkout, packages and Q/Joern pin check in `phase_log.jsonl`. The `work/`
directory is ignored by Git.

For UCL Myriad, use the scheduler commands and setup in
[`scripts/myriad/RUNBOOK.md`](../scripts/myriad/RUNBOOK.md). It selects U/V
A100 80 GB nodes, builds an Apptainer runtime and records image/model pins.
The commands below describe pipeline phases; run heavy phases as the
corresponding Myriad jobs rather than on its login nodes.

0. **Update and reinstall.** `evidence_experiment` is now an installed
   package, so after pulling run `python -m pip install -e .` (and
   `'.[inference]'` on the GPU node). The pilot scripts also work from the
   checkout without reinstalling.

1. **Run the development probe on the university GPU node.** Complete the
   environment and Joern checks in [`juliet_pilot/RUNBOOK.md`](../juliet_pilot/RUNBOOK.md),
   create `real_probe.json` from the example, set its Joern digest, and run:

   ```bash
   python juliet_pilot/prepare.py
   python juliet_pilot/real_probe.py --config real_probe.json
   python juliet_pilot/real_probe.py --config real_probe.json --work work/real-probe-controls --include-fixed-controls
   ```

   Expect 16 query and 16 slice rows: 4 vulnerable cases × 3 repeats, plus each
   fixed control once as the case's decoy (`F`) arm. Read `probe_readouts.json`:

   * `U_selected_fraction` near 1 means slices are saturated;
   * `element_roles` shows which roles (guard, capacity, lifetime event, sink)
     were selected;
   * `fix_site_selected_in_U` / `fix_site_selected_in_fixed` false, or
     `fixed_excerpt_text_identical` true, means the excerpt cannot distinguish
     the vulnerable program from its fix;
   * all failures must have retained Joern traces.

   Then have two masked reviewers rate the 8 packets in
   `blind_review_packets.jsonl`. Join their ratings to `review_key.jsonl`
   privately: any decoy rated adequate is a false adequacy.

2. **Decide the corpus frame from the census.** Juliet caps the number of
   independent clusters. Count templates in the pinned mirror:

   ```bash
   git clone --filter=blob:none --no-checkout https://github.com/arichardson/juliet-test-suite-c juliet
   git -C juliet ls-tree -r --name-only f88433e3443648a17671398797a04ea1f8e1a274 testcases > juliet-files.txt
   python juliet_pilot/templates.py census --file-list juliet-files.txt
   python juliet_pilot/templates.py census --file-list juliet-files.txt --include-related
   ```

   With the default grouping, the C files of the five in-scope CWEs give 48
   templates (66 if copy sinks are kept distinct; CWE-124/126/127 add 18).
   CWE-416 has 2 templates, neither with single-file cross-function
   variants, and CWE-415 has 1. Decide, and record:

   * the template grouping (default, or `--keep-copy-sinks`) and scope
     (CWE-124/126/127, C++, multi-file `_5x`/`_6x` variants; multi-file needs
     a concatenation step that `prepare.py` does not yet provide);
   * whether lifetime flaws are in scope at all, given 3 C templates;
   * if the probe showed saturated or non-discriminating slices, which longer
     single-file cross-function variants (`_41`, `_42`, `_44`, `_45`) to use.

3. **Freeze the protocol before main enrolment.** Write down:

   * the sampling frame, cluster grouping and per-template enrolment rule;
   * N **in clusters**, with the precision you can expect. Roughly 20–30
     independent analysable clusters gives a 95% interval half-width of about
     ±0.2–0.25 for the paired difference;
   * the primary RQ2 analysis: `one_case_per_cluster` (exact McNemar,
     Newcombe interval) is recommended with fewer than ~30 clusters, with the
     all-pairs cluster bootstrap as sensitivity; and the `--analysis-seed`;
     representatives are selected from baseline-eligible cases before
     transformed outcomes are resolved; an uncertain representative is
     retained and never replaced by a resolved case from its cluster;
   * admissibility and exclusion rules; operator catalogue and deterministic
     placement rule; source-first target/control candidates;
   * the claim for each case (`flaw_class` + `operation`), allowed assumptions
     about helpers, the review rubric, and what reviewers are told about decoys;
   * decoys: include `sources.F` for every case with a documented fixed variant;
   * the duplicate share and `--review-seed`;
   * the disagreement-resolution process and an adjudication double-check sample;
   * `detector_calibration_abstentions` (`exclude` with reporting, or `fail`);
   * `--repeats 1` for the main deterministic Q run if the probe showed no
     repeat variation, plus a separate repeated stability sample.

4. **Prepare the corpus and finite witnesses.** Enrol vulnerable originals
   before any Q result is seen, including documented misses. Write
   `corpus/cases.jsonl` with `cluster_id` from `templates.py`, templated
   claims, `sources.F`, element mappings, operator, predeclared candidate
   lines and per-arm rules. Retain diffs, mapping checks and independent
   mechanism review. Compare ASan's reported access, allocation and free lines
   with `mapped_lines` in each arm. Use `benign_reason` if no benign input
   exists. Then:

   ```bash
   python -m evidence_experiment verify --manifest corpus/cases.jsonl --work work/main-001
   python -m evidence_experiment validate --manifest corpus/cases.jsonl --work work/main-001 --witness-plan corpus/witness_plan.jsonl
   ```

   `verify` lists claim problems and decoy counts. Record every failed check
   and excluded pair rather than replacing it opportunistically.

5. **Acquire Q and Joern evidence independently of D.** Pin Q and Joern in
   `corpus/config.json` (no threshold yet) and pass the same `--repeats` to
   every command:

   ```bash
   python -m evidence_experiment query   --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   python -m evidence_experiment slice   --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   python -m evidence_experiment packets --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --duplicate-fraction 0.1 --review-seed SEED
   ```

   Check raw query failures, CPGQL traces, selected versus rendered lines,
   role coverage and the eligible-pair yield. The issued review queue is
   frozen from here on.

6. **Review and analyse the evidence.** Send only `blind_review_packets.jsonl`
   to reviewers; keep `review_key.jsonl` private. Collect two independent
   ratings per packet, resolve disagreements by third review or recorded
   consensus, and adjudicate evidence packets against the referent in each
   packet's own coordinates. Review and analysis may run on the laptop:

   ```bash
   python -m evidence_experiment analyze --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --assessments reviews.jsonl --adjudications matches.jsonl --resolutions resolutions.jsonl --analysis-seed SEED --evidence-only
   ```

   Inspect RQ1's full original denominator; RQ2's enrolled, eligible and
   resolved counts, `one_case_per_cluster`, bounds and coverage change; RQ3's
   stage traces and probe patterns; and `review_quality` (agreement by arm,
   decoy false adequacy, duplicate test-retest).

7. **Pin and calibrate D in its own directory.** Smoke-test the released
   adapter, its pinned 4-bit base and tokenizer, and the Yes/No head. Create
   `corpus/calibration_manifest.jsonl` with mixed calibration examples and a
   safe specificity set from templates outside the analysis clusters, then:

   ```bash
   python -m evidence_experiment score-calibration --manifest corpus/cases.jsonl --calibration-manifest corpus/calibration_manifest.jsonl --config corpus/config.json --work work/calibration-001
   ```

   Prepare D dependencies before the cluster run and use the frozen SIF for
   calibration and detection. Calibration records effective model settings,
   scoring code, packages, image identity and stage hashes. Resuming calibration
   or detecting in a different scoring environment is refused. If the usability screen fails, keep the evidence-only
   result and diagnose D without tuning on analysis cases.

8. **Detect and report.** Copy the calibrated threshold into the config, then:

   ```bash
   python -m evidence_experiment detect  --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --calibration work/calibration-001/calibration.json
   python -m evidence_experiment analyze --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --assessments reviews.jsonl --adjudications matches.jsonl --resolutions resolutions.jsonl --analysis-seed SEED
   ```

   Publish estimates with the filter yield, reviewer agreement and resolution
   rate, the predeclared primary RQ2 analysis and its sensitivity analyses,
   uncertain-outcome bounds, decoy false adequacy, calibration abstentions by
   label, and the limits of finite witnesses and Juliet generality.
