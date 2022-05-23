import os

import pytest


@pytest.fixture(autouse=True)
def test_env():
    os.environ = {
        "ALMA_CHALLENGE_SECRET": "itsasecret",
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
        "body": {"action": "JOB_END"},
    }
    return request_data


@pytest.fixture()
def post_request_valid_signature():
    request_data = {
        "headers": {"x-exl-signature": "bbQKggzWRSuwopIwszy757lusNZWOPllfv5Rt6Qj8uE="},
        "requestContext": {"http": {"method": "POST"}},
        "body": {"action": "JOB_END"},
    }
    return request_data
