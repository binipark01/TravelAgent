# Agent Runtime

`travel_agent/app/agent_core` contains the runtime boundary.

- `contracts.py`: BaseAgent, AgentResult, MissingField, SupervisorDecision
- `runtime.py`: run creation, continuation, event emission, evidence persistence
- `supervisor.py`: high-level supervisor decision model
- `event_bus.py`: ordered AgentEvent creation
- `checkpoint.py`: TripPlanState snapshot persistence
- `step_executor.py`: AgentStep lifecycle helper
- `tool_executor.py`: tool boundary export

The current MVP reuses existing deterministic domain planning code while routing run lifecycle, source discovery, evidence persistence, and provider policy through `AgentRuntime`.

Future live agents should keep the same contract: agents call tools, tools call connectors, connectors normalize into evidence.
