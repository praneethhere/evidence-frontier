# NAACL 2027 — Prospective, trajectory-disjoint holdout (frozen v0.6 rules)

**Research status:** The previously reported 36-case **96.97% F1** is a **development-set** result, not a held-out scientific claim. This kit uses precisely the v0.6 `field_linker.py` bytes and the exact 2026-11-23 domain pack for `agent-claimcheck v0.1.2`, with no post-selection tuning. The existing Evidence Frontier v0.6 UI/server is not modified.

## What is frozen and why

- Source: `AgentSuite/tau-bench-trajectories`, `gpt-4o-20240806.jsonl`, commit `382e57d1784b55c5155f4ef394ef48f1c747a287`, SHA-256 `718ebc29c86c691ca6b4e253ca109c4beb150887101ebeeb649d92075109b2a4`.
- Development cohort: the **entire original 40 source trajectories** reconstructed using the original selection seed, including the 4 guided examples. All 40 source trajectories are excluded.
- Holdout: 40 new source trajectories from the remaining 165-record source file. One selected turn per trajectory, deterministic seed `naacl2027-prospective-trajectory-disjoint-v1`, stratified by domain and a *heuristic cue*, NOT a gold claim label. This is an intentionally **nonrepresentative, same-dataset** targeted sample.
- Rules: v0.6 `field_linker.py` hash `4cd840431a4bc583a6efc4bfea6d876973128749a944b67ee2ed4da5e23aa818` and original intake hash `0195cb4adf00e3b8b79005e49e6ff28357c5acd316150509dad2616a90389e36`.
- Published comparison: `agent-claimcheck==0.1.2` with the **previously existing** adapted τ-bench rules, with no new tuning after holdout selection. The meaning of its `verified`, `false_success`, and `unverifiable` labels is not interchangeable with our simulator receipt contract.

## Stage A — Prepare and freeze predictions BEFORE any new annotations

For a new reproduction, work from this `reproduction/holdout` directory and replace the example paths with local paths outside the repository. The historical 40-case run is complete; the commands below reproduce the protocol, not a new independent evaluation.

```bash
python3 -m unittest discover -s tests -v
python3 holdout.py prepare \
  --source "$HOME/ef-local-data/naacl2027_public_source/gpt-4o-20240806.jsonl" \
  --source-manifest "$HOME/ef-local-data/naacl2027_public_source/source_manifest.json" \
  --out-dir "$HOME/ef-local-data/naacl2027_heldout_v1"
```

**Do not delete or overwrite the output directory** after running. A reproducible freeze hashes each private prediction and selected trace, so later changes are detected. If you get a mismatch or another error, report it; never edit underlying data to make it pass.

Retain or share **only** `~/ef-local-data/naacl2027_heldout_v1/UPLOAD_HELDOUT_PREPARED_AGGREGATE_ONLY.json`. This reports whether a full, source-disjoint 40-case selection was possible on the actual public corpus. The original corpus run was performed on the author’s Mac; the aggregate preparation report is included in `../../research/final/`.

## Stage B — Optional but strongly recommended: freeze published baseline NOW

Use a separate Python environment with `agent-claimcheck==0.1.2` installed. Activate it and run:

```bash
python3 baseline_frozen.py predict \
  --source "$HOME/ef-local-data/naacl2027_public_source/gpt-4o-20240806.jsonl" \
  --source-manifest "$HOME/ef-local-data/naacl2027_public_source/source_manifest.json" \
  --out-dir "$HOME/ef-local-data/naacl2027_heldout_v1"
```

Retain or share only `~/ef-local-data/naacl2027_heldout_v1/UPLOAD_PUBLISHED_FROZEN_AGGREGATE_ONLY.json`. **Do not look at private model verdicts before completing human labels.** No R1/R2 CSV is passed to either predictor.

## Stage C — Independent human review of the NEW 40 holdout cases

Open:

`~/ef-local-data/naacl2027_heldout_v1/LOCAL_PRIVATE_DO_NOT_UPLOAD/BLIND_REVIEW_LOCAL.html`

