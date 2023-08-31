"""tests/integration/test_webhook.py.

NOTE: see conftest.pytest_collection_modifyitems for restrictions on when these
    pytest.mark.integration tests are allowed to run

Required .env variables:
    - WORKSPACE=dev
"""
# ruff: noqa: TRY002, D415, TRY003, EM102

import json
import os
import time

import boto3
import pytest

from lambdas.helpers import (
    send_get_to_lambda_function_url,
    send_post_to_lambda_function_url,
)


def get_step_function_invocation(step_function_arn: str, timeout: int = 15) -> dict:
    """Retrieve RUNNING StepFunction invocation, parse input JSON for first event"""
    sfn_client = boto3.client("stepfunctions")
    t0 = time.time()
    while True:
        # timeout
        if time.time() - t0 > timeout:
            raise Exception(
                f"Timeout of {timeout}s exceeded, could not identify running StepFunction"
            )

        # get all running executions
        running_executions = sfn_client.list_executions(
            stateMachineArn=step_function_arn, statusFilter="RUNNING"
        )["executions"]

        if len(running_executions) == 1:
            execution = running_executions[0]
            execution_results = sfn_client.get_execution_history(
                executionArn=execution["executionArn"]
            )
            return json.loads(
                execution_results["events"][0]["executionStartedEventDetails"]["input"]
            )

        if len(running_executions) > 1:
            raise Exception(
                f"Found {len(running_executions)} RUNNING executions, cannot reliably "
                f"determine if invoked by this webhook event."
            )

        time.sleep(0.5)


@pytest.mark.integration()
@pytest.mark.usefixtures("_set_integration_tests_env_vars")
def test_integration_webhook_handles_get_request_success():
    """Test that deployed lambda can receive GET requsts"""
    challenge_phrase = "challenge-accepted"
    response_text = send_get_to_lambda_function_url(challenge_phrase)
    assert response_text == challenge_phrase


@pytest.mark.integration()
@pytest.mark.usefixtures("_set_integration_tests_env_vars")
def test_integration_webhook_handles_post_request_but_no_job_type_match():
    """Test that deployed lambda can receive POST requests and skips unknown job type"""
    payload = {"action": "JOB_END", "job_instance": {"name": "Unhandled Job Name Here"}}
    response_text = send_post_to_lambda_function_url(payload)
    assert (
        response_text == "Webhook POST request received and validated in dev env for "
        "job 'Unhandled Job Name Here', no action taken."
    )


@pytest.mark.integration()
@pytest.mark.usefixtures("_set_integration_tests_env_vars")
@pytest.mark.usefixtures("_integration_tests_s3_fixtures")
def test_integration_webhook_handles_pod_step_function_trigger(
    sample_pod_export_job_end_webhook_post_body,
):
    """Test deployed lambda handles PPOD job type webhooks and invokes step function.

    Able to assert specific values in StepFunction execution results based on fixtures.
    """
    response_text = send_post_to_lambda_function_url(
        sample_pod_export_job_end_webhook_post_body
    )

    # assert lambda response that StepFunction invoked
    assert (
        response_text == "Webhook POST request received and validated, PPOD pipeline "
        "initiated."
    )

    # assert StepFunction running and with expected payload
    step_function_arn = os.getenv("PPOD_STATE_MACHINE_ARN")
    step_function_input_json = get_step_function_invocation(step_function_arn)
    assert (
        step_function_input_json["filename-prefix"]
        == "exlibris/pod/POD_ALMA_EXPORT_20230815"
    )


@pytest.mark.integration()
@pytest.mark.usefixtures("_set_integration_tests_env_vars")
@pytest.mark.usefixtures("_integration_tests_s3_fixtures")
def test_integration_webhook_handles_timdex_step_function_trigger(
    sample_timdex_export_job_end_webhook_post_body,
):
    """Tests deployed lambda handles TIMDEX job type webhooks and invokes step function.

    Able to assert specific values in StepFunction execution results based on fixtures.
    """
    response_text = send_post_to_lambda_function_url(
        sample_timdex_export_job_end_webhook_post_body
    )

    # assert lambda response that StepFunction invoked
    assert (
        response_text == "Webhook POST request received and validated, TIMDEX pipeline "
        "initiated."
    )

    # assert StepFunction running and with expected payload
    step_function_arn = os.getenv("TIMDEX_STATE_MACHINE_ARN")
    step_function_input_json = get_step_function_invocation(step_function_arn)
    assert step_function_input_json["next-step"] == "transform"
    assert step_function_input_json["run-date"] == "2023-08-15"
    assert step_function_input_json["run-type"] == "daily"
    assert step_function_input_json["source"] == "alma"
