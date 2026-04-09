"""VM state models."""
from __future__ import annotations

from enum import IntEnum


class VMState(IntEnum):
    BOOTING = 0
    READY = 1
    BUSY = 2
    DESTROYED = 3
