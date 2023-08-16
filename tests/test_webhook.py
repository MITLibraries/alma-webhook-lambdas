import json
from datetime import UTC, datetime
from importlib import reload
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from lambdas import webhook
from lambdas.webhook import (
    count_exported_records,
    execute_state_machine,
    lambda_handler,
    valid_signature,
)


def test_webhook_configures_sentry_if_dsn_present(caplog, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://1234567890@00000.ingest.sentry.io/123456")
    reload(webhook)
    assert (
        "Sentry DSN found, exceptions will be sent to Sentry with env=test" in caplog.text
    )


def test_webhook_doesnt_configure_sentry_if_dsn_not_present(
    caplog, get_request, monkeypatch
):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    reload(webhook)
    assert "No Sentry DSN found, exceptions will not be sent to Sentry" in caplog.text


def test_webhook_missing_workspace_env_raises_error(monkeypatch):
    monkeypatch.delenv("WORKSPACE", raising=False)
    with pytest.raises(RuntimeError) as e:
        lambda_handler({}, {})
    assert "Required env variable WORKSPACE is not set" in str(e)


def test_webhook_missing_request_method_raises_error():
    with pytest.raises(KeyError):
        lambda_handler({}, {})


def test_webhook_handles_invalid_request_method(caplog):
    request_data = {"requestContext": {"http": {"method": "DELETE"}}}
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 405,
        "body": "HTTP method DELETE not allowed. Supported methods: GET, POST.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "lambdas.webhook",
        30,
        "Received invalid HTTP request method DELETE, returning 405 error response.",
    ) in caplog.record_tuples


def test_webhook_handles_get_request_missing_parameter(caplog):
    request_data = {"requestContext": {"http": {"method": "GET"}}}
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 400,
        "body": "Malformed request, 'challenge' query parameter required.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "lambdas.webhook",
        30,
        "Received GET request without 'challenge' query parameter, returning "
        "400 error response.",
    ) in caplog.record_tuples


def test_webhook_handles_get_request_success(caplog, get_request):
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "challenge-accepted",
    }
    assert lambda_handler(get_request, {}) == expected_output
    assert "GET request received, returning 200 success response." in caplog.text


def test_webhook_handles_post_request_invalid_signature(
    caplog, post_request_invalid_signature
):
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 401,
        "body": "Unable to validate signature. Has the webhook challenge secret "
        "changed?",
    }
    assert lambda_handler(post_request_invalid_signature, {}) == expected_output
    assert (
        "lambdas.webhook",
        30,
        "Invalid signature in POST request, returning 401 error response.",
    ) in caplog.record_tuples


def test_webhook_handles_post_request_not_job_end(caplog, mocked_valid_signature):
    request_body = {
        "action": "THIS_IS_WRONG",
        "job_instance": {"name": "PPOD Export"},
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, not a JOB_END "
        "webhook so no action was taken.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "lambdas.webhook",
        30,
        "Received a non-JOB_END webhook POST request, may require investigation. "
        "Returning 200 success response.",
    ) in caplog.record_tuples


def test_webhook_handles_post_request_job_for_different_env(
    caplog, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {"name": "TIMDEX Export to other-env"},
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated in test env for job "
        "'TIMDEX Export to other-env', no action taken.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "Job 'TIMDEX Export to other-env' was for a different environment (current "
        "environment is test), no action triggered. Returning 200 success response."
        in caplog.text
    )


def test_webhook_handles_post_request_job_end_unknown_job(
    caplog, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {"name": "This is Wrong"},
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, no action taken.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "POST request received and validated, no action triggered for job: "
        "'This is Wrong'. Returning 200 "
        "success response." in caplog.text
    )


def test_webhook_handles_post_request_job_end_job_failed(
    caplog, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {
            "name": "PPOD Export to Test",
            "status": {"value": "COMPLETED_FAILED"},
        },
    }

    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, PPOD export job failed "
        "so no action was taken.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "lambdas.webhook",
        30,
        "PPOD export job did not complete successfully, may need investigation. "
        "Returning 200 success response.",
    ) in caplog.record_tuples


