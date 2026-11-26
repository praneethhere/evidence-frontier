# Evidence Frontier: historical proposed annotation protocol

**Historical planning document.** The full proposed two-reviewer study and automatic probe-planning evaluation were not executed. Separate single-R1 development (36 scored cases) and trajectory-disjoint holdout (40 cases) studies were executed; see `research/final/` for frozen results. Do not treat this plan as a user study.

## Research question

Given a user task, a final natural-language agent report, and only the tool observations visible to the agent at finish time, does an evaluator recognize exactly which *asserted* task obligations are supported, unsupported, or not yet knowable? How often does a proposed next observation change that judgment while preserving correctness and avoiding unnecessary writes?

## Evaluation units

Each unit is `(task instruction, original agent response, original visible execution prefix, declared tool contract)`. Units must be from **actual recorded language-agent executions** (not our edited/scripted completions), with unique IDs and a separate evaluator-private after-settlement oracle.

## Human labeling policy

1. Annotators are blinded to fault mode, hidden future events, and outcome oracle.
2. Annotate each statement span's stance: `ASSERTED_COMPLETE`, `UNCERTAIN`, `NEGATED`, `PENDING`, `OTHER`, or `UNMAPPABLE`.
3. Link each asserted claim to the requested obligation(s); mark mismatched targets/recipients.
4. For each obligation, use `SUPPORTED`, `CONTRADICTED`, or `INSUFFICIENT_AT_CLAIM_TIME`. A timeout is **not** automatically contradicted.
5. Evidence must cite the exact agent-visible tool message IDs and timing. Annotate intended world-state constraints (e.g., exactly one email) separately from mere tool-return ACKs.
6. Record unresolved disagreement independently for two reviewers, then adjudicate. Report agreement before adjudication and retain blind review files.
7. Only after annotations freeze, reveal evaluator-private eventual outcomes. Do not use eventual success to redefine claim-time support.

## Required baselines and system comparison

- Naive finish-only acceptance (weak control).
- Claim-only language model judge with documented prompt/model/settings, **if resources allow**.
- Strong trace-aware existing system (e.g., agent-claimcheck): run the actual release with its native trace adapters, compare matched inputs and abstention assumptions. **Completed for the separate detection pilot and holdout using agent-claimcheck v0.1.2 shipped/adapted offline configurations; no model-judge or full per-obligation evaluation.**
- Evidence Frontier rule baseline and any proposed stronger extractor.
- Report claim span precision/recall/F1; mapping accuracy; per-obligation support/conflict/unknown macro F1; false-certification rate, appropriate abstention, coverage, runtime. Separate unsupported confidence from eventual failed task truth.
- Evaluate probe proposal quality only if a real executable, safe intervention adapter is implemented and compared against equivalent existing evidence interventions.

## Integrity and exclusions

No LLM prediction or human label can be inferred from three scripted episodes. Exclude traces without original messages or valid time cut. Do not substitute private oracle fields into evaluation input, or treat constructed data as observational data. Report sampling, denominators, selection criteria, adjudication decisions, and false positives.

## Ethical / data handling

Use synthetic or public tasks with permitted data. Do not publish real customer details, access tokens, or private employer logs. Disclose tool/LLM assistance per NAACL rules and evaluate any sensitive-task implications.
