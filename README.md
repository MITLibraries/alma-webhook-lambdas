# alma-webhook-lambdas

Lambda functions to receive and handle Alma webhook requests.

## Alma configuration

Enterprise Systems handles webhook configuration in Alma, however there are some important things to know about how this configuration works. We currently have two workflows that use Alma webhooks to trigger data pipeline processes: the POD metadata
upload and the TIMDEX pipeline. Both of these call the webhook URL on "job end", when Alma completes a job internally. Because of how Alma webhooks are configured, posts to our webhook URLs get sent on _every_ job end, not just the jobs we care about. This means we have to do a lot of checks within the webhook lambda function to identify which webhook calls should trigger the POD and TIMDEX actions. Webhook posts for other job end tasks simply log the call and return a response to Alma without triggering further action.

In addition, we have two Alma instances (sandbox and production), but three AWS infrastructure environments (Dev1, Stage, and Prod). In order to have a full dev/stage/prod deployment pipeline for testing, we have jobs and webhooks configured from production Alma to both the stage and prod AWS environments. Again, because of how Alma webhooks work, _both_ the stage and prod webhooks get called on _every_ job end. This means that, for example, a POD export to stage from Alma prod will call both the stage and prod webhook URLs. However, we only want to trigger an action in AWS if the job that caused the webhook call was configured for the same environment that this webhook lambda is running in, so that "stage" configured jobs only trigger actions in stage and "prod" configured jobs only trigger actions in prod. The stage/prod job configurations in production Alma are differentiated by the job name; jobs that send data to stage will have "stage" somwhere in the job name and likewise jobs that send data to prod will have "prod" in the job name. Therefore it is important that new pipeline jobs include those values in the name when configured in Alma, and that this webhook checks the job name \to confirm it matches the current runtime environment before triggering the relevant action.

## Developing locally

### Installation and setup

- To install dependencies: `make install`
- To run tests: `make test`
- To update dependencies: `make update`

Required env variables:

- `ALMA_CHALLENGE_SECRET=itsasecret`: this value will work with the test fixtures, must match Alma sandbox/prod configured challenge secrets in Dev1, stage, and prod environments.
- `ALMA_BURSAR_EXPORT_JOB_NAME`: the exact name of the Bursar export job in Alma. Must match Alma sandbox/prod configured job names.
- `ALMA_POD_EXPORT_JOB_NAME`: the exact name of the POD export job in Alma. Must match Alma sandbox/prod configured job names.
- `ALMA_TIMDEX_EXPORT_JOB_NAME_PREFIX`: the exact name of the TIMDEX export job in Alma, _up to the point where it differs export type_, e.g. "Publishing Platform Job TIMDEX EXPORT to Dev1". Must match Alma sandbox/prod configured job names.
- `BURSAR_STATE_MACHINE_ARN`: the arn of the step functions Bursar state machine. Specific to each environment.
- `PPOD_STATE_MACHINE_ARN`: the arn of the step functions PPOD state machine. Specific to each environment.
- `TIMDEX_STATE_MACHINE_ARN`: the arn of the step functions TIMDEX state machine. Specific to each environment.
- `WORKSPACE=dev`: env for local development, set by Terraform in AWS environments.
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

- Send a POST request mimicking a webhook POST (not a POD or TIMDEX export job)

  ```bash
  pipenv run python -c "from lambdas.helpers import send_post_to_lambda_function_url, SAMPLE_WEBHOOK_POST_BODY; print(send_post_to_lambda_function_url(SAMPLE_WEBHOOK_POST_BODY))"
  ```

  Observe output: `Webhook POST request received and validated, no action taken.`

- Send a POST request mimicking a POD export job webhook
  _Note_: sending a request that mimics a POD export JOB_END will trigger the entire POD workflow, which is fine _in Dev1 only_ for testing.

  Add the following to your .env:
  - `VALID_POD_EXPORT_DATE=<the date of a POD export with files in the Dev1 S3 export bucket, in "YYYY-MM-DD" format>` Note: if it's been a while since the last POD export from Alma sandbox, there may be no files in the Dev1 S3 export bucket and you may need to run the publishing job from the sandbox.

  ```bash
  pipenv run python -c "from lambdas.helpers import send_post_to_lambda_function_url, SAMPLE_POD_EXPORT_JOB_END_WEBHOOK_POST_BODY; print(send_post_to_lambda_function_url(SAMPLE_POD_EXPORT_JOB_END_WEBHOOK_POST_BODY))"
  ```

  Observe output: `Webhook POST request received and validated, PPOD pipeline initiated.` and then check the Dev1 ppod state machine logs to confirm the entire process ran!

- Send a POST request mimicking a TIMDEX export job webhook
  _Note_: sending a request that mimics a TIMDEX export JOB_END will trigger the entire TIMDEX workflow, which is fine _in Dev1 only_ for testing.

  Add the following to your .env:
  - `VALID_TIMDEX_EXPORT_DATE=<the date of a TIMDEX export with files in the Dev1 S3 export bucket, in "YYYY-MM-DD" format>` Note: if it's been a while since the last TIMDEX export from Alma sandbox, there may be no files in the Dev1 S3 export bucket and you may need to run the publishing job from the sandbox.

  ```bash
  pipenv run python -c "from lambdas.helpers import send_post_to_lambda_function_url, SAMPLE_TIMDEX_EXPORT_JOB_END_WEBHOOK_POST_BODY; print(send_post_to_lambda_function_url(SAMPLE_TIMDEX_EXPORT_JOB_END_WEBHOOK_POST_BODY))"
  ```

  Observe output: `Webhook POST request received and validated, TIMDEX pipeline initiated.` and then check the Dev1 timdex state machine logs to confirm the entire process ran!

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
