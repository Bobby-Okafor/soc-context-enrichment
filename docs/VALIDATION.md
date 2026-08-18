# Validation

The project is validated with deterministic synthetic scenarios rather than production data.

## Replay corpus

The V01 to V20 corpus covers:

| ID | Scenario | Expected behavior |
|---|---|---|
| V01 | Exact operational match | Related context, high confidence |
| V02 | Valid user alias | Explicit alias accepted |
| V03 | FQDN host normalization | Host equivalence accepted |
| V04 | Similar username | False join rejected |
| V05 | Same user, unrelated host | Relationship rejected |
| V06 | Same host, different user | Relationship rejected |
| V07 | Stale operational record | Relationship rejected |
| V08 | Approved matching change | Related context |
| V09 | Cancelled matching change | Contradictory context |
| V10 | Contradictory activity | Contradictory context |
| V11 | Missing timestamp | Degraded confidence |
| V12 | Malformed timezone | Degraded confidence |
| V13 | Competing tickets | Ambiguous context |
| V14 | Historical case | Context preserved without treating history as authorization |
| V15 | No related context | No reliable context found |
| V16 | Provider unavailable | Partial enrichment |
| V17 | Malformed provider record | Bounded degradation |
| V18 | Duplicate records | No evidence inflation |
| V19 | Identity event contradicts ticket | Contradictory context |
| V20 | Replay determinism | Repeated output remains deterministic |

## Safety properties

The demonstration layer validates that:

- confidence cannot be modified by the assistant
- evidence cannot be fabricated
- `NOT_SUPPORTED` cannot become support
- `CONTRADICTED` cannot become support
- provider failure cannot become successful evidence absence
- ambiguity cannot be silently removed
- presentation adapters cannot mutate packet authority
- relationship claims retain evidence references
- identical requests and packets produce deterministic authoritative output

## Run validation

```bash
python -m pytest -q
python -m context_enrichment validate --scenarios fixtures/scenarios
python -m context_enrichment demo-validate
```

## Interpreting the results

The validation corpus proves only the behaviors represented by the synthetic scenarios. It does not establish production source quality, scale, authorization semantics, provider reliability, data governance, or operational fit in a real environment.
