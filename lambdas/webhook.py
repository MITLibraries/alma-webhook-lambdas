import base64
import hmac
import json
import logging
import os
from datetime import datetime

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


def lambda_handler(event: dict, context: object) -> dict[str, object]:
    logger.debug(json.dumps(event))

    if not os.getenv("WORKSPACE"):
        raise RuntimeError("Required env variable WORKSPACE is not set")

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
    if job_name == os.environ["ALMA_POD_EXPORT_JOB_NAME"]:
        logger.info("PPOD export job webhook received.")
        job_type = "PPOD"
    elif job_name.startswith(os.environ["ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX"]):
        logger.info("TIMDEX export job webhook received.")
        job_type = "TIMDEX"
    else:
        logger.info(
            "POST request received and validated, no action triggered. Returning 200 "
            "success response."
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, no action taken.",
        }

    if message_body["job_instance"]["status"]["value"] != "COMPLETED_SUCCESS":
        logger.warning(
            "%s export job did not complete successfully, may need investigation. "
            "Returning 200 success response.",
            job_type,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated, {job_type} export "
            "job failed so no action was taken.",
        }

    if count_exported_records(message_body["job_instance"]["counter"]) == 0:
        logger.info(
            "%s job did not export any records, no action needed. Returning 200 "
            "success response.",
            job_type,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated, {job_type} "
            "export job exported zero records so no action was taken.",
        }

    logger.info(
        "%s export from Alma completed successfully, initiating %s step function.",
        job_type,
        job_type,
    )
    job_date = message_body["job_instance"]["end_time"][:10]
    state_machine_arn = os.environ[f"{job_type}_STATE_MACHINE_ARN"]
    step_function_input, execution_name = generate_step_function_input(
        job_date, job_name, job_type
    )
    execute_state_machine(state_machine_arn, step_function_input, execution_name)
    logger.info("%s step function executed, returning 200 success response.", job_type)
    return {
        "statusCode": 200,
        "body": f"Webhook POST request received and validated, {job_type} pipeline "
        "initiated.",
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


def generate_step_function_input(
    job_date: str, job_name: str, job_type: str
) -> tuple[str, str]:
    timestamp = datetime.now().strftime("%Y-%m-%dt%H-%M-%S")
    if job_type == "PPOD":
        result = {
            "filename-prefix": "exlibris/pod/POD_ALMA_EXPORT_"
            f"{job_date.replace('-', '')}"
        }
        execution_name = f"ppod-upload-{timestamp}"
    elif job_type == "TIMDEX":
        run_type = job_name.split()[-1].lower()
        result = {
            "next-step": "transform",
            "run-date": job_date,
            "run-type": run_type,
            "source": "alma",
            "verbose": "true",
        }
        execution_name = f"alma-{run_type}-ingest-{timestamp}"
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
