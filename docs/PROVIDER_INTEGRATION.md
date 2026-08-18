# Provider Integration

## Contract before vendor

The included providers represent generic source roles. They do not assume that a real environment uses any particular vendor or even the same number of systems.

Conceptually, a provider exposes:

```text
health_check()
search(ProviderQuery) -> ProviderResult[RawProviderRecord]
retrieve(record_id) -> ProviderResult[RawProviderRecord]
```

A `ProviderResult` distinguishes:

- `SUCCESS`
- `PARTIAL`
- `FAILED`

A failure must remain an explicit diagnostic. It must not be represented as a successful empty result.

## Included synthetic roles

- ticket
- change
- identity
- asset
- historical case

Historical case context is intentionally not treated as current authorization.

## Safe replacement sequence

1. Implement a provider behind the provider boundary.
2. Preserve native record identity, source schema version, raw values, and retrieval metadata.
3. Return raw records plus structured provider diagnostics.
4. Add normalization mappings separately.
5. Add deterministic fixture backed contract tests.
6. Validate success, partial failure, complete failure, schema drift, missing fields, duplicate identifiers, and timestamp quality.
7. Run candidate, correlation, evidence, confidence, replay, false association, assistant, and integration tests.

A provider should never become the owner of normalization, entity resolution, correlation, evidence, confidence, or assistant truth authority.

## Real integrations

Production integrations require organizational authorization, authentication, least privilege, secrets management, audit controls, privacy policy, rate limiting, timeouts, resilience, schema governance, and operational ownership.
