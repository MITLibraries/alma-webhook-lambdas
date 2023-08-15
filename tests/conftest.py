import datetime
import os
import urllib

import botocore.session
import pytest
import requests_mock
from botocore.stub import Stubber

from lambdas.webhook import lambda_handler


@pytest.fixture(autouse=True)
def test_env():
    os.environ = {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "ALMA_CHALLENGE_SECRET": "itsasecret",
        "ALMA_POD_EXPORT_JOB_NAME": "PPOD Export",
        "ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX": "TIMDEX Export",
        "ALMA_BURSAR_EXPORT_JOB_NAME_PREFIX": "Export to bursar",
        "LAMBDA_FUNCTION_URL": "http://example.com/lambda",
        "PPOD_STATE_MACHINE_ARN": "arn:aws:states:us-east-1:account:stateMachine:"
        "ppod-test",
        "TIMDEX_STATE_MACHINE_ARN": "arn:aws:states:us-east-1:account:stateMachine:"
        "timdex-test",
        "BURSAR_STATE_MACHINE_ARN": "arn:aws:states:us-east-1:account:stateMachine:"
        "bursar-test",
        "VALID_POD_EXPORT_DATE": "2022-05-23",
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


@pytest.fixture()
def mocked_valid_signature(mocker):
    return mocker.patch("lambdas.webhook.valid_signature", return_value=True)


def get_request_callback(request, context):
    query = urllib.parse.urlparse(request.url).query
    parsed_query = urllib.parse.parse_qsl(query)[0]
    request_data = {
        "queryStringParameters": {parsed_query[0]: parsed_query[1]},
        "requestContext": {"http": {"method": request.method}},
    }
    response = lambda_handler(request_data, {})
    return response["body"]


def post_request_callback(request, context):
    request_data = {
        "headers": {"x-exl-signature": request.headers["x-exl-signature"]},
        "requestContext": {"http": {"method": request.method}},
        "body": request.body.decode(),
    }
    response = lambda_handler(request_data, {})
    return response["body"]


@pytest.fixture()
def mocked_lambda_function_url():
    with requests_mock.Mocker() as m:
        m.get("http://example.com/lambda", text=get_request_callback)
        m.post("http://example.com/lambda", text=post_request_callback)
        yield m


@pytest.fixture()
def stubbed_ppod_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:ppod-test:12345",
        "startDate": datetime.datetime(2022, 5, 1),
    }
    expected_params = {
        "stateMachineArn": "arn:aws:states:us-east-1:account:stateMachine:ppod-test",
        "input": '{"filename-prefix": "exlibris/pod/POD_ALMA_EXPORT_20220501"}',
        "name": "ppod-upload-2022-05-01t00-00-00",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn


@pytest.fixture()
def stubbed_timdex_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:timdex-test:12345",
        "startDate": datetime.datetime(2022, 5, 1),
    }
    expected_params = {
        "stateMachineArn": "arn:aws:states:us-east-1:account:stateMachine:timdex-test",
        "input": '{"next-step": "transform", "run-date": "2022-05-01", '
        '"run-type": "full", "source": "alma", "verbose": "true"}',
        "name": "alma-full-ingest-2022-05-01t00-00-00",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn


@pytest.fixture()
def stubbed_bursar_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:-test:bursar12345",
        "startDate": datetime.datetime(2022, 5, 1),
    }
    expected_params = {
        "stateMachineArn": "arn:aws:states:us-east-1:account:stateMachine:bursar-test",
        "input": '{"job_id": "test id", "job_name": "Export to bursar using profile '
        "Bursar "
        'Export to test"}',
        "name": "bursar",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn
