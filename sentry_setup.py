"""Optional Sentry error monitoring configured through environment variables."""

import os


def init_sentry() -> bool:
    """Initialize Sentry when SENTRY_DSN is configured."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        send_default_pii=False,
    )
    return True
