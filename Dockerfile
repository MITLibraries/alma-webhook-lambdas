FROM public.ecr.aws/lambda/python:3.13

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR ${LAMBDA_TASK_ROOT}

COPY pyproject.toml uv.lock ./

RUN uv export --locked --no-dev --no-emit-project \
        --format requirements.txt --output-file /tmp/requirements.txt && \
    uv pip install --system --no-deps -r /tmp/requirements.txt \
        --target "${LAMBDA_TASK_ROOT}"

COPY . ${LAMBDA_TASK_ROOT}/

CMD ["lambdas.webhook.lambda_handler"]
