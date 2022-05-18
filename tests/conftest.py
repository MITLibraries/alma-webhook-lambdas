import os

import pytest


@pytest.fixture(autouse=True)
def test_env():
    os.environ = {"WORKSPACE": "test"}
    yield


@pytest.fixture()
def get_request():
    request_data = {
        "queryStringParameters": {"challenge": "challenge-accepted"},
        "requestContext": {
            "http": {
                "method": "GET",
            },
        },
    }
    yield request_data


@pytest.fixture()
def get_request_missing_parameter():
    request_data = {
        "requestContext": {
            "http": {
                "method": "GET",
            },
        },
    }
    yield request_data
