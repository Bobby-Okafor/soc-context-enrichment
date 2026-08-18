# Demo Guide

The demo is designed to tell one engineering story across three cases:

**value → false association safety → provider degradation**

## Primary scenario

Run:

```bash
python -m context_enrichment demo
```

Focus on these terminal sections:

1. `ALERT`
2. `CONTEXT DISCOVERY`
3. `ENTITY RESOLUTION`
4. `CORRELATION`
5. `EVIDENCE`
6. `CONFIDENCE`
7. `ANALYST RESPONSE`

The point is that operational context is useful only after identity, action, time, state, and provenance survive deterministic evaluation.

## False association scenario

Run:

```bash
python -m context_enrichment demo --scenario false-join
```

Focus on:

```text
EXPLICIT_USER_MISMATCH
No qualifying evidence; no evidence was fabricated
NO_RELIABLE_CONTEXT_FOUND
```

The point is:

> Retrieved does not mean related.

## Provider failure scenario

Run:

```bash
python -m context_enrichment demo --scenario provider-failure
```

Focus on:

```text
PROVIDER_UNAVAILABLE
PARTIAL_ENRICHMENT
MEDIUM
```

The point is:

> Evidence absent does not mean evidence unavailable.

## Assistant workflow

The visible assistant plan demonstrates where agentic orchestration sits:

```text
Assistant intent
→ finite plan
→ controlled tools
→ AssistantTrace
→ analyst response
```

The assistant consumes already validated enrichment. It does not establish the relationship itself.

## Closing boundary

The prototype is synthetic and deliberately stops before production integration. It should be evaluated as an executable engineering pattern, not as a deployable SOC product.
