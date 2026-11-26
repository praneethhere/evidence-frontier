# Historical study reporting and completed holdout results

## Development pilot (already executed, NOT held-out)

On 36 source-verified, purposively selected agent utterances from the AgentSuite τ-bench GPT-4o release, a single human reviewer identified 16 action-completion claims. Our restricted rule-based linker found all 16 but marked one of the 20 nonclaims as a completion claim (P = 94.12%, R = 100%, F1 = 96.97% relative to that one reviewer). Of the 16 claimed actions, the system matched R1's tool-contract evidence judgments in 12 and abstained on 4 cases. **This is a development-set diagnostic:** part of the reviewer examples were inspected before the rule system was implemented. No adjudicated gold standard or independent generalization score exists for that cohort.

## Prospective, same-corpus trajectory-disjoint holdout (COMPLETED)

The 40-case holdout is complete. EF TP=2, FP=2, FN=8, TN=28 (precision 0.50, recall 0.20, F1 0.286). Adapted Agent-ClaimCheck TP=2, FP=0, FN=8, TN=30 (F1 0.333); shipped modes detect no claims. Both adapted methods miss the same eight positives. R1 is the sole reviewer, with scope ambiguity. No R2 agreement or adjudication is available. See the frozen aggregate reports in `../../research/final/`. Original prospective reporting requirements: (a) original 40 trajectory IDs excluded by source line; (b) new selected count and domain/cue composition; (c) independent R1 and optional R2 counts, agreement, uncertain labels; (d) exact TP/FP/TN/FN and precision/recall/F1; (e) matched published baseline results under their own receipt/probe semantics; (f) abstentions/unsupported certification and claim-evidence mismatch analysis, including failures.

If the heldout results are materially worse than development, say so plainly and revise the proposed method. If zero contradictions occur, say that the sample is uninformative for contradiction sensitivity. This study cannot by itself establish novelty, representativeness, external validity, user-study gains, or actionable evidence-planning improvement.

## Closest prior art and boundary

- Zhang & Ma, *Progress Drift: Auditing False Progress in Long-Horizon LLM Agents* (AACL 2026): claim-level evidence alignment and progress ledger already established.
- *AgentEval: Evidence-Bounded Assessment of Stateful Agents* (2026 preprint): evidence-bounded assessment and controlled interventions already studied.
- *agent-claimcheck* v0.1.2: existing claim-to-receipt/state-probe rules, abstentions, dashboard, and trained classifier. Report v0.1.2 shipped configuration and separately identify previously developed τ-bench rule adaptation. Its receipt-only abstention is deliberate, not necessarily a false alarm.

The scope of novelty remains narrow; integration is the system contribution, not a new general verification principle. The system-demo value proposition may emphasize source-verifiable, claim-time trace inspection and reproducible local human/automatic evidence judgments, but it must still substantiate comparative research utility and licensing before a NAACL paper is ready.
