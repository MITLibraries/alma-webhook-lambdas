import base64
import hmac
import json
import os

import requests


def generate_signature(message_body: dict) -> str:
    secret = os.environ["ALMA_CHALLENGE_SECRET"]
    message_string = json.dumps(message_body)
    message_hash = hmac.digest(
        secret.encode(), msg=message_string.encode(), digest="sha256"
    )
    return base64.b64encode(message_hash).decode()


def send_get_to_lambda_function_url(challenge_phrase: str) -> str:
    function_url = os.environ["LAMBDA_FUNCTION_URL"]
    response = requests.get(
        function_url, params={"challenge": challenge_phrase}, timeout=30
    )
    return response.text


def send_post_to_lambda_function_url(message_body: dict) -> str:
    function_url = os.environ["LAMBDA_FUNCTION_URL"]
    headers = {"x-exl-signature": generate_signature(message_body)}
    response = requests.post(function_url, headers=headers, json=message_body, timeout=30)
    return response.text