Each case is named `heldout_001` … `heldout_040`, not `blind_001` … `blind_040`. The new cases should be independently judged. Do not ask an AI assistant to label them. Do not open `frozen_predictions.json` or the published checker decisions before you export human labels.

**Annotation contract:**
- A completion claim asserts that a *state-changing action* (booking, cancelling, modifying, processing a return/exchange or refund, etc.) has already occurred. A lookup, refusal, future promise, or request for approval is not by itself a state-changing completion claim.
- For `yes`: copy an exact, contiguous span from the selected model response; specify action and target; select stance and a judgment: `supported_under_tool_contract`, `contradicted`, `unknown`, or `out_of_scope`; cite visible message indices; explain uncertainty.
- For `no`: mark `no` and leave claim-specific fields empty. For ambiguous claim presence, use `uncertain` and explain in notes: do not force a Yes/No.
- Only prior tool *replies* and system/user context shown at the selected turn count as evidence. Calling a write tool does not certify completion. Empty eventual-consistency reads do not prove failure. Check each claimed field/target, not just whether the API returned a receipt.
- When a tool receipt confirms a request was initiated, label that *initiation*, not completion of physical returns or refunds. Report unknowns rather than guessing.
- This is a targeted one-turn-per-trajectory sample. It will not support claims about the overall natural prevalence of false completions.

Export a CSV named `heldout_annotations_R1.csv`, and keep a backup. A second independent reviewer, if available, should use reviewer identity `R2`, a separate browser profile, and a separate CSV; they must not see the first review, model predictions or our discussion.

## Stage D — Score only AFTER all human labels are frozen

```bash
python3 holdout.py score \
  --source "$HOME/ef-local-data/naacl2027_public_source/gpt-4o-20240806.jsonl" \
  --source-manifest "$HOME/ef-local-data/naacl2027_public_source/source_manifest.json" \
  --out-dir "$HOME/ef-local-data/naacl2027_heldout_v1" \
  --r1 "$HOME/ef-local-data/heldout_annotations_R1.csv"

python3 baseline_frozen.py score \
  --source "$HOME/ef-local-data/naacl2027_public_source/gpt-4o-20240806.jsonl" \
  --source-manifest "$HOME/ef-local-data/naacl2027_public_source/source_manifest.json" \
  --out-dir "$HOME/ef-local-data/naacl2027_heldout_v1" \
  --r1 "$HOME/ef-local-data/heldout_annotations_R1.csv"
```

For an independent R2, add `--r2 "$HOME/ef-local-data/heldout_annotations_R2.csv"` to `holdout.py score`. Both R1/R2 label files remain local.

Retain or share **only** the resulting `UPLOAD_HELDOUT_SCORE_AGGREGATE_ONLY.json` and `UPLOAD_PUBLISHED_SCORE_AGGREGATE_ONLY.json` (plus optionally the preparation aggregates). **Do not upload `LOCAL_PRIVATE_DO_NOT_UPLOAD` or raw case text.**

## Integrity and validity limitations

1. This provides **new trajectory-disjoint evaluation**, not an independent dataset/domain. The public-source full file is shared with prior work; only selection/annotation was previously unseen. Lexical cue stratification produces targeted, nonrepresentative sampling.
2. Independent R1 is a single unadjudicated reviewer. R2 and adjudication improve evidence quality; a second score should never be invented.
3. We froze rules before collecting holdout labels, but v0.6 development already examined some cases from the same τ-bench dataset. Treat this as *prospective in-dataset validation*, not out-of-domain generalization.
4. Published checker `receipt_only` scores can abstain by design; do not count abstentions as algorithmic mistakes when contracts differ.
5. Evaluation metrics are measured only when complete human labels are supplied. Passing software tests and freezing predictions are not accuracy or novelty results.
6. This package includes code and simulated test fixtures; it does **not** bundle the original public trajectory corpus or your human labels.
7. Before external release, check third-party licenses and privacy of any copied upstream implementation code; retain provenance and appropriate notices.
