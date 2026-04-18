# SeleneDB schema packs (pinned)

These JSON files define the operational-state node and edge types that
``openfdd_stack`` registers with SeleneDB on boot when
``OFDD_STORAGE_BACKEND=selene``.

## Source of truth

Upstream: [jscott3201/selenepack-smartbuildings](https://github.com/jscott3201/selenepack-smartbuildings)
— packs live at ``packs/hvac-fdd.json`` and ``packs/bacnet-driver.json``.

This directory holds a **pinned copy** checked into the stack repo so
deployments stay self-contained (air-gapped edge installs cannot fetch at
boot). See Decision D10 in the graph (node 10216).

## Sync policy

1. Upstream cuts a new release of the schema pack (e.g. v2.1.0).
2. Open a sync PR here that copies the JSON verbatim from that tag.
3. The stack's pack loader (``openfdd_stack/platform/selene/schema_pack.py``)
   registers each type and relationship idempotently on API boot.
4. Migration-breaking schema changes (removed fields, required-field
   additions) need a Phase-bump on the stack side before the sync lands.

## Pack contents (as pinned)

| Pack | Version | Types | Relationships |
|---|---|---|---|
| ``hvac-fdd.json`` | 2.0.0 | fault_rule, fault_event, energy_profile, suppression_group, site_config, fault_cluster, remediation_playbook, annotation, finding, proposal | hasFault, boundToRule, hasEnergyProfile, suppressedBy, triggeredBy, memberOf, hasPlaybook, configuredBy, hasAnnotation, relatedToFault, relatedToEquipment, hasConcept |
| ``bacnet-driver.json`` | 2.0.0 | data_source, protocol_network, bacnet_network, bacnet_object, protocol_object, bacnet_device | hasNetwork, hasDevice, exposesObject, protocolBinding, acquiredBy |

## Vocabulary (separate from these packs)

The Mnemosyne canonical vocabulary + Brick 1.4.4 + Haystack 4.0 + ASHRAE 223P
do **not** live here. They are delivered as a pre-ingested SeleneDB snapshot
image — see Decision D11 (graph node 10217).
