"""Placeholder: canonical event contract.

The canonical event contract is the single shared definition used by the
MQL5 bridge (producer), collector (consumer), and analytics consumers.
It is NOT defined at bootstrap time: plumbing the exact fields would
invent decisions that belong to the approved measurement specification.

Planned (subject to specification, not implemented here):

* an event envelope (metadata + payload)
* the per-event payload shape produced by the MQL5 bridge
* versioning of the contract

JSON Schema placeholder: ``shared/schemas/event.schema.json``.
"""

__all__: list[str] = []
