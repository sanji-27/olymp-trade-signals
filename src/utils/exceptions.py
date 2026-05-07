"""Custom exception types used across the bot."""


class DataStaleError(RuntimeError):
    """Raised when no ticks have arrived for too long."""


class AuthenticationError(RuntimeError):
    """Raised when broker auth (e.g. Olymp SSID) fails."""


class RiskBlockedError(RuntimeError):
    """Raised by the risk agent when a signal violates a hard rule."""
