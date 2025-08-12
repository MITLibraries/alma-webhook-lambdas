import datetime
import os
import urllib
from contextlib import contextmanager
from importlib import reload

import boto3
import botocore.session
import pytest
import requests_mock
from botocore.exceptions import ClientError
from botocore.stub import Stubber

import lambdas.webhook
from lambdas.webhook import lambda_handler

ORIGINAL_ENV = os.environ.copy()


@contextmanager
def temp_environ(environ):
    """Provide a temporary environ with automatic teardown.

    Tests that use fixtures, that use this, are all invoked as part of the 'yield' step
    below.  Therefore, the environment is reset via 'finally' regardless of their
    success / fail / error results.
    """
    previous_environ = os.environ.copy()
    # ruff: noqa: B003
    os.environ = environ
    try:
        yield
    finally:
        # ruff: noqa: B003
        os.environ = previous_environ


@pytest.fixture(autouse=True)
def _test_env():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["ALMA_CHALLENGE_SECRET"] = "itsasecret"
    os.environ["ALMA_POD_EXPORT_JOB_NAME"] = "PPOD Export to test"
    os.environ["ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX"] = "TIMDEX Export to test"
    os.environ["ALMA_BURSAR_EXPORT_JOB_NAME"] = "Bursar Export to test"
    os.environ["LAMBDA_FUNCTION_URL"] = "http://example.com/lambda"
    os.environ["PPOD_STATE_MACHINE_ARN"] = (
        "arn:aws:states:us-east-1:account:stateMachine:ppod-test"
    )
    os.environ["TIMDEX_STATE_MACHINE_ARN"] = (
        "arn:aws:states:us-east-1:account:stateMachine:timdex-test"
    )
    os.environ["BURSAR_STATE_MACHINE_ARN"] = (
        "arn:aws:states:us-east-1:account:stateMachine:bursar-test"
    )
    os.environ["VALID_POD_EXPORT_DATE"] = "2022-05-23"
    os.environ["WORKSPACE"] = "test"


@pytest.fixture
def get_request():
    return {
        "queryStringParameters": {"challenge": "challenge-accepted"},
        "requestContext": {"http": {"method": "GET"}},
    }


@pytest.fixture
def post_request_invalid_signature():
    return {
        "headers": {"x-exl-signature": "thisiswrong"},
        "requestContext": {"http": {"method": "POST"}},
        "body": "The POST request body",
    }


@pytest.fixture
def post_request_valid_signature():
    return {
        "headers": {"x-exl-signature": "e9SHoXK4MZrSGqhglMK4w+/u1pjYn0bfTEYtcFqj7CE="},
        "requestContext": {"http": {"method": "POST"}},
        "body": "The POST request body",
    }


@pytest.fixture
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
    reload(lambdas.webhook)
    response = lambda_handler(request_data, {})
    return response["body"]


@pytest.fixture
def mocked_lambda_function_url():
    with requests_mock.Mocker() as m:
        m.get("http://example.com/lambda", text=get_request_callback)
        m.post("http://example.com/lambda", text=post_request_callback)
        yield m


