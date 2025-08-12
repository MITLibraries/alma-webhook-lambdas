FROM public.ecr.aws/lambda/python:3.12

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY . ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN cd ${LAMBDA_TASK_ROOT} && \
    uv export --format requirements-txt --no-hashes --no-dev > requirements.txt && \
    uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --system

# Default handler. See README for how to override to a different handler.
CMD [ "lambdas.webhook.lambda_handler" ]
