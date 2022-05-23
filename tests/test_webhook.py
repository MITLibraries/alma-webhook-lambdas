import logging

import pytest

from lambdas.webhook import lambda_handler, valid_signature


def test_webhook_configures_sentry_if_dsn_present(caplog, get_request, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://1234567890@00000.ingest.sentry.io/123456")
    caplog.set_level(logging.INFO)
    lambda_handler(get_request, {})
    assert (
        "Sentry DSN found, exceptions will be sent to Sentry with env=test"
        in caplog.text
    )


def test_webhook_doesnt_configure_sentry_if_dsn_not_present(
    caplog, get_request, monkeypatch
):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    caplog.set_level(logging.INFO)
    lambda_handler(get_request, {})
    assert "Sentry DSN found" not in caplog.text


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


def test_webhook_handles_post_request_success(caplog, post_request_valid_signature):
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "Webhook POST request received and validated, no action taken.",
    }
    assert lambda_handler(post_request_valid_signature, {}) == expected_output
    assert (
        "POST request received and validated, no action triggered. Returning 200 "
        "success response." in caplog.text
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
