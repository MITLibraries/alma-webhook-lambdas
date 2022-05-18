import logging

from lambdas.webhook import lambda_handler


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


def test_webhook_handles_invalid_request_type():
    request_data = {"requestContext": {"http": {"method": "DELETE"}}}
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 405,
        "body": "HTTP method not allowed. Only GET requests are supported.",
    }
    assert lambda_handler(request_data, {}) == expected_output


def test_webhook_handles_get_request_success(get_request):
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "challenge-accepted",
    }
    assert lambda_handler(get_request, {}) == expected_output


def test_webhook_handles_get_request_missing_parameter(get_request_missing_parameter):
    expected_output = {
        "headers": {"Content-Type": "text/plain"},
        "isBase64Encoded": False,
        "statusCode": 400,
        "body": "Malformed request, 'challenge' query parameter required",
    }
    assert lambda_handler(get_request_missing_parameter, {}) == expected_output
