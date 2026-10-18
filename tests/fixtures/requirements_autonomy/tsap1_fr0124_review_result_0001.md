# TSAP1-FR-0124 — Review Result 0001

Review artifact written by the independent Standard Requirement Reviewer. It records the verification of one exact reviewed state so a human at Ready can see what was checked and what was concluded. It is immutable review history. The verdict is derived from the findings below, and the relations it confirms are not written to Fibery.

```json
{
  "review_result_version": "0.3",
  "iteration": 1,
  "requirement_id": "TSAP1-FR-0124",
  "reviewed_document_fingerprint": "111fb0de1990734872eb8af71921283024010e103c96b0d8b926f81e5debb6c1",
  "reviewed_process_iteration": 1,
  "reviewed_process_output_fingerprint": "111fb0de1990734872eb8af71921283024010e103c96b0d8b926f81e5debb6c1",
  "reviewed_normative_tree": {
    "normative_tree_version": 2,
    "requirement_id": "TSAP1-FR-0124",
    "root_document_id": "91c65bf0-bf36-4501-ad4d-b1b91692bbf1",
    "documents": [
      {
        "document_id": "91c65bf0-bf36-4501-ad4d-b1b91692bbf1",
        "parent_document_id": null,
        "name": "TSAP1-FR-0124 — Uniform 400 error response for every invalid request",
        "content_fingerprint": "111fb0de1990734872eb8af71921283024010e103c96b0d8b926f81e5debb6c1"
      }
    ],
    "normative_tree_fingerprint": "31bc5a771812d080fa2014cad40c4083981e14ca29465378215e6c0fbae02db1"
  },
  "derived_verdict": "NEEDS_WORK",
  "process_finding_verifications": [
    {
      "process_finding_index": 0,
      "outcome": "CONFIRMED",
      "severity": "WARNING",
      "reason": "TSAP1-FR-0123 (Applied) defines validity only as 'after standard URL decoding'. It carries none of the WHATWG form-urlencoded clarification: '&'-only splitting, skipping empty components, case-sensitive name, ';' not a separator, '+' as space, UTF-8 percent-decoding. That clarification decides that ?text=hello&, ?&text=hello, ?%74ext=hello and ?text=%41 are valid. Under FR-0123 those requests must receive 200. The shared validity partition is therefore refined in only one of the two complementary Requirements, and the two can be read divergently."
    }
  ],
  "relation_proposal_verifications": [
    {
      "kind": "AFFECTS",
      "requirement_id": "TSAP1-FR-0123",
      "outcome": "CONFIRMED",
      "reason": "This Requirement defines invalidity as the exact complement of the validity rule that FR-0123 uses to decide which requests receive 200. The parsing clarification here therefore fixes the boundary of FR-0123's success set."
    }
  ],
  "confirmed_relation_proposals": [
    {
      "kind": "AFFECTS",
      "requirement_id": "TSAP1-FR-0123",
      "outcome": "CONFIRMED",
      "reason": "This Requirement defines invalidity as the exact complement of the validity rule that FR-0123 uses to decide which requests receive 200. The parsing clarification here therefore fixes the boundary of FR-0123's success set."
    }
  ],
  "new_findings": [],
  "assessment": {
    "clarity": "Clear. The human product clarification makes 'standard URL decoding' unambiguous by referencing the WHATWG application/x-www-form-urlencoded parser. It also spells out the observable consequences: separators, empty components, '=' splitting, '+' handling, UTF-8 percent-decoding, repeated pairs and case-sensitive name. Every listed edge case checks correctly against that parsing. For example, ?text=%zz leaves '%zz' undecoded, which is not letters, and ?=x&text=hello yields two pairs. The WHATWG reference defines observable product semantics and is explicitly a human product decision, so it is not implementation leakage.",
    "completeness": "Complete at the Requirement level. It states the 400 status, the exact error body, the application/json declaration, the non-significance of JSON formatting, and the full validity rule whose complement defines invalidity. It covers every source-enumerated invalid category, and the clarification resolves the parsing boundary cases. Other paths and methods are out of scope per the source.",
    "atomicity": "Atomic. The single obligation is a uniform 400 error response for invalid requests to GET /v1/uppercase. The validity definition, parsing clarification and media type are facets of that one obligation.",
    "testability": "Testable by observation. Each enumerated request can be sent, and its status, declared media type and JSON members and values can be compared against the stated expectations, including the explicit valid and invalid edge-case lists.",
    "internal_consistency": "Consistent. The enumerated invalid categories, parsing clarification, acceptance examples and edge-case lists agree with each other. They also agree with the RAW source's validity rule and examples. The only alignment risk is external: FR-0123 does not carry the same clarification.",
    "acceptance_criteria": "Adequate at the observable-outcome level. The criteria reproduce the source examples (missing text, text=hello1, repeated text). They also cover empty value, 33+ letters, a non-letter character and an additional parameter, each with the identical body declared as application/json. They are supplemented by the clarified valid and invalid edge cases."
  }
}
```