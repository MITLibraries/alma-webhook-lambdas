import json
import logging
import os

import sentry_sdk


def lambda_handler(event: dict, context: object) -> dict[str, object]:
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)

    env = os.environ["WORKSPACE"]
    if sentry_dsn := os.getenv("SENTRY_DSN"):
        sentry_sdk.init(sentry_dsn, environment=env)
        logger.info(
            "Sentry DSN found, exceptions will be sent to Sentry with env=%s", env
        )

    logger.debug(json.dumps(event))

    base_response = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
    }

    request_type = event["requestContext"]["http"]["method"]
    if request_type == "GET":
        result = handle_get_request(event)
    else:
        result = {
            "statusCode": 405,
            "body": "HTTP method not allowed. Only GET requests are supported.",
        }

    return base_response | result


def handle_get_request(event: dict) -> dict[str, object]:
    try:
        challenge_secret = event["queryStringParameters"]["challenge"]
    except KeyError:
        return {
            "statusCode": 400,
            "body": "Malformed request, 'challenge' query parameter required",
        }
    return {
        "statusCode": 200,
        "body": challenge_secret,
    }
