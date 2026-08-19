def init_sentry(dsn: str | None, environment: str) -> None:
    if not dsn:
        return

    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=environment)
