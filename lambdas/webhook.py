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

    try:
        job_type = get_job_type(job_name)
    except ValueError as e:
        logger.info(
            "POST request received and validated, no action triggered for job: '%s'. "
            "Returning 200 success response.",
            e,
        )
        return {
            "statusCode": 200,
            "body": "Webhook POST request received and validated, no action taken.",
        }

    if str(env).lower() not in job_name.lower():
        logger.info(
            "Job '%s' was for a different environment (current environment is %s), no "
            "action triggered. Returning 200 success response.",
            job_name,
            env,
        )
        return {
            "statusCode": 200,
            "body": f"Webhook POST request received and validated in {env} env for job "
            f"'{job_name}', no action taken.",
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

    state_machine_arn = os.environ[f"{job_type}_STATE_MACHINE_ARN"]
    step_function_input, execution_name = generate_step_function_input(
        message_body, job_type=job_type
    )
    execute_state_machine(state_machine_arn, step_function_input, execution_name)
    logger.info("%s step function executed, returning 200 success response.", job_type)
    return {
        "statusCode": 200,
        "body": f"Webhook POST request received and validated, {job_type} pipeline "
        "initiated.",
    }

def get_job_type(job_name):
    if job_name.startswith(os.environ["ALMA_POD_EXPORT_JOB_NAME"]):
        logger.info("PPOD export job webhook received.")
        return "PPOD"
    elif job_name.startswith(os.environ["ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX"]):
        logger.info("TIMDEX export job webhook received.")
        return "TIMDEX"
    raise ValueError(job_name)

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


def generate_step_function_input(message_body: dict, job_type: str) -> tuple[str, str]:
    step_function_input = choose_step_function_input_generator(job_type)
    return step_function_input(message_body)


def choose_step_function_input_generator(job_type):
    if job_type == "PPOD":
        return generate_ppod_step_function_input
    elif job_type == "TIMDEX":
        return generate_timdex_step_function_input
    else:
        raise ValueError(job_type)


def generate_ppod_step_function_input(message_body) -> tuple[str, str]:
    timestamp = datetime.now().strftime("%Y-%m-%dt%H-%M-%S")
    job_date = message_body["job_instance"]["end_time"][:10]
    result = {
        "filename-prefix": "exlibris/pod/POD_ALMA_EXPORT_"
        f"{job_date.replace('-', '')}"
    }
    execution_name = f"ppod-upload-{timestamp}"
    return json.dumps(result), execution_name


def generate_timdex_step_function_input(message_body):
    timestamp = datetime.now().strftime("%Y-%m-%dt%H-%M-%S")
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
