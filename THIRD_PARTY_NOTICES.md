# Third-party notices and data provenance

The root MIT license covers original Evidence Frontier software and author-created documentation, not third-party datasets or material subject to separate terms.

## LIMBO

Jiapeng Li (2026), *LIMBO: Benchmark code, harness adapters and episode traces*, version 1.0, https://github.com/jaxblack/limbo-bench. Source commit `2db09fba22a0572a70639162a808906409f612a8`.

- Upstream code: [MIT License](https://raw.githubusercontent.com/jaxblack/limbo-bench/2db09fba22a0572a70639162a808906409f612a8/LICENSE), copyright (c) 2026 Jiapeng Li. See `LICENSES/LIMBO-MIT.txt` for the retained notice.
- Upstream released episode records and generated paper outputs: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as specified in [DATA_LICENSE](https://raw.githubusercontent.com/jaxblack/limbo-bench/2db09fba22a0572a70639162a808906409f612a8/DATA_LICENSE).
- `data/` contains our separately executed scripted simulator runs, transformed into agent-visible and evaluator-only projections, plus provenance and hashes. These are not copied release episodes or real customer records. `pilot_results/` and `research/executed_probe_16.json` contain our derived descriptive outputs. Attribution is retained; LIMBO-derived record content is distributed under CC BY 4.0 to the extent applicable, not relicensed under MIT. No upstream endorsement is implied.

## AgentSuite / tau-bench

External source: https://huggingface.co/datasets/AgentSuite/tau-bench-trajectories, revision `382e57d1784b55c5155f4ef394ef48f1c747a287`, file `gpt-4o-20240806.jsonl`. No raw source conversations, case-level labels or case-level predictions are distributed. Dataset redistribution rights were not established; review source terms before optional local use. Aggregate measurements and independently authored analysis scripts are included. The root MIT license does not grant any rights in the external dataset.

## agent-claimcheck

External comparator: https://pypi.org/project/agent-claimcheck/0.1.2/ (version 0.1.2). No package binaries or upstream code are bundled. The reproduction workflow uses a separately installed comparator with our frozen adapter and domain rules. Consult upstream terms when installing it. The default workbench does not require this dependency.