def test_webhook_handles_post_request_job_end_no_records_exported(
    caplog, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {
            "name": "TIMDEX Export to Test",
            "status": {"value": "COMPLETED_SUCCESS"},
            "counter": [
                {
                    "type": {"value": "label.new.records", "desc": "New Records"},
                    "value": "0",
                },
                {
                    "type": {
                        "value": "label.updated.records",
                        "desc": "Updated Records",
                    },
                    "value": "0",
                },
                {
                    "type": {
                        "value": "label.deleted.records",
                        "desc": "Deleted Records",
                    },
                    "value": "0",
                },
            ],
        },
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, TIMDEX export job "
        "exported zero records so no action was taken.",
    }
    assert lambda_handler(request_data, {}) == expected_output
    assert (
        "TIMDEX job did not export any records, no action needed. Returning 200 "
        "success response." in caplog.text
    )


@freeze_time("2022-05-01")
def test_webhook_handles_post_request_pod_export_job_success(
    caplog, stubbed_ppod_sfn_client, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {
            "name": "PPOD Export to Test",
            "end_time": "2022-05-01T14:55:14.894Z",
            "status": {"value": "COMPLETED_SUCCESS"},
            "counter": [
                {
                    "type": {"value": "label.new.records", "desc": "New Records"},
                    "value": "1",
                },
            ],
        },
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, PPOD pipeline initiated.",
    }
    with patch("boto3.client") as mocked_boto_client:
        mocked_boto_client.return_value = stubbed_ppod_sfn_client
        assert lambda_handler(request_data, {}) == expected_output
    assert (
        "PPOD export from Alma completed successfully, initiating PPOD step function."
        in caplog.text
    )
    assert "PPOD step function executed, returning 200 success response." in caplog.text


@freeze_time("2022-05-01")
def test_webhook_handles_post_request_timdex_export_job_success(
    caplog, stubbed_timdex_sfn_client, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {
            "name": "TIMDEX Export to Test FULL",
            "end_time": "2022-05-01T14:55:14.894Z",
            "status": {"value": "COMPLETED_SUCCESS"},
            "counter": [
                {
                    "type": {"value": "label.new.records", "desc": "New Records"},
                    "value": "1000",
                },
            ],
        },
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, TIMDEX pipeline "
        "initiated.",
    }
    with patch("boto3.client") as mocked_boto_client:
        mocked_boto_client.return_value = stubbed_timdex_sfn_client
        assert lambda_handler(request_data, {}) == expected_output
    assert (
        "TIMDEX export from Alma completed successfully, initiating TIMDEX step "
        "function." in caplog.text
    )
    assert "TIMDEX step function executed, returning 200 success response." in caplog.text


@freeze_time("2022-05-01")
def test_webhook_handles_post_request_bursar_export_job_success(
    caplog, stubbed_bursar_sfn_client, mocked_valid_signature
):
    request_body = {
        "action": "JOB_END",
        "job_instance": {
            "name": "Export to bursar using profile Bursar Export to test",
            "id": "test id",
            "end_time": "2022-05-01T14:55:14.894Z",
            "status": {"value": "COMPLETED_SUCCESS"},
            "counter": [
                {
                    "type": {
                        "value": "com.exlibris.external.bursar.report.user_count",
                        "desc": "Total number of users",
                    },
                    "value": "5",
                },
                {
                    "type": {
                        "value": "com.exlibris.external.bursar.report.fines_fees_count",
                        "desc": "Total number of fines and fees",
                    },
                    "value": "20",
                },
            ],
        },
    }
    request_data = {
        "headers": {"x-exl-signature": "foo"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(request_body),
    }
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, BURSAR pipeline initiated.",
    }
    with patch("boto3.client") as mocked_boto_client:
        mocked_boto_client.return_value = stubbed_bursar_sfn_client
        assert lambda_handler(request_data, {}) == expected_output
    assert (
        "BURSAR export from Alma completed successfully, initiating BURSAR step function."
        in caplog.text
    )
    assert (
        "BURSAR step function executed, returning 200 success response." in caplog.text
    )


