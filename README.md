# alma-webhook-lambdas
Lambda functions to receive and handle Alma webhook requests

## Developing locally
<https://docs.aws.amazon.com/lambda/latest/dg/images-test.html>

### Installation and setup
- To install dependencies: `make install`
- To run tests: `make test`
- To update dependencies: `make update`

Required env variables:
- `ALMA_CHALLENGE_SECRET=itsasecret`: this value will work with the test fixtures, must
  match Alma sandbox/prod configured challenge secrets in Dev1, stage, and prod
  environments.
- `WORKSPACE=dev`: env for local development.
- `SENTRY_DSN`: only needed in production.

### To run locally
- Build the container:
  ```bash
  docker build -t alma-webhook-lambdas .
  ```
- Run the container:
  ```bash
  docker run -p 9000:8080 -e WORKSPACE=dev -e ALMA_CHALLENGE_SECRET=itsasecret \
  alma-webhook-lambdas:latest
  ```
- GET request example
  - Post data to the container:
    ```bash
    curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -H \
    "Content-Type: application/json" -d \
    '{"queryStringParameters":
    {"challenge": "challenge-accepted"}, "requestContext": {"http": {"method": "GET"}}}'
    ```
  - Observe output:
    ```json
    {
      "headers": {"Content-Type": "text/plain"},
      "isBase64Encoded": false,
      "statusCode": 200,
      "body": "challenge-accepted"
    }
    ```
- POST request example
  - Post data to the container:
    ```bash
    curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -H \
    "Content-Type: application/json" -d \
    '{"headers": {"x-exl-signature": "bbQKggzWRSuwopIwszy757lusNZWOPllfv5Rt6Qj8uE="}, "requestContext": {"http": {"method": "POST"}}, "body": {"action": "JOB_END"}}'
    ```
  - Observe output:
    ```json
    {
      "headers": {"Content-Type": "text/plain"},
      "isBase64Encoded": false,
      "statusCode": 200,
      "body": "Webhook POST request received and validated, no action taken."
    }
    ```

### To run a different handler in the container
You can call any handler you copy into the container (see Dockerfile) by name as part of the `docker run` command.

```bash
docker run -p 9000:8080 -e WORKSPACE=dev alma-webhook-lambdas:latest lambdas.ping.lambda_handler
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d "{}"
```

Should result in `pong` as the output.
