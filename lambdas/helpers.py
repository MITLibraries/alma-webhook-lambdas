import base64
import hmac
import json
import os

import requests

SAMPLE_WEBHOOK_POST_BODY = {
    "action": "JOB_END",
    "job_instance": {
        "name": "Not a POD export job",
    },
}

SAMPLE_POD_EXPORT_JOB_END_WEBHOOK_POST_BODY = {
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

SAMPLE_TIMDEX_EXPORT_JOB_END_WEBHOOK_POST_BODY = {
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


def generate_signature(message_body: dict) -> str:
    secret = os.environ["ALMA_CHALLENGE_SECRET"]
    message_string = json.dumps(message_body)
    message_hash = hmac.digest(
        secret.encode(), msg=message_string.encode(), digest="sha256"
    )
    signature = base64.b64encode(message_hash).decode()
    return signature


def send_get_to_lambda_function_url(challenge_phrase: str) -> str:
    function_url = os.environ["LAMBDA_FUNCTION_URL"]
    response = requests.get(
        function_url, params={"challenge": challenge_phrase}, timeout=30
    )
    return response.text


def send_post_to_lambda_function_url(message_body: dict) -> str:
    function_url = os.environ["LAMBDA_FUNCTION_URL"]
    headers = {"x-exl-signature": generate_signature(message_body)}
    response = requests.post(
        function_url, headers=headers, json=message_body, timeout=30
    )
    return response.text
