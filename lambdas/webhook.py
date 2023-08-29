import base64
import hmac
import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import boto3
import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

env = os.getenv("WORKSPACE")
if sentry_dsn := os.getenv("SENTRY_DSN"):
    sentry = sentry_sdk.init(
        dsn=sentry_dsn,
        environment=env,
        integrations=[
            AwsLambdaIntegration(),
        ],
        traces_sample_rate=1.0,
    )
    logger.info("Sentry DSN found, exceptions will be sent to Sentry with env=%s", env)
else:
    logger.info("No Sentry DSN found, exceptions will not be sent to Sentry")


class JobTypeError(Exception):
    """Exception raised when unknown job name received."""


def lambda_handler(event: dict, context: object) -> dict[str, object]:  # noqa: ARG001
    logger.debug(json.dumps(event))

    if not os.getenv("WORKSPACE"):
        unset_workspace_error_message = "Required env variable WORKSPACE is not set"
        raise RuntimeError(unset_workspace_error_message)

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
        logger.warning("Invalid signature in POST request, returning 401 error response.")
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

    return handle_job_end_webhook(message_body)


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


def handle_job_end_webhook(message_body: dict) -> dict:
    job_name = message_body["job_instance"]["name"]

    if str(env).lower() not in job_name.lower():
        logger.info(
            "Alma job '%s' was for a different environment (current environment is %s), "
            "no action triggered. Returning 200 success response.",
            job_name,
            env,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated in {env} env for job "
            f"'{job_name}', no action taken.",
        }

    try:
        job_type, generate_step_function_input = get_job_type(job_name)
    except JobTypeError as e:
        logger.info(
            "POST request received and validated, no action triggered for job: '%s'. "
            "Returning 200 success response.",
            e,
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, no action taken.",
        }

    if message_body["job_instance"]["status"]["value"] != "COMPLETED_SUCCESS":
        logger.warning(
            "Alma job '%s' did not complete successfully, may need investigation. "
            "Returning 200 success response.",
            job_name,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated, Alma job '{job_name}' "
            "failed so no action was taken.",
        }

    if count_exported_records(message_body["job_instance"]["counter"]) == 0:
        logger.warning(
            "Alma job '%s' did not export any records, no action needed. Returning 200 "
            "success response.",
            job_name,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated, Alma job '{job_name}' "
            "exported zero records so no action was taken.",
        }

    logger.info(
        "%s export from Alma completed successfully, initiating %s step function.",
        job_type,
        job_type,
    )

    state_machine_arn = os.environ[f"{job_type}_STATE_MACHINE_ARN"]
    step_function_input, execution_name = generate_step_function_input(message_body)
    execute_state_machine(state_machine_arn, step_function_input, execution_name)
    logger.info("%s step function executed, returning 200 success response.", job_type)
    return {
        "statusCode": 200,
        "body": f"Webhook POST request received and validated, {job_type} pipeline "
        "initiated.",
    }


def get_job_type(job_name: str) -> tuple[str, Callable]:
    """Get job name from Alma webhook POST request.

    Given an expected job name, return the job type and corresponding function for
    generating the step function input.
    """
    job_types = [
        (
            "PPOD",
            "ALMA_POD_EXPORT_JOB_NAME",
            generate_ppod_step_function_input,
            "PPOD export job webhook received.",
        ),
        (
            "TIMDEX",
            "ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX",
            generate_timdex_step_function_input,
            "TIMDEX export job webhook received.",
        ),
        (
            "BURSAR",
            "ALMA_BURSAR_EXPORT_JOB_NAME",
            generate_bursar_step_function_input,
            "BURSAR export job webhook received.",
        ),
    ]

    for job_type, env_key, step_function_input_handler, log_msg in job_types:
        job_name_prefix = os.getenv(env_key)
        if not job_name_prefix:
            logger.warning("Expected env var not present: %s", env_key)
        if job_name_prefix and job_name.startswith(job_name_prefix):
            logger.info(log_msg)
            return job_type, step_function_input_handler

    # if job type not matched, raise exception
    raise JobTypeError(job_name)


def count_exported_records(counter: list[dict]) -> int:
    exported_record_types = [
        "label.new.records",
        "label.updated.records",
        "label.deleted.records",
        "com.exlibris.external.bursar.report.fines_fees_count",
    ]
    return sum(
        [int(c["value"]) for c in counter if c["type"]["value"] in exported_record_types]
    )


def generate_ppod_step_function_input(message_body: dict[str, Any]) -> tuple[str, str]:
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dt%H-%M-%S")
    job_date = message_body["job_instance"]["end_time"][:10]
    result = {
        "filename-prefix": f"exlibris/pod/POD_ALMA_EXPORT_{job_date.replace('-', '')}"
    }
    execution_name = f"ppod-upload-{timestamp}"
    return json.dumps(result), execution_name


def generate_timdex_step_function_input(message_body: dict[str, Any]) -> tuple[str, str]:
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dt%H-%M-%S")
    job_date = message_body["job_instance"]["end_time"][:10]
    run_type = message_body["job_instance"]["name"].split()[-1].lower()
    result = {
        "next-step": "transform",
        "run-date": job_date,
        "run-type": run_type,
        "source": "alma",
        "verbose": "true",
    }
    execution_name = f"alma-{run_type}-ingest-{timestamp}"
    return json.dumps(result), execution_name


def generate_bursar_step_function_input(message_body: dict[str, Any]) -> tuple[str, str]:
    result = {
        "job_id": message_body["job_instance"]["id"],
        "job_name": message_body["job_instance"]["name"],
    }
    execution_name = "bursar"
    return json.dumps(result), execution_name


def execute_state_machine(
    state_machine_arn: str,
    step_function_input: str,
    execution_name: str,
) -> dict:
    client = boto3.client("stepfunctions")
    response = client.start_execution(
        stateMachineArn=state_machine_arn,
        input=step_function_input,
        name=execution_name,
    )
    logger.debug(response)
    return response
