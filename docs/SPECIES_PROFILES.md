# Species profiles

Species profiles provide versioned, reusable species defaults without coupling
the domain to Home Assistant devices or entities. They are reference data, not
individual reptile records and not a substitute for keeper judgment.

## Scope

A `SpeciesProfile` identifies a species and may provide reviewed environmental
targets, future CareTask template identifiers, and supporting references. A
`Reptile` remains the durable record for an individual animal. Future
CarePlans may adopt profile defaults and then preserve reptile-specific choices
independently.

Profiles do not contain sensor entity IDs, device IDs, enclosure assignments,
or live measurements. Home Assistant adapters will map domain target IDs to
entities in a later milestone.

## Identifiers and versions

Profile IDs are stable lowercase namespaced identifiers such as
`builtin:gargoyle_gecko`. The schema version describes the serialized document
shape. The profile version identifies a revision of the content within that
schema. Both versions are positive integers.

Built-in profiles live in `custom_components/reptilecare/profiles` as JSON
resources. The registry loads and validates every bundled document during
config-entry setup. Unknown fields, malformed ranges, unsupported schema
versions, duplicate IDs, and invalid references stop loading with a clear
error; profile data is never silently ignored.

## Environmental targets

`EnvironmentalTarget` is intentionally generic. Its stable `target_id`, range,
warning bounds, display name, and explicit unit can describe temperature,
humidity, or future measurements without embedding Home Assistant concepts.
Warning bounds, when present, must enclose the recommended range.

Environmental recommendations are husbandry guidance and require reviewed,
traceable sources. The initial Gargoyle Gecko profile contains species identity
only. Environmental ranges, CareTask templates, and references will be added
after the project establishes and completes its source-review process.

## References

`ProfileReference` records a title, publisher, absolute HTTP(S) URL, optional
publication date, and optional notes. References explain the basis for profile
content. Runtime loading is local and never performs network requests.

## Serialization and compatibility

Serialization is explicit through `species_profile_to_dict` and
`species_profile_from_dict`. The current reader supports schema version 1 and
rejects unknown fields so accidental schema changes cannot enter published
profiles unnoticed. Future schema versions must introduce an intentional
migration or compatibility policy before being accepted.

Model collections are copied into immutable tuples. Registry output is sorted
by profile ID, making lookups and tests deterministic.
