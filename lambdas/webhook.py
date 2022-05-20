import base64
import hmac
import json
import logging
import os

import sentry_sdk

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def lambda_handler(event: dict, context: object) -> dict[str, object]:
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

    request_method = event["requestContext"]["http"]["method"]
    if request_method == "GET":
        result = handle_get_request(event)
    elif request_method == "POST":
        result = handle_post_request(event)
    else:
        logger.warning(
            "Received invalid HTTP request method %s, returning 405 error response.",
            request_method,
        )
        result = {
            "statusCode": 405,
            "body": f"HTTP method {request_method} not allowed. Supported methods: "
            "GET, POST.",
        }

    return base_response | result


def handle_get_request(event: dict) -> dict[str, object]:
    try:
        challenge_secret = event["queryStringParameters"]["challenge"]
    except KeyError:
        logger.warning(
            "Received GET request without 'challenge' query parameter, returning "
            "400 error response."
        )
        return {
            "statusCode": 400,
            "body": "Malformed request, 'challenge' query parameter required.",
        }
    logger.info("GET request received, returning 200 success response.")
    return {
        "statusCode": 200,
        "body": challenge_secret,
    }


def handle_post_request(event: dict) -> dict[str, object]:
    if not valid_signature(event):
        logger.warning(
            "Invalid signature in POST request, returning 401 error response."
        )
        return {
            "statusCode": 401,
            "body": "Unable to validate signature. Has the webhook challenge secret "
            "changed?",
        }
    logger.info(
        "POST request received and validated, no action triggered. Returning 200 "
        "success response."
    )
    return {
        "statusCode": 200,
        "body": "Webhook POST request received and validated, no action taken.",
    }


def valid_signature(event: dict) -> bool:
    secret = os.environ["ALMA_CHALLENGE_SECRET"]
    message = json.dumps(event["body"])
    try:
        request_signature = event["headers"]["x-exl-signature"]
    except KeyError:
        return False
    message_hash = hmac.digest(secret.encode(), msg=message.encode(), digest="sha256")
    expected_signature = base64.b64encode(message_hash).decode()
    return request_signature == expected_signature
