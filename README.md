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

### Integration Tests for Dev1

Some minimal integration tests are provided for checking the deployed webhook handling lambda, defined as `integration` type pytest tests.  These tests check the following:
  * lambda function URL is operational
  * `GET` and `POST` requests are received
  * deployed lambda has adequate permissions to communicate with S3, StepFunctions, etc.

Other notes about tests:
  * tests are limited to `Dev1` environment
  * AWS `AWSAdministratorAccess` role credentials must be set on developer machine
  * environment variable `WORKSPACE=dev` must be set
    * no other environment variables are required, these are all retrieved from deployed context

#### Steps to run integration tests

  1. Update docker image to ensure local changes are deployed to `Dev1`:

```shell
make publish-dev
make update-lambda-dev
```

  2. Run tests against deployed assets:

```shell
make test-integration
```

## Running locally with Docker

Note: this is only useful for validating exceptions and error states, as success states require calling other AWS services for which we do not currently support local emulation.

<https://docs.aws.amazon.com/lambda/latest/dg/images-test.html>

1. Build the container:

```bash
make dist-dev
```

2. Run the default handler for the container

```bash
docker run -p 9000:8080 alma-webhook-lambdas-dev:latest
```

Depending on what you're testing, you may need to pass `-e WORKSPACE=dev` and/or other environment variables as options to the `docker run` command.

3. POST to the container

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d "{}"
```

4. Observe output

Running the above with no env variables passed should result in an exception.
