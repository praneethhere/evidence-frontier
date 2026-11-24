# Reproducibility guide

## Default offline installation

Python 3.10 or newer. From the repository root run `python3 verify_bundle.py`, `python3 -m unittest discover -s tests -v`, then `python3 server.py --port 8775`. Open `http://127.0.0.1:8775/#stress`. Stop with Ctrl-C. For the separate frozen holdout test suite, run `(cd reproduction/holdout && python3 -m unittest discover -s tests -v)`.

The default installation needs no dataset, network, keys, or paid service. The receipt stress test actually executes the two local implementations on a copy of a trace. Recorded LIMBO and evaluation panels are replays, not fresh agent runs. Original and guarded verdicts can both be wrong; UNKNOWN is not failure proof.

## Study boundaries

| Study | Scope | Result |
| --- | --- | --- |
| Development | 36 unguided turns; single R1; 4 guided cases excluded | F1 0.970, exploratory |
| Holdout | 40 trajectory-disjoint intermediate turns, same source, single R1 | F1 0.286 vs 0.333 adapted comparator; both miss 8 of 10 positives |
| Receipt audit and repair | 42 selected pairs, 28 trajectories; post-hoc | 126 dependent corrupted variants downgrade to Unknown; 42 formatting controls preserved; all 893 original verdicts unchanged |
| LIMBO | 16 deterministic scripted runs | 5 read-back positives; 0 full-task certifications under the stricter contract |

The 161 original receipts with both IDs present agreed. The guard is a targeted regression repair, not new independent accuracy evidence. Original labels have scope ambiguity and no R2 adjudication. The comparator is final-message oriented and its model-judge mode was not run. No user study or deployment validation is claimed.

## Optional source-based reconstruction

See README for pinned source download/intake. For receipt pairs only, use `python3 server.py --port 8775 --stress-source /absolute/path/gpt-4o-20240806.jsonl`. The exact source bytes are verified; no external service calls are made by the server. Original data may be displayed locally, so do not expose this server publicly.

To reproduce the receipt census and repair with independently obtained pinned source data, set `SRC` and `MANIFEST` to your local paths and `OUT` to a fresh directory outside this repository:

```sh
python3 NAACL2027_receipt_binding_audit.py --holdout-dir reproduction/holdout --source "$SRC" --manifest "$MANIFEST" --out "$OUT/audit"
python3 NAACL2027_receipt_binding_guard.py --holdout-dir reproduction/holdout --source "$SRC" --manifest "$MANIFEST" --prior-report "$OUT/audit/UPLOAD_RECEIPT_BINDING_AGGREGATE_ONLY.json" --out "$OUT/guard"
```

The aggregate outputs in `research/final/` are the original executed records, with SHA-256 manifests. `reproduction/holdout/` preserves the historical frozen protocol and commands; use the scripts from that directory and supply your own local source and annotation files. Historical paths in that README are examples from the author's run, not requirements. New reviewers will need to collect their own independent labels; exact published single-R1 scores cannot be independently recomputed from this public package alone because original labels and private predictions are withheld pending redistribution review. The source fetch workflow has not been independently tested from a new network environment.

The `data/evaluator_private/` directory contains only simulated evaluator-only outcomes, intentionally separate from agent-visible inputs; it is not a directory of personal or restricted reviewer data. Do not use those records as claim-time evidence.
