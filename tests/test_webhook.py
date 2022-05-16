import logging

from lambdas.webhook import lambda_handler


def test_webhook_returns_expected_value():
    expected_output = "Hello lambda!"
    assert lambda_handler({}, {}) == expected_output


def test_webhook_configures_sentry_if_dsn_present(caplog, monkeypatch):
    monkeypatch.setenv("WORKSPACE", "test")
    monkeypatch.setenv("SENTRY_DSN", "https://1234567890@00000.ingest.sentry.io/123456")
    caplog.set_level(logging.INFO)
    lambda_handler({}, {})
    assert (
        "Sentry DSN found, exceptions will be sent to Sentry with env=test"
        in caplog.text
    )


def test_webhook_doesnt_configure_sentry_if_dsn_not_present(caplog, monkeypatch):
    monkeypatch.setenv("WORKSPACE", "test")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    caplog.set_level(logging.INFO)
    lambda_handler({}, {})
    assert "Sentry DSN found" not in caplog.text
