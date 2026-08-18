# Trust Boundaries

This project deliberately puts the hardest trust decisions before the analyst assistant.

## Retrieved does not mean related

A provider can return a record because it is textually or structurally plausible. Candidate selection and correlation still have to establish a safe relationship.

## Evidence absent does not mean evidence unavailable

A successful empty provider result and a provider failure carry different semantics. Collapsing them would create false confidence.

## Relationship confidence does not mean alert disposition

Confidence describes trust in the operational context relationship. It does not label the alert malicious, benign, true positive, false positive, severe, or safe to close.

## Agent explanation does not equal truth authority

The assistant can inspect and explain an accepted packet. It cannot alter the packet's correlation, evidence, confidence, ambiguity, provider diagnostics, or execution state.

## Model adapter

The optional model adapter is presentation only. The default release uses no model. If a future adopter enables a model, structured packet facts remain authoritative.
