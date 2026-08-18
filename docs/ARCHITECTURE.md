# Architecture

## Problem

A security alert can be technically accurate while relevant operational context exists in separate systems. The difficult problem is not merely retrieval. It is determining whether a retrieved record is actually related to the alert, preserving why, and handling ambiguity or source failure without inventing certainty.

## Authoritative runtime sequence

1. Receive a raw alert.
2. Validate the intake envelope.
3. Normalize the alert into a canonical representation.
4. Resolve alert side entities.
5. Construct provider queries.
6. Query enabled context providers.
7. Capture provider results and diagnostics.
8. Normalize provider records.
9. Resolve context side entities.
10. Select candidates eligible for correlation.
11. Evaluate deterministic correlation features.
12. Produce relationship results.
13. Construct supporting and contradicting evidence.
14. Build the evidence set.
15. Assess relationship confidence.
16. Determine the enrichment execution state.
17. Assemble the `EnrichmentPacket`.
18. Return the deterministic packet.
19. Replay validation compares actual output with expected behavior.
20. The optional analyst assistant consumes the accepted packet downstream.

## Responsibility boundaries

### Providers

Providers retrieve raw records and provider health diagnostics. They do not normalize records, establish relationships, construct evidence, or assess confidence.

### Normalization

Normalization converts heterogeneous raw representations into canonical records. Timestamp quality is explicit. Missing, malformed, and ambiguous timestamps are not silently repaired.

### Entity resolution

Entity resolution handles exact canonical identity, explicit aliases, normalized host equivalence, ambiguity, mismatch, and unavailable values. Similarity alone is not enough.

### Candidate selection

Candidate selection decides whether a record is eligible for correlation. Selection is not relationship proof.

False association defenses prevent host only equality from overriding an explicit user mismatch and prevent user only equality from overriding an explicit host mismatch.

### Correlation

Correlation evaluates explicit features such as:

- user match
- host match
- action compatibility
- temporal relationship
- record state

The relationship result is one of:

- `SUPPORTED`
- `PARTIALLY_SUPPORTED`
- `CONTRADICTED`
- `NOT_SUPPORTED`

### Evidence

Evidence is the provenance bearing representation of correlation observations. Supporting evidence and contradicting evidence are separate. Missing information is not represented as contradiction.

### Confidence

Confidence describes trust in the relationship assessment:

- `HIGH`
- `MEDIUM`
- `LOW`
- `INSUFFICIENT_CONTEXT`

It does not mean malicious, benign, true positive, false positive, severity, or disposition.

### Execution state

The enrichment result distinguishes:

- `RELATED_CONTEXT_FOUND`
- `AMBIGUOUS_CONTEXT`
- `CONTRADICTORY_CONTEXT`
- `NO_RELIABLE_CONTEXT_FOUND`
- `PARTIAL_ENRICHMENT`
- `ENRICHMENT_FAILED`

A provider failure cannot be collapsed into “no context exists.”

## Assistant boundary

The analyst assistant is downstream of `EnrichmentPacket`.

```text
EnrichmentPacket
    ↓
AssistantRequest
    ↓
Deterministic intent policy
    ↓
Finite action plan
    ↓
Controlled tools
    ↓
AssistantTrace
    ↓
AssistantResponse
```

It cannot modify the authoritative packet, fabricate evidence, redefine confidence, suppress ambiguity, or perform response actions.

## Why this separation matters

The architecture is designed around four boundaries:

1. Retrieval is not relationship proof.
2. Missing evidence is not the same as unavailable evidence.
3. Relationship confidence is not alert disposition.
4. Narrative generation is not truth authority.
