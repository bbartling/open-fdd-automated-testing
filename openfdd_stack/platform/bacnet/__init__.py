"""BACnet driver — rusty-bacnet backed, BACnet/IP first, BACnet/SC forward-compatible.

Greenfield rewrite of the platform's BACnet integration. The old
``drivers/bacnet.py`` (JSON-RPC against the sibling ``diy-bacnet-server``
container) is retired in favour of an embedded driver backed by
`rusty-bacnet <https://github.com/jscott3201/rusty-bacnet>`_ (PyO3
wrapper over a full ASHRAE 135-2020 stack in Rust).

Public surface (kept small):

- :class:`BacnetDriver` — orchestrator; user code talks to this
- :class:`Transport` + :class:`BipTransport` — pluggable transport layer
  so a future :class:`ScTransport` drops in without touching discovery /
  scrape / graph code
- :class:`DiscoveredDevice` / :class:`DiscoveredObject` — plain dataclass
  results returned from discovery; insulates callers from
  ``rusty_bacnet.*`` types
- Typed errors: :class:`BacnetError` + specialised subclasses so callers
  can distinguish timeouts from unreachable devices from decode failures

Everything here is ``async``. Callers drive the driver from FastAPI route
handlers (already async) or from CLI harnesses via ``asyncio.run``.

Graph writes land in SeleneDB as ``:bacnet_device`` / ``:bacnet_object``
nodes per ``config/schema_packs/bacnet-driver.json``. No Postgres rows
for discovered state — Phase 2 is graph-first.
"""

from openfdd_stack.platform.bacnet.bip import BipTransport
from openfdd_stack.platform.bacnet.driver import BacnetDriver
from openfdd_stack.platform.bacnet.errors import (
    BacnetAbortedError,
    BacnetDecodeError,
    BacnetDriverError,
    BacnetError,
    BacnetProtocolError,
    BacnetRejectedError,
    BacnetTimeoutError,
    BacnetUnreachableError,
)
from openfdd_stack.platform.bacnet.object_types import (
    OBJECT_TYPE_TO_CURIE,
    curie_for_object_type,
)
from openfdd_stack.platform.bacnet.scrape import (
    BacnetScraper,
    ScrapeBinding,
    ScrapePlan,
    ScrapeResult,
    load_scrape_plan,
)
from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    DiscoveredObject,
    PropertyRead,
    PropertyReadResult,
    Transport,
)

__all__ = [
    # Orchestrator
    "BacnetDriver",
    # Scrape surface
    "BacnetScraper",
    "ScrapeBinding",
    "ScrapePlan",
    "ScrapeResult",
    "load_scrape_plan",
    # Transport layer
    "Transport",
    "BipTransport",
    "DiscoveredDevice",
    "DiscoveredObject",
    "PropertyRead",
    "PropertyReadResult",
    # Errors
    "BacnetError",
    "BacnetDriverError",
    "BacnetTimeoutError",
    "BacnetUnreachableError",
    "BacnetProtocolError",
    "BacnetRejectedError",
    "BacnetAbortedError",
    "BacnetDecodeError",
    # Object-type vocabulary (Mnemosyne alignment)
    "OBJECT_TYPE_TO_CURIE",
    "curie_for_object_type",
]
