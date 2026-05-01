from __future__ import annotations


class CancelledError(Exception):
    """Raised by engine functions when a caller-provided cancel_event is set."""
