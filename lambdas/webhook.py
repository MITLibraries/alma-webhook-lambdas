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

    message_body = json.loads(event["body"])
    if message_body["action"] != "JOB_END":
        logger.warning(
            "Received a non-JOB_END webhook POST request, may require investigation. "
            "Returning 200 success response."
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, not a JOB_END "
            "webhook so no action was taken.",
        }

    if message_body["job_instance"]["name"] == os.environ["ALMA_POD_EXPORT_JOB_NAME"]:
        logger.info("POD export job webhook received.")
        return handle_pod_export_webhook(message_body)

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
    message = event["body"]
    try:
        request_signature = event["headers"]["x-exl-signature"]
    except KeyError:
        return False
    message_hash = hmac.digest(secret.encode(), msg=message.encode(), digest="sha256")
    expected_signature = base64.b64encode(message_hash).decode()
    return request_signature == expected_signature


def handle_pod_export_webhook(message_body: dict) -> dict[str, object]:
    if message_body["job_instance"]["status"]["value"] != "COMPLETED_SUCCESS":
        logger.warning(
            "POD export job did not complete successfully, may need investigation. "
            "Returning 200 success response."
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, POD export job "
            "failed so no action was taken.",
        }

    if count_exported_records(message_body["job_instance"]["counter"]) == 0:
        logger.info(
            "POD job did not export any records, no action needed. Returning 200 "
            "success response."
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, POD export job "
            "exported zero records so no action was taken.",
        }

    logger.info(
        "POD export from Alma completed successfully, initiating POD upload step "
        "function."
    )
    return {
        "statusCode": 200,
        "body": "Webhook POST request received and validated, initiating POD upload.",
    }


def count_exported_records(counter: list[dict]) -> int:
    exported_record_types = [
        "label.new.records",
        "label.updated.records",
        "label.deleted.records",
    ]
    count = sum(
        [
            int(c["value"])
            for c in counter
            if c["type"]["value"] in exported_record_types
        ]
    )
    return count