def test_validate_missing_signature_returns_false():
    request_data = {
        "requestContext": {"http": {"method": "POST"}},
        "body": {"action": "JOB_END"},
    }
    assert valid_signature(request_data) is False


def test_validate_invalid_signature_returns_false(post_request_invalid_signature):
    assert valid_signature(post_request_invalid_signature) is False


def test_validate_valid_signature_returns_true(post_request_valid_signature):
    assert valid_signature(post_request_valid_signature) is True


def test_get_job_type_warning_if_env_missing(caplog, monkeypatch):
    job_name = "TIMDEX Export to Test Full"
    monkeypatch.delenv("ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX")
    reload(webhook)
    with pytest.raises(ValueError):
        webhook.get_job_type(job_name)
    assert (
        "expected env var not present: ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX"
        in caplog.text
    )


def test_count_exported_records_with_no_records_exported():
    counter = [
        {
            "type": {"value": "label.new.records", "desc": "New Records"},
            "value": "0",
        },
        {
            "type": {"value": "label.updated.records", "desc": "Updated Records"},
            "value": "0",
        },
        {
            "type": {"value": "label.deleted.records", "desc": "Deleted Records"},
            "value": "0",
        },
        {
            "type": {
                "value": "c.jobs.publishing.failed.publishing",
                "desc": "Unpublished failed records",
            },
            "value": "1",
        },
        {
            "type": {
                "value": "c.jobs.publishing.skipped",
                "desc": "Skipped records (update date changed but no data change)",
            },
            "value": "0",
        },
        {
            "type": {
                "value": "c.jobs.publishing.filtered_out",
                "desc": "Filtered records (not published due to filter)",
            },
            "value": "1",
        },
        {
            "type": {
                "value": "c.jobs.publishing.totalRecordsWrittenToFile",
                "desc": "Total records written to file",
            },
            "value": "0",
        },
    ]
    assert count_exported_records(counter) == 0


def test_count_exported_records_with_records_exported():
    counter = [
        {
            "type": {"value": "label.new.records", "desc": "New Records"},
            "value": "1",
        },
        {
            "type": {"value": "label.updated.records", "desc": "Updated Records"},
            "value": "2",
        },
        {
            "type": {"value": "label.deleted.records", "desc": "Deleted Records"},
            "value": "3",
        },
        {
            "type": {
                "value": "c.jobs.publishing.failed.publishing",
                "desc": "Unpublished failed records",
            },
            "value": "0",
        },
        {
            "type": {
                "value": "c.jobs.publishing.skipped",
                "desc": "Skipped records (update date changed but no data change)",
            },
            "value": "1",
        },
        {
            "type": {
                "value": "c.jobs.publishing.filtered_out",
                "desc": "Filtered records (not published due to filter)",
            },
            "value": "0",
        },
        {
            "type": {
                "value": "c.jobs.publishing.totalRecordsWrittenToFile",
                "desc": "Total records written to file",
            },
            "value": "0",
        },
    ]
    assert count_exported_records(counter) == 6  # noqa: PLR2004


@freeze_time("2022-05-01")
def test_execute_state_machine_success(stubbed_ppod_sfn_client):
    with patch("boto3.client") as mocked_boto_client:
        mocked_boto_client.return_value = stubbed_ppod_sfn_client
        response = execute_state_machine(
            "arn:aws:states:us-east-1:account:stateMachine:ppod-test",
            '{"filename-prefix": "exlibris/pod/POD_ALMA_EXPORT_20220501"}',
            "ppod-upload-2022-05-01t00-00-00",
        )
    assert response == {
        "executionArn": "arn:aws:states:us-east-1:account:execution:ppod-test:12345",
        "startDate": datetime(2022, 5, 1, tzinfo=UTC),
    }
