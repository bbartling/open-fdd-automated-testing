# Graph Query Patterns

Document query intent and expected fields, not static hardcoded result sets.

## Questions the graph should answer

- Which points belong to this equipment?
- Which BACnet device does this equipment/point belong to?
- Which Brick classes are present on this device?
- Which rule inputs can be satisfied by this equipment/device?
- Which faults are applicable based on modeled points and rule inputs?
- Which point identities should appear in provenance for a given fault result?

## Query categories

- site -> equipment
- equipment -> points
- point -> Brick class
- point -> BACnet reference (`bacnet_device_id`, `object_identifier`, `object_name`)
- point -> semantic mapping (`rule_input`, `fdd_input`, `mapsToRuleInput`)
- device -> applicable faults through modeled points + YAML requirements

## Expected output fields

For device/fault applicability checks:
- `site_id`, `site_name`
- `bacnet_device_id`
- `equipment_ids`, `equipment_names`
- `applicable_fault_ids`
- `active_fault_ids`
- `matched_points_by_fault` with point identity fields

## MCP usage note

Prefer graph-backed APIs and model queries first; runtime-only rows are overlays, not primary applicability truth.
