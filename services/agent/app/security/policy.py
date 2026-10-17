"""Policy thresholds shared by the money services and (from Phase 5.1) the tier classifier.

Phase 5.1 owns this file; P13 only adds the constants the escrow service needs today.
"""

from decimal import Decimal

# SR-1: a Tier 1 (auto + notice) release is at most this much; above it is Tier 3.
TIER1_MAX_USD = Decimal("20000")
# SR-9: Tier 3 cooling-off window.
COOLING_OFF_MINUTES = 10
