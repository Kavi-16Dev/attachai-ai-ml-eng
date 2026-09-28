"""Provider-neutral error types for the extraction pipeline.

Kept out of any specific provider module so the router and tests don't
depend on which LLM vendor is behind the client.
"""


class TransientLLMError(Exception):
    """Retryable: rate limit, timeout, connection error, or 5xx."""


class PermanentLLMError(Exception):
    """Not retryable: bad request, auth/quota failure, refusal, or
    unparseable/invalid model output. Also what a transient error becomes
    once the retry budget is exhausted."""
