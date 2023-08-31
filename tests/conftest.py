# ruff: noqa: G004
import datetime
import logging
import os
import urllib
from importlib import reload

import boto3
import botocore.session
import pytest
import requests_mock
from botocore.exceptions import ClientError
from botocore.stub import Stubber

import lambdas.helpers
import lambdas.webhook
from lambdas.webhook import lambda_handler

ORIGINAL_ENV = os.environ.copy()


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
    os.environ[
        "PPOD_STATE_MACHINE_ARN"
    ] = "arn:aws:states:us-east-1:account:stateMachine:ppod-test"
    os.environ[
        "TIMDEX_STATE_MACHINE_ARN"
    ] = "arn:aws:states:us-east-1:account:stateMachine:timdex-test"
    os.environ[
        "BURSAR_STATE_MACHINE_ARN"
    ] = "arn:aws:states:us-east-1:account:stateMachine:bursar-test"
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
        "input": '{"job_id": "test id", "job_name": "Bursar Export to test"}',
        "name": "bursar",
    }
    with Stubber(sfn) as stubber:
        stubber.add_response("start_execution", expected_response, expected_params)
        yield sfn


@pytest.fixture
def _set_integration_tests_env_vars() -> None:
    """Fixture to set os environment variables by retrieving data from AWS.

    Because mocked AWS credentials are set in the testing environment, this temporary
    reinstating of the calling environment (e.g. developer's machine) when the tests
    began is required.  Once data about deployed assets, e.g. lambda function URL and
    deployed environment variables, is retrieved, the testing environment is used again.
    """
    # backup current, test env
    test_env = os.environ.copy()

    # set os.environ as original env before testing framework
    # ruff: noqa: B003
    os.environ = ORIGINAL_ENV

    try:
        if not os.getenv("WORKSPACE"):
            # ruff: noqa: TRY301, TRY002, TRY003, EM101
            raise Exception("WORKSPACE env var must be set for integration tests")

        # get lambda configurations
        lambda_client = boto3.client("lambda")
        lambda_function_config = lambda_client.get_function_configuration(
            FunctionName=f"alma-webhook-lambdas-{os.getenv('WORKSPACE').lower()}"
        )
        lambda_function_env_vars = lambda_function_config["Environment"]["Variables"]
        lambda_function_url = lambda_client.get_function_url_config(
            FunctionName=f"alma-webhook-lambdas-{os.getenv('WORKSPACE').lower()}"
        )["FunctionUrl"]

        # get values from parameter store
        ssm_client = boto3.client("ssm")
        ssm_client.get_parameter(Name="/apps/almahook/alma-pod-export-job-name")[
            "Parameter"
        ]["Value"]
        ppod_state_machine_arn = ssm_client.get_parameter(
            Name="/apps/almahook/ppod-state-machine-arn"
        )["Parameter"]["Value"]
        timdex_state_machine_arn = ssm_client.get_parameter(
            Name="/apps/almahook/timdex-ingest-state-machine-arn"
        )["Parameter"]["Value"]

    except:
        logging.exception("could not retrieve lambda configurations via boto3")
        raise
    finally:
        # reset testing env vars
        os.environ = test_env

    # set env vars
    os.environ["LAMBDA_FUNCTION_URL"] = lambda_function_url
    os.environ["ALMA_CHALLENGE_SECRET"] = lambda_function_env_vars[
        "ALMA_CHALLENGE_SECRET"
    ]
    os.environ["ALMA_POD_EXPORT_JOB_NAME"] = "Publishing Platform Job PPOD EXPORT to Dev1"
    os.environ["PPOD_STATE_MACHINE_ARN"] = ppod_state_machine_arn
    os.environ["VALID_POD_EXPORT_DATE"] = "2023-08-15"  # matches fixture date
    os.environ["TIMDEX_STATE_MACHINE_ARN"] = timdex_state_machine_arn
    os.environ["VALID_TIMDEX_EXPORT_DATE"] = "2023-08-15"  # matches fixture date


@pytest.fixture
def _integration_tests_s3_fixtures(_set_integration_tests_env_vars) -> None:
    """Upload integration test fixtures to S3, if they don't already exist.

    These s3 files are used by deployed assets during integration tests.  This fixture
    relies on _set_integration_tests_env_vars as a dependency to ensure AWS credentials
    have not been clobbered by testing env vars.
    """
    s3 = boto3.client("s3")

    def check_and_upload_file(bucket, key):
        try:
            s3.head_object(Bucket=bucket, Key=key + "foo")
            logging.info(f"File s3://{bucket}/{key} already exists, nothing to do!")
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            # ruff: noqa: PLR2004
            if error_code == 404:
                logging.info(f"File s3://{bucket}/{key} not found. Uploading...")
                local_file_path = os.path.join("tests", "fixtures", os.path.basename(key))
                if os.path.exists(local_file_path):
                    s3.upload_file(local_file_path, bucket, key)
                    logging.info(f"File uploaded to s3://{bucket}/{key}")
                else:
                    msg = f"Fixture file {local_file_path} does not exist."
                    logging.exception(msg)
                    raise FileNotFoundError(msg) from None
            else:
                raise

    # Specify your bucket and key
    fixtures = [
        (
            "dev-sftp-shared",
            "exlibris/pod/POD_ALMA_EXPORT_20230815_220844[016]_new.tar.gz",
        ),
        (
            "dev-sftp-shared",
            "exlibris/timdex/TIMDEX_ALMA_EXPORT_DAILY_20230815_220844[016]_new.tar.gz",
        ),
    ]
    for bucket, key in fixtures:
        check_and_upload_file(bucket, key)


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
            "name": os.getenv("ALMA_POD_EXPORT_JOB_NAME", "PPOD Export"),
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
            "name": "Publishing Platform Job TIMDEX EXPORT to Dev1 DAILY",
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


def pytest_collection_modifyitems(config, items):
    """Hook that is run after all tests collected, which allows for modification pre-run.

    https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems
    """
    # skip integration tests if WORKSPACE is not 'dev'
    allowed_test_environments = ["dev"]
    for item in items:
        if (
            item.get_closest_marker("integration")
            and os.getenv("WORKSPACE") not in allowed_test_environments
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason="integration tests currently only support environments: %s"
                    % allowed_test_environments
                )
            )
