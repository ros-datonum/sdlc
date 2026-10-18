# TSAP1-FR-0124 — Process Result 0001

Process artifact written by the Standard Requirement Processor. It records the validated normalization and analysis of one processing iteration so a retry can resume without asking the model again. It is immutable process history, and the relations it proposes are not written to Fibery.

```json
{
  "process_result_version": "0.3",
  "iteration": 1,
  "requirement_id": "TSAP1-FR-0124",
  "input_fingerprint": "39669e1a9423f88af212fb5da68a5aa3d578a407cbe0e4fcd8bb34fb64610179",
  "output_fingerprint": "111fb0de1990734872eb8af71921283024010e103c96b0d8b926f81e5debb6c1",
  "normative_input_tree": {
    "normative_tree_version": 2,
    "requirement_id": "TSAP1-FR-0124",
    "root_document_id": "91c65bf0-bf36-4501-ad4d-b1b91692bbf1",
    "documents": [
      {
        "document_id": "91c65bf0-bf36-4501-ad4d-b1b91692bbf1",
        "parent_document_id": null,
        "name": "TSAP1-FR-0124 — Uniform 400 error response for every invalid request",
        "content_fingerprint": "39669e1a9423f88af212fb5da68a5aa3d578a407cbe0e4fcd8bb34fb64610179"
      }
    ],
    "normative_tree_fingerprint": "0f13b525b5fc0f3879d82fcccf11dcf932c95035161ca44060674d2edd4fb4ca"
  },
  "normative_output_tree": {
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
  "normalized_requirement": {
    "title": "Uniform 400 error response for every invalid request to GET /v1/uppercase",
    "requirement": "Every request to GET /v1/uppercase that is not valid must receive HTTP status 400 and the JSON body {\"error\": \"invalid_text\"}, identical for every kind of invalid input.",
    "detailed_behavior": "A request is invalid unless its query string, after standard URL decoding, contains exactly one parameter, named \"text\", whose value is 1 to 32 ASCII letters (A to Z and a to z). Invalid requests include a missing \"text\" parameter, an empty value, a value longer than 32 characters, a value containing any character that is not an ASCII letter, a repeated \"text\" parameter and any additional query parameter.\n\nAs a human product clarification of standard URL decoding, the query string is interpreted as the application/x-www-form-urlencoded parser of the WHATWG URL Standard (section 5.1) defines: it is split into components on \"&\" only; empty components are skipped; each component is split at its first \"=\"; a component without \"=\" has an empty value; \"+\" becomes a space; names and values are percent-decoded as UTF-8; repeated parameters remain separate name-value pairs; and \";\" is not a separator. The request is valid only when this yields exactly one name-value pair whose decoded name is exactly \"text\" (case-sensitive) and whose decoded value is 1 to 32 ASCII letters.\n\nThe error response is declared as JSON (application/json). Whitespace and other formatting inside the JSON body are not significant; only the members and their values are.",
    "rationale": "Every invalid request receives the same predictable error response.",
    "acceptance_verification": "GET /v1/uppercase returns HTTP 400 with {\"error\": \"invalid_text\"}. GET /v1/uppercase?text=hello1 returns HTTP 400 with {\"error\": \"invalid_text\"}. GET /v1/uppercase?text=a&text=b returns HTTP 400 with {\"error\": \"invalid_text\"}. Requests with an empty value, a value of 33 or more letters, a value containing a character that is not an ASCII letter, or an additional query parameter each return HTTP 400 with the same body, declared as application/json.",
    "constraints_edge_cases": "The error body is identical regardless of which validity rule was violated; no distinction between kinds of invalid input is exposed. Under the clarified parsing, GET /v1/uppercase?text=hello&, ?&text=hello, ?%74ext=hello and ?text=%41 are valid, and ?text, ?Text=hello, ?text=, ?text=hello1, ?text=a&text=b, ?text=a;b, ?text=%zz and ?=x&text=hello are invalid.",
    "non_goals": "Handling non-ASCII text or values longer than 32 characters beyond rejecting them.",
    "open_questions": "None."
  },
  "analysis": {
    "completeness": "Complete at the Requirement level. It states the error status, the exact error body, the media type declaration, the full definition of invalidity (as the complement of the shared validity rule) and the enumerated invalid categories from the RAW source. It also includes a human clarification that makes the parsing of the query string unambiguous. Other methods and paths are out of scope per the RAW source and TSAP1-FR-0123.",
    "clarity": "Clear. The human clarification removes the ambiguity of 'standard URL decoding' covering separators, empty components, '+' handling, percent-decoding, case-sensitivity of the name and repeated parameters. The worked valid and invalid examples agree with that parsing. ?text=%zz is invalid because the undecodable '%' stays in the value and is not an ASCII letter. The WHATWG reference is an explicit product-level definition of observable parsing semantics, not an implementation choice, so it is kept and not treated as leakage.",
    "atomicity": "Atomic. The single obligation is a uniform 400 response for invalid requests; the validity definition and media type declaration are facets of that obligation.",
    "testability": "Testable by observation. Each listed request can be sent, and its status, declared media type and JSON members and values can be checked against the stated expectations.",
    "internal_consistency": "Consistent. The enumerated invalid categories, the parsing clarification, the acceptance examples and the valid/invalid edge-case list all agree. They also match the RAW source's validity rule and examples."
  },
  "findings": [
    {
      "kind": "POSSIBLE_CHANGE",
      "requirement_id": "TSAP1-FR-0123",
      "detail": "TSAP1-FR-0123 (Applied) defines validity only as 'after standard URL decoding'. This Requirement adds a human product clarification of that phrase: WHATWG application/x-www-form-urlencoded parsing, with '&'-only splitting, empty components skipped, a case-sensitive name and ';' not a separator. The clarification also decides which requests are valid and so receive 200, for example ?text=hello&, ?&text=hello, ?%74ext=hello and ?text=%41. TSAP1-FR-0123 does not carry it, so the shared validity rule is now refined in only one of the two complementary Requirements. TSAP1-FR-0123 may need the same clarification to stay aligned."
    }
  ],
  "proposed_relations": [
    {
      "kind": "AFFECTS",
      "requirement_id": "TSAP1-FR-0123",
      "rationale": "This Requirement's parsing clarification fixes which requests are valid. Valid requests are exactly those that TSAP1-FR-0123 must answer with HTTP 200 and the uppercase body. Invalid requests here and valid requests there are complementary partitions of the same rule."
    }
  ]
}
```