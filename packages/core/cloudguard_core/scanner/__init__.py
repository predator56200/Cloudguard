"""The scanner engine. Empty until M3 — the abstractions are already frozen in docs/03.

THE ONE-SENTENCE DESIGN:
    Collectors turn AWS into `Resource` objects; the engine evaluates pure `Rule` functions
    over those objects to produce `Observation`s; reconciliation (in `domain/`) turns
    `Observation`s into stateful `Finding`s.

THE PROPERTY EVERYTHING DEPENDS ON — I/O and logic are strictly separated:

    Collectors do I/O and NO logic.     (boto3, pagination, retries, normalisation)
    Rules do logic and NO I/O.          (pure functions: Resource -> Observation | None)

That separation is why 30 rules can be tested in milliseconds without touching a network, and
it is the difference between a scanner you extend fearlessly and one you're afraid of.

Arriving in M3:
    models.py      Resource, Observation, RuleContext, ResourceIndex  (frozen dataclasses)
    registry.py    @register decorator + lookup by ResourceType
    engine.py      RuleEngine.evaluate(resources, ctx) — pure
    aws.py         AwsCredentialBroker: STS AssumeRole, 15-min creds, NEVER persisted
    collectors/    s3, iam, ec2, security_groups
    rules/         the 30-rule catalogue
"""
