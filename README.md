# alma-webhook-lambdas

Lambda functions to receive and handle Alma webhook requests

## Developing locally

### Installation and setup

- To install dependencies: `make install`
- To run tests: `make test`
- To update dependencies: `make update`

Required env variables:

- `ALMA_CHALLENGE_SECRET=itsasecret`: this value will work with the test fixtures, must
  match Alma sandbox/prod configured challenge secrets in Dev1, stage, and prod
  environments.
- `ALMA_POD_EXPORT_JOB_NAME`: the exact name of the POD export job in Alma, must match
  Alma sandbox/prod configured job name in Dev1, stage, and prod environments.
- `PPOD_STATE_MACHINE_ARN`: the arn of the step functions state machine. Specific to each environment.
- `WORKSPACE=dev`: env for local development.
- `SENTRY_DSN`: only needed in production.

### To verify local changes in Dev1

- Ensure your aws cli is configured with credentials for the Dev1 account.
- Ensure you have the above env variables set in your .env, matching those in our Dev1 environment.
- Add the following to your .env: `LAMBDA_FUNCTION_URL=<the Dev1 lambda function URL>`
- Publish the lambda function:

  ```bash
  make publish-dev
  make update-lambda-dev
  ```

#### GET request example

- Send a GET request with challenge phrase to the lambda function URL:

  ```bash
  pipenv run python -c "from lambdas.helpers import send_get_to_lambda_function_url; print(send_get_to_lambda_function_url('your challenge phrase'))"
  ```

  Observe output: `your challenge phrase`

#### POST request examples

- Send a POST request mimicking a webhook POST (not a POD export job)

  ```bash
  pipenv run python -c "from lambdas.helpers import send_post_to_lambda_function_url, SAMPLE_WEBHOOK_POST_BODY; print(send_post_to_lambda_function_url(SAMPLE_WEBHOOK_POST_BODY))"
  ```

  Observe output: `Webhook POST request received and validated, no action taken.`

- Send a POST request mimicking a POD export job webhook
  *Note*: sending a request that mimics a POD export JOB_END will trigger the entire POD workflow, which is fine *in Dev1 only* for testing.

  Add the following to your .env:
  - `VALID_POD_EXPORT_DATE=<the date of a POD export with files in the Dev1 S3 export bucket, in "YYYY-MM-DD" format>` Note: if it's been a while since the last POD export from Alma sandbox, there may be no files in the Dev1 S3 export bucket and you may need to run the publishing job from the sandbox.

  ```bash
  pipenv run python -c "from lambdas.helpers import send_post_to_lambda_function_url, SAMPLE_POD_EXPORT_JOB_END_WEBHOOK_POST_BODY; print(send_post_to_lambda_function_url(SAMPLE_POD_EXPORT_JOB_END_WEBHOOK_POST_BODY))"
  ```

  Observe output: `Webhook POST request received and validated, POD upload initiated.` and then check the Dev1 ppod state machine logs to confirm the entire process ran!

## Running locally with Docker

Note: this is only useful for validating exceptions and error states, as success states require calling other AWS services for which we do not currently support local emulation.

<https://docs.aws.amazon.com/lambda/latest/dg/images-test.html>

### Build the container

```bash
make dist-dev
```

### Run the default handler for the container

```bash
docker run -p 9000:8080 alma-webhook-lambdas-dev:latest
```

Depending on what you're testing, you may need to pass `-e WORKSPACE=dev` and/or other environment variables as options to the `docker run` command.

### POST to the container

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d "{}"
```

### Observe output

Running the above with no env variables passed should result in an exception.
