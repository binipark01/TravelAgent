# Evidence Pipeline

1. Agent requests information through a tool.
2. Tool asks `SourceRegistry` for policy-approved sources.
3. Connector collects provider data.
4. Normalizer converts provider output into category-specific normalized data.
5. `EvidencePacket` is stored with source refs, confidence, freshness policy, and mock/live flags.
6. Agent consumes evidence and patches `TripPlanState`.
7. `PlanCriticAgent` checks missing, stale, simulated, or unsafe evidence before final presentation.

No raw scraped HTML should enter final prompts or final plan claims.
