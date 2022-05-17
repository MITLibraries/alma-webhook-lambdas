import os

import pytest


@pytest.fixture(autouse=True)
def test_env():
    os.environ = {"WORKSPACE": "test"}
    yield
