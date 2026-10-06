# Execution sequence for the evidence experiment

Run from the repository root. Keep the four `_01` pilot cases and their fixed
controls in a development work directory; do not reuse them in the final
analysis or either calibration split. Record software revisions, GPU and Joern
image digest with every run. The `work/` directory is ignored by Git.

1. **Run the real development probe on the university GPU node.** Complete the
   environment and Joern checks in [`juliet_pilot/RUNBOOK.md`](../juliet_pilot/RUNBOOK.md).
   Create a local `real_probe.json` from the example, replace its Joern digest,
   and run:

   ```bash
   python juliet_pilot/prepare.py
   python juliet_pilot/real_probe.py --config real_probe.json
   python juliet_pilot/real_probe.py --config real_probe.json --work work/real-probe-controls --include-fixed-controls
   ```

   Expect 24 query and 24 slice rows. Inspect `probe_summary.json`, failures
   and traces, and `probe_readouts.json`. Look for near-complete function
   coverage, missing guards or other roles, and U/fixed excerpts that fail to
   distinguish the documented mechanism. The generated readouts are mechanical;
   masked reviewers must judge whether the four fixed packets receive a false
   adequacy rating. If slices are saturated or fixed controls appear vulnerable,
   trial longer Juliet data-flow variants before choosing the analysis frame.

2. **Freeze the protocol before main enrolment.** Write down the sampling frame
   and one `cluster_id` per CWE/flaw-template group; the admissibility and
   exclusion rules; the documented vulnerability claim, allowed assumptions
   about helpers, and blind review rubric; and the target/control candidates
   selected from source annotations. Do not move candidate locations after
   viewing the slices. Decide a deterministic catalogue and placement rule for
   alias, temporary-variable, or wrapper transforms. Predeclare the primary
   paired contrast, a cluster-aware interval, uncertainty bounds, and a
   sensitivity analysis with one case per cluster. Plan yield and reviewer
   capacity: roughly 40 *analysable independent pairs* are useful for a large
   effect but imprecise, so about 100 enrolled pairs is a provisional planning
   number, not a guarantee of power. Record a feasible precision target and
   revise N from pilot yield before the main run. Use `--repeats 1` for the main
   deterministic Q run if the probe shows no meaningful variability, and run a
   separate repeated stability sample. A disguised duplicate-packet review
   sample is needed to quantify **rater** noise; repeated Q calls measure a
   different source of variation.

3. **Prepare the corpus and finite witnesses.** Enrol vulnerable originals
   before any Q result is seen. Include documented misses and all admissible
   TM/TN pairs in `corpus/cases.jsonl` with source-coordinate element mappings,
   claim, operator, predeclared candidate lines, and per-arm diagnostic rules.
   Construct matched edits, retain diffs, mapping checks and independent
   mechanism review. Use `benign_reason` if no benign input exists. Check
   compiler/ASan trigger and any benign input on all three arms with a
   `corpus/witness_plan.jsonl`, then inspect and retain the record:

   ```bash
   python -m evidence_experiment verify --manifest corpus/cases.jsonl --work work/main-001
   python -m evidence_experiment validate --manifest corpus/cases.jsonl --work work/main-001 --witness-plan corpus/witness_plan.jsonl
   ```

   The witness is finite evidence. It does not prove semantic equivalence.
   The source-first target/control candidates must each occur in the *selected*
   original slice for a pair to enter the primary RQ2 analysis. Record every
   failed check and excluded pair rather than replacing it opportunistically.

4. **Acquire Q and Joern evidence independently of D.** Pin Q, Joern and
   dependencies in `corpus/config.json`; use a distinct `work/main-001` from
   the development probe. Pass the same frozen `--repeats` value to every
   command (shown here as one):

   ```bash
   python -m evidence_experiment query --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   python -m evidence_experiment slice --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   python -m evidence_experiment packets --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   ```

   Check raw query failures, CPGQL traces, selected versus rendered lines,
   role coverage and the eligible-pair yield. A missing D checkpoint or a
   failed D calibration does not prevent this evidence study.

5. **Review packets and analyse evidence.** Mix separately generated fixed
   safe controls into the *development* blind review queue; keep their IDs and
   safe status out of reviewer view, then calculate false adequacy by joining
   results privately. For the analysis corpus collect two independent ratings
   per unique packet, resolve disagreements with a third reviewer or recorded
   consensus, and perform source-referent matching in each packet's own source
   coordinates. Double-check an adjudication sample independently. Keep packet
   order, disclosure and duplicate-review procedure in the protocol. The
   current CLI accepts the resolved ratings and records unresolved cases. Omit
   `--resolutions` if there were no resolved disagreements:

   ```bash
   python -m evidence_experiment analyze --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --assessments reviews.jsonl --adjudications matches.jsonl --resolutions resolutions.jsonl --evidence-only
   ```

   Inspect RQ1's full original denominator; RQ2's enrolled, eligible and
   resolved counts and uncertainty bounds; and RQ3's stage traces and probe
   patterns. The reporter does not automatically score the external safe
   control queue or the disguised reviewer duplicates.

6. **Pin and calibrate D on disjoint data.** On the suitable GPU, smoke-test
   the released adapter, its *pinned* 4-bit base and tokenizer, and the Yes/No
   probability head. Create `corpus/calibration_manifest.jsonl` with mixed
   vulnerable/safe calibration examples and a separate safe specificity set,
   grouped so neither overlaps the analysis templates. Run the actual stages:

   ```bash
   python -m evidence_experiment score-calibration --manifest corpus/cases.jsonl --calibration-manifest corpus/calibration_manifest.jsonl --config corpus/config.json --work work/main-001
   ```

   If any score is missing or the usability screen fails, retain the
   evidence-only result and diagnose D without tuning on analysis cases.
   Otherwise copy the resulting threshold into the config (the acquisition
   lock permits this before D), then execute:

   ```bash
   python -m evidence_experiment detect --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1
   python -m evidence_experiment analyze --manifest corpus/cases.jsonl --config corpus/config.json --work work/main-001 --repeats 1 --assessments reviews.jsonl --adjudications matches.jsonl --resolutions resolutions.jsonl
   ```

   Inspect D abstentions and verdicts crossed with adequacy. Publish estimates
   with the filter yield, reviewer agreement and resolution rate, cluster CI
   (only with at least two clusters), uncertain-outcome bounds, safe-control
   false adequacy, and the limits of finite witnesses and Juliet generality.
