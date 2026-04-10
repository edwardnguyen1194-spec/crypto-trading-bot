"""
DEPRECATED: DualModeStrategy has been replaced by SmartStrategy.

This module is kept only for backward compatibility. It previously imported
`talib` (a C library not available in this environment). All talib imports
have been removed.

Use `smart_strategy.SmartStrategy` instead (5-strategy weighted composite
engine ported from the proven JS bot at 94.8% WR).
"""

import warnings
warnings.warn(
    "dual_mode_strategy is deprecated - use smart_strategy.SmartStrategy",
    DeprecationWarning,
    stacklevel=2,
)

from typing import Optional
from strategy import Signal
import config


class DualModeStrategy:
    """DEPRECATED stub. Use SmartStrategy from smart_strategy instead."""

    def __init__(self, client):
        self.client = client
        warnings.warn(
            "DualModeStrategy is deprecated. Use smart_strategy.SmartStrategy",
            DeprecationWarning,
            stacklevel=2,
        )

    def analyze(self, symbol: str) -> Optional[Signal]:
        """Returns None - this strategy is deprecated."""
        return None

    def scan_all_pairs(self) -> list:
        return []
