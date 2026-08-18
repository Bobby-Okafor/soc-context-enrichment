# Release Validation

This public mirror was validated against the synthetic corpus before publication.

## Publication gate results

- Python syntax/import execution: PASS
- Pytest: **87/87 PASS**
- Replay scenarios V01–V20: **20/20 PASS**
- Designated false associations: **0**
- Replay errors: **0**
- Demonstration-layer validation: **13/13 PASS**
- Demonstration-layer false associations: **0**
- Primary demo: PASS
- False-association demo: PASS
- Provider-failure demo: PASS
- Runtime dependency list: empty
- Fixture disclosure scan: no private names, absolute local paths, obvious credentials, API tokens, or private-key material found
- Final staged-tree disclosure scan: PASS

## Commands

```bash
python -m pytest -q
python -m context_enrichment validate --scenarios fixtures/scenarios
python -m context_enrichment demo-validate
python -m context_enrichment demo
python -m context_enrichment demo --scenario false-join
python -m context_enrichment demo --scenario provider-failure
```

These results validate only the deterministic behaviors represented by the synthetic corpus. They do not establish production scale, provider reliability, data governance, authorization semantics, or operational fit in a real environment.
