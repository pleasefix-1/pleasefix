import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_home_renders(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"PleaseFix" in response.content


def test_about_renders(client: Client) -> None:
    response = client.get("/about/")
    assert response.status_code == 200
    assert b"scenario" in response.content
    assert b"deptree" in response.content


def test_healthz(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_version(client: Client) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json()["name"] == "pleasefix"
