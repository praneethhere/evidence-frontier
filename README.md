# Evidence Frontier

Praneeth Kodumagulla · Independent Researcher

A local interactive workbench for inspecting claim-time evidence and stress-testing the receipt binding of a restricted rule-based verifier. Research artifact version 1.0.0. This is an experimental verifier diagnostic tool, not a claim of scientific superiority or an accepted publication.

## Quick start (Python 3.10+, standard library only)

From this directory:

```sh
python3 verify_bundle.py
python3 -m unittest discover -s tests -v
python3 server.py --port 8775
```

Open http://127.0.0.1:8775/ in a browser. The app binds only to loopback. No model API, simulator tool execution, account, external services or private dataset is required. The default shows authored synthetic receipt examples, three recorded scripted LIMBO episodes, recorded aggregate experiments, and the negative frozen holdout. Select each receipt condition to execute the original frozen verifier and the original guard on a trace copy. The airline fixture illustrates a case where the original verifier already detects the wrong target. The application is not designed for public internet hosting; local source mode can display original conversation content.

## Optional pinned model traces (local only)

The AgentSuite τ-bench trajectory source is not distributed here. Its redistribution license has not been established; review its terms before downloading or using the source. No raw trajectory, verbatim reviewer label, or case-level prediction is included. The optional local data retrieval checks the exact SHA-256 and refuses changed bytes. The dataset's published revision is referenced but remote download has not been tested in the release environment. Choose an external data directory, not this repository:

```sh
python3 fetch_pinned_source.py --destination "$HOME/ef-local-data/source" --confirm-local-use
python3 turn_intake_pinned.py --input "$HOME/ef-local-data/source/gpt-4o-20240806.jsonl" --source-manifest "$HOME/ef-local-data/source/source_manifest.json" --out-dir "$HOME/ef-local-data/intake"
python3 server.py --port 8775 --source "$HOME/ef-local-data/source/gpt-4o-20240806.jsonl" --private-dir "$HOME/ef-local-data/intake/REVIEW_LOCAL_PRIVATE" --census "$HOME/ef-local-data/intake/UPLOAD_THIS_CENSUS_ONLY.json"
```

The real explorer reconstructs the original 36 unguided cases. The stress panel additionally reconstructs the 42 receipt/action pairs from the pinned source and verifies the original audit counts before making them available. You can use `--stress-source /path/to/gpt-4o-20240806.jsonl` alone to load only the 42 receipt pairs. R1 reveal is disabled unless you explicitly provide your own original annotation CSV with `--annotations`. Do not publish raw data, local case directories or verbatim labels by default. No external inference is performed.

## Reproducibility and limitations

- `field_linker.py`, `turn_intake_pinned.py`, and the two receipt scripts retain their original hashes. `stress.py` invokes the original guard rather than rewriting its rules.
- `research/final/` contains unchanged aggregate reports and a hash manifest. The app's results table is read from those reports. Count-based F1 is zero when there are positive reference labels but no predicted positives; precision is undefined in that setting.
- `reproduction/holdout/` preserves the frozen holdout workflow and the adapted baseline configuration. Baseline execution requires the original `agent-claimcheck==0.1.2` environment; not necessary for the interactive demo. Refer to its README for commands. The receipt scripts accept `--holdout-dir reproduction/holdout` and explicit source/manifest paths; the guard also needs the original audit report. Outputs are local and should be stored outside this repository.
- 36 development cases, 40 trajectory-disjoint holdout cases (single reviewer; scope ambiguity), and 42 post-hoc receipt pairs (28 trajectories) are separate studies. The holdout F1 is 0.286 versus 0.333 for the adapted baseline. 126 dependent corrupted receipt variants changed to Unknown with the guard. This is a scoped regression check, not independent validation, model accuracy, persistent-state proof or a user study.
- LIMBO panels replay recorded experiments; the receipt panel reruns local code, not agent or tool actions.

## License and attribution

Original Evidence Frontier code and author-created documentation are licensed under the [MIT License](LICENSE). The bundled LIMBO-derived scripted records have separate provenance and notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No license to the separately obtained AgentSuite source data is granted here.

## Research status and reproducibility

See [documentation errata](DOCUMENTATION_ERRATA.md) for the documentation-only update and exact v1.0.0 implementation scope.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for study boundaries and commands. This artifact is intended for research and debugging, not production authorization or proof of real-world task success. The paper is being prepared for submission; no acceptance or peer-review outcome is claimed. Generative AI assisted code, interface, documentation and manuscript development; the author executed the reported experiments and reviewed the research outputs.
