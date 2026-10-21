"""Permission tiers (SR-1). `classify()` for money actions arrives in Phase 5.1; this module holds
the tier enum and the ceiling for tools the LLM may run on its own."""

from enum import IntEnum


class Tier(IntEnum):
    T0 = 0  # auto: read-only analysis, checks, calculations, RAG
    T1 = 1  # auto + notice
    T2 = 2  # one-tap human approval
    T3 = 3  # OTP + 10-minute cooling-off


# P08: the agent may only run read-only tools. Anything above is refused by the registry guard
# with a structured "requires approval flow" error and never executes.
MAX_LLM_TOOL_TIER = Tier.T0
