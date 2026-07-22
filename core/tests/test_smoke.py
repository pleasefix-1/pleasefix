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


def test_home_in_malay(client: Client) -> None:
    response = client.get("/", HTTP_ACCEPT_LANGUAGE="ms")
    assert b"Laporkan. Jejaki. Sehingga selesai." in response.content


def test_language_switcher_present(client: Client) -> None:
    response = client.get("/")
    assert b'name="language" value="ms"' in response.content


def test_account_pages_use_site_shell(client: Client) -> None:
    for path in ("/accounts/login/", "/accounts/signup/", "/accounts/password/reset/"):
        content = client.get(path).content.decode()
        assert 'class="brand"' in content, path  # our header
        assert "/i18n/setlang/" in content, path  # our footer
        assert "PleaseFix" in content, path


def test_healthz(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_version(client: Client) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json()["name"] == "pleasefix"
