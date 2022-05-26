import os

import pytest


@pytest.fixture(autouse=True)
def test_env():
    os.environ = {
        "ALMA_CHALLENGE_SECRET": "itsasecret",
        "ALMA_POD_EXPORT_JOB_NAME": "PPOD Export",
        "WORKSPACE": "test",
    }
    return


@pytest.fixture()
def get_request():
    request_data = {
        "queryStringParameters": {"challenge": "challenge-accepted"},
        "requestContext": {"http": {"method": "GET"}},
    }
    return request_data


@pytest.fixture()
def post_request_invalid_signature():
    request_data = {
        "headers": {"x-exl-signature": "thisiswrong"},
        "requestContext": {"http": {"method": "POST"}},
        "body": "The POST request body",
    }
    return request_data


@pytest.fixture()
def post_request_valid_signature():
    request_data = {
        "headers": {"x-exl-signature": "e9SHoXK4MZrSGqhglMK4w+/u1pjYn0bfTEYtcFqj7CE="},
        "requestContext": {"http": {"method": "POST"}},
        "body": "The POST request body",
    }
    return request_data
