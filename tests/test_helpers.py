from lambdas.helpers import (
    SAMPLE_WEBHOOK_POST_BODY,
    generate_signature,
    send_get_to_lambda_function_url,
    send_post_to_lambda_function_url,
)


def test_generate_signature_dict_body():
    assert (
        generate_signature({"key": "value"})
        == "LGDc/m21XaGvd2a9416uCJk6ZwqyknX+GwCE8Ch4T8A="
    )


def test_generate_signature_string_body():
    assert generate_signature("message") == "tp4YILPZGmIjcZLSaTa+3Ws+1BuNzeZI3byc7gcQ604="


def test_send_get_to_lambda_function_url(mocked_lambda_function_url):
    assert send_get_to_lambda_function_url("hello, lambda!") == "hello, lambda!"


def test_send_post_to_lambda_function_url(mocked_lambda_function_url):
    assert (
        send_post_to_lambda_function_url(SAMPLE_WEBHOOK_POST_BODY)
        == "Webhook POST request received and validated, no action taken."
    )