@pytest.fixture
def stubbed_ppod_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:ppod-test:12345",
        "startDate": datetime.datetime(2022, 5, 1, tzinfo=datetime.UTC),
    }
    expected_params = {
        "stateMachineArn": "arn:aws:states:us-east-1:account:stateMachine:ppod-test",
        "input": '{"filename-prefix": "exlibris/pod/POD_ALMA_EXPORT_20220501"}',
        "name": "ppod-upload-2022-05-01t00-00-00",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn


@pytest.fixture
def stubbed_timdex_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:timdex-test:12345",
        "startDate": datetime.datetime(2022, 5, 1, tzinfo=datetime.UTC),
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


@pytest.fixture
def stubbed_bursar_sfn_client():
    sfn = botocore.session.get_session().create_client(
        "stepfunctions", region_name="us-east-1"
    )
    expected_response = {
        "executionArn": "arn:aws:states:us-east-1:account:execution:-test:bursar12345",
        "startDate": datetime.datetime(2022, 5, 1, tzinfo=datetime.UTC),
    }
    expected_params = {
        "stateMachineArn": "arn:aws:states:us-east-1:account:stateMachine:bursar-test",
        "input": '{"job_id": "test id"}',
        "name": "bursar-2022-05-01t00-00-00",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn


def set_env_vars_from_deployed_lambda_configurations():
    env = os.getenv("WORKSPACE").lower()
    lambda_client = boto3.client("lambda")
    lambda_function_config = lambda_client.get_function_configuration(
        FunctionName=f"alma-webhook-lambdas-{env}"
    )
    lambda_function_env_vars = lambda_function_config["Environment"]["Variables"]
    lambda_function_url = lambda_client.get_function_url_config(
        FunctionName=f"alma-webhook-lambdas-{env}"
    )["FunctionUrl"]

    os.environ["LAMBDA_FUNCTION_URL"] = lambda_function_url
    os.environ["ALMA_CHALLENGE_SECRET"] = lambda_function_env_vars[
        "ALMA_CHALLENGE_SECRET"
    ]


def set_env_vars_from_ssm_parameters():
    ssm_client = boto3.client("ssm")
    ppod_state_machine_arn = ssm_client.get_parameter(
        Name="/apps/almahook/ppod-state-machine-arn"
    )["Parameter"]["Value"]
    timdex_state_machine_arn = ssm_client.get_parameter(
        Name="/apps/almahook/timdex-ingest-state-machine-arn"
    )["Parameter"]["Value"]
    bursar_state_machine_arn = ssm_client.get_parameter(
        Name="/apps/almahook/bursar-state-machine-arn"
    )["Parameter"]["Value"]

    os.environ["PPOD_STATE_MACHINE_ARN"] = ppod_state_machine_arn
    os.environ["TIMDEX_STATE_MACHINE_ARN"] = timdex_state_machine_arn
    os.environ["BURSAR_STATE_MACHINE_ARN"] = bursar_state_machine_arn


@pytest.fixture
def _set_integration_test_environ() -> None:
    """Fixture to bypass the auto used fixture '_test_env' for integration tests.

    Because mocked AWS credentials are set in the auto used testing environment, this
    temporarily bypasses the testing environment and uses the calling environment
    (e.g. developer machine) such that AWS credentials can be used for integration tests.

    When any test that uses this fixture is finished, the testing environment is
    automatically reinstated.
    """
    with temp_environ(ORIGINAL_ENV):
        if os.getenv("WORKSPACE") != "dev":
            # ruff: noqa: TRY002, TRY003, EM101
            raise Exception("WORKSPACE env var must be 'dev' for integration tests")

        os.environ["VALID_POD_EXPORT_DATE"] = "2023-08-15"  # matches fixture date
        os.environ["VALID_TIMDEX_EXPORT_DATE"] = "2023-08-15"  # matches fixture date

        set_env_vars_from_deployed_lambda_configurations()

        set_env_vars_from_ssm_parameters()

        # required to allow tests to run in this contextmanager
        yield


@pytest.fixture
def _integration_tests_s3_fixtures(_set_integration_test_environ) -> None:
    """Upload integration test fixtures to S3 if they don't already exist.

    These s3 files are used by deployed assets during integration tests.  This fixture
    relies on _set_integration_tests_env_vars as a dependency to ensure AWS credentials
    have not been clobbered by testing env vars.
    """
    fixtures = [
        (
            "dev-sftp-shared",
            "exlibris/pod/POD_ALMA_EXPORT_20230815_220844[016]_new.tar.gz",
        ),
        (
            "dev-sftp-shared",
            "exlibris/timdex/TIMDEX_ALMA_EXPORT_DAILY_20230815_220844[016]_new.tar.gz",
        ),
        (
            "dev-sftp-shared",
            "exlibris/bursar/BURSAR_EXPORT_to_Dev1-12345678-99999999.xml",
        ),
    ]
    s3 = boto3.client("s3")
    for bucket, key in fixtures:
        try:
            s3.head_object(Bucket=bucket, Key=key + "foo")
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            # ruff: noqa: PLR2004
            if error_code == 404:
                local_file_path = os.path.join("tests", "fixtures", os.path.basename(key))
                if os.path.exists(local_file_path):
                    s3.upload_file(local_file_path, bucket, key)
                else:
                    msg = f"Local file '{local_file_path}' does not exist."
                    raise FileNotFoundError(msg) from None
            else:
                raise


@pytest.fixture
def sample_webhook_post_body() -> dict:
    return {
        "action": "JOB_END",
        "job_instance": {
            "name": "Not a POD export job",
        },
    }


@pytest.fixture
def sample_pod_export_job_end_webhook_post_body() -> dict:
    return {
        "action": "JOB_END",
        "job_instance": {
            "name": os.getenv(
                "ALMA_POD_EXPORT_JOB_NAME", "Publishing Platform Job PPOD EXPORT to Dev1"
            ),
            "end_time": os.getenv("VALID_POD_EXPORT_DATE", "2022-05-23"),
            "status": {"value": "COMPLETED_SUCCESS"},
            "counter": [
                {
                    "type": {"value": "label.new.records", "desc": "New Records"},
                    "value": "1",
                },
            ],
        },
    }


@pytest.fixture
def sample_timdex_export_job_end_webhook_post_body() -> dict:
    return {
        "action": "JOB_END",
        "job_instance": {
            "name": os.getenv(
                "ALMA_TIMDEX_EXPORT_JOB_NAME",
                "Publishing Platform Job TIMDEX EXPORT to Dev1 DAILY",
            ),
            "status": {"value": "COMPLETED_SUCCESS"},
            "end_time": os.getenv("VALID_TIMDEX_EXPORT_DATE", "2022-10-24"),
            "counter": [
                {
                    "type": {"value": "label.new.records", "desc": "New Records"},
                    "value": "1",
                },
            ],
        },
    }


@pytest.fixture
def sample_bursar_export_job_end_webhook_post_body() -> dict:
    return {
        "action": "JOB_END",
        "job_instance": {
            "name": os.getenv(
                "ALMA_BURSAR_EXPORT_JOB_NAME",
                "Export to bursar using profile BURSAR EXPORT to Dev1",
            ),
            "status": {"value": "COMPLETED_SUCCESS"},
            "id": "12345678",
            "counter": [
                {
                    "type": {
                        "value": "com.exlibris.external.bursar.report.fines_fees_count",
                        "desc": "Total number of fines and fees",
                    },
                    "value": "2",
                },
            ],
        },
    }


def _skip_integration_tests_when_not_dev_workspace(items):
    """Skip integration tests if WORKSPACE is not 'dev'."""
    allowed_test_environments = ["dev"]
    for item in items:
        if (
            item.get_closest_marker("integration")
            and os.getenv("WORKSPACE") not in allowed_test_environments
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "integration tests currently only support environments: "
                        f"{allowed_test_environments}"
                    )
                )
            )


def pytest_collection_modifyitems(config, items):
    """Pytest hook that is run after all tests collected.

    https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems

    It is preferred that any actions needed performed by this hook will have a dedicated
    function, keeping this hook runner relatively simple.
    """
    _skip_integration_tests_when_not_dev_workspace(items)
