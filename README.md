# alma-webhook-lambdas
Lambda functions to receive and handle Alma webhook requests

## Developing locally
<https://docs.aws.amazon.com/lambda/latest/dg/images-test.html>

### Installation and setup
- To install dependencies: `make install`
- To run tests: `make test`
- To update dependencies: `make update`

Required env variables:
- `WORKSPACE=dev` (for local development)
- `SENTRY_DSN` (only needed in production)

### To run locally
- Build the container:
  ```bash
  docker build -t alma-webhook-lambdas .
  ```
- Run the container:
  ```bash
  docker run -p 9000:8080 -e WORKSPACE=dev alma-webhook-lambdas:latest
  ```
- Post data to the container:
  ```bash
  curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -H \
  'Content-Type: application/json' -d \
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

### To run a different handler in the container
You can call any handler you copy into the container (see Dockerfile) by name as part of the `docker run` command.

```bash
docker run -p 9000:8080 -e WORKSPACE=dev alma-webhook-lambdas:latest lambdas.ping.lambda_handler
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d "{}"
```

Should result in `pong` as the output.
