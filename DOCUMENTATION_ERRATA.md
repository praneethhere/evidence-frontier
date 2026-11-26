# Documentation errata (v1.0.1 candidate)

The executable artifact and recorded results are those of v1.0.0, commit `67e36c6a30f811d4b123d7b5f836e20743002835`. This update changes documentation only. No frozen source, test, result, historical protocol or underlying data has been changed. The original v1.0.0 tag remains immutable.

- The historical R1 holdout is complete, not pending: EF F1 0.286, adapted Agent-ClaimCheck F1 0.333. Neither generalization nor comparative utility is demonstrated.
- The nested `reproduction/holdout/FILE_SHA256_MANIFEST.json` is the historical kit manifest. Its README and reporting-template hashes refer to the original documents at v1.0.0; use the top-level publication manifest to verify the updated documents. The original code hashes and pre-registered protocol remain unchanged.
- The identity guard has a nine-name allowlist, not nine verified benchmark operations. It checks cited request/receipt identifiers only for mapped tools and downgrades Supported to Unknown; existing Contradicted verdicts are unchanged. The default synthetic reservation example illustrates this legacy behavior.
- The original-model explorer loads the 36 development cases only, with reviewer labels optional; holdout results are aggregate-only.
- The default browser is the same implementation and displays v1.0.0. The corrected documentation does not require a new screencast.
