"""Custom exceptions for Talkie."""


class TalkieError(Exception):
    """Base exception for all Talkie errors — caught by the pipeline and surfaced to the user."""

    pass


class TalkieAPIError(TalkieError):
    """Error communicating with an external API (STT or LLM)."""

    def __init__(self, message: str, provider: str = "", original: Exception | None = None) -> None:
        self.provider = provider
        self.original = original
        super().__init__(message)


class TalkieConfigError(TalkieError):
    """Configuration error (missing key, invalid value, etc.)."""

    pass
