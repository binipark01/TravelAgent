# Source Connectors

Configured source types:

- `official_api`
- `partner_api`
- configured `public_page`
- `mock` for dev/test/fallback only

Connector rules:

- use typed request/response models
- apply timeout and error handling
- never expose secrets in provider status
- return data that can be normalized into `EvidencePacket`

To add a connector, update `source_catalog.yaml`, implement the connector, add source policy tests, add mocked HTTP mapping tests, then wire it through a tool.

Accommodation source notes:

- Booking.com must go through `booking_demand` partner access; public challenge pages are not used as accommodation data sources.
- Agoda is registered as `agoda_partner`; public GraphQL/private endpoints are not treated as configured sources.
- Google Hotels uses Travel Partner API account credentials for partner data, not general consumer hotel search.
- Airbnb public pages stay disabled until explicit authorization is recorded; no automated collection is run by default.
