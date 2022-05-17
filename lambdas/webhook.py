import logging
import os

import sentry_sdk


def lambda_handler(event: dict, context: object) -> str:
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

    env = os.environ["WORKSPACE"]
    if sentry_dsn := os.getenv("SENTRY_DSN"):
        sentry_sdk.init(sentry_dsn, environment=env)
        logger.info(
            "Sentry DSN found, exceptions will be sent to Sentry with env=%s", env
        )

    return "Hello lambda!"
