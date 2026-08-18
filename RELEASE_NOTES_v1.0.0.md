# v1.0.0

First public reference release of the SOC Context Enrichment Prototype.

## Included

- deterministic alert intake and normalization
- deterministic user and host entity resolution
- synthetic ticket, change, identity, asset, and historical case providers
- candidate selection separated from correlation
- explicit relationship features
- provenance bearing supporting and contradicting evidence
- semantic relationship confidence
- explicit enrichment execution states
- V01 to V20 replay validation corpus
- false association defenses
- provider failure semantics
- bounded deterministic analyst assistant
- mandatory assistant trace
- optional presentation only model adapter
- primary, false join, and provider failure demos

## Core design boundaries

- retrieval does not establish a relationship
- missing evidence is distinct from unavailable evidence
- relationship confidence is not alert disposition
- assistant narration is downstream of deterministic evidence

## Non goals

This release is not a production SOC platform and does not include real enterprise connectors, production authentication, secrets management, deployment infrastructure, external model dependencies, autonomous disposition, or response automation.
