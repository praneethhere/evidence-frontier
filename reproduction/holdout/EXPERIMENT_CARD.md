# Prospective evaluation card — frozen before new labels

**Question:** Does the v0.6 field-level claim/evidence linker detect model-generated state-changing completion claims and find cited contradictions or justified abstentions on **unseen source trajectories**?

**Primary metric:** Claim-presence precision/recall/F1 against independently authored human review; report confusion counts and class prevalence. Secondary: evidence-label cross-tab with coverage/abstentions and false certification counts (with narrowly specified tool-receipt semantics). No cherry-picked scores; retain unprocessable and unknown results in the denominator or separately account explicitly.

**Comparators:** Published `agent-claimcheck v0.1.2` shipped rules/cascade, plus its previously authored τ-bench adapted rules/cascade, all frozen before holdout labels. Their stricter state-probe/receipt thresholds are acknowledged. Comparisons on the same 40 source-disjoint cases; no apples-to-oranges significance claims.

**Data:** 165 GPT-4o τ-bench trajectories at pinned SHA; 40 original selected source trajectories entirely excluded; 40 new source trajectories, one hash-selected turn each, stratified by existing lexical cue and domain. Same model and dataset, no claim of population representativeness or out-of-domain robustness.

**Controls:** Exact source SHA pin; no hidden benchmark reward used; no observations after utterance cutoff; code/rules hashes checked; predicted outputs frozen before R1/R2; R1 and R2 blind to predictions; explicit record of abstentions. We do not claim a raw receipt establishes independent persistence, physical fulfillment, delivery, or exactly-once completion.

**Failure conditions:** Strong heldout degradation; inability to process common trace schemas; high unsupported certification; failure to detect independent contradictions; low interreviewer agreement; no defensible differentiation against prior art. Report these even if the result weakens the NAACL submission.

**Not addressed by this experiment:** automatic evidence selection/planning and actual agent-world interactive probes, human-usefulness study, novel methods versus AgentEval/Progress Drift/agent-claimcheck. Existing 16-run LIMBO probe replay is a separate controlled simulator result.

**Submission logistics:** NAACL 2027 System Demonstrations deadline Dec 4, 2026 AoE. Six content pages max; required video ≤2.5 minutes; accessible installation/demo. An empirical evaluation without novelty is not sufficient for acceptance.
