import base64

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from cqw.proxy import (
    BasicAuthMiddleware,
    close_http_client,
    create_proxy_app,
    find_available_port,
    get_http_client,
)


class TestGetHttpClient:
    def test_singleton_behavior(self):
        get_http_client()
        client1 = get_http_client()
        client2 = get_http_client()
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_http_client(self):
        get_http_client()
        await close_http_client()

        from cqw import proxy

        assert proxy._http_client is None

    @pytest.mark.asyncio
    async def test_recreate_after_close(self):
        get_http_client()
        await close_http_client()

        client = get_http_client()
        assert client is not None


class TestFindAvailablePort:
    def test_returns_int(self):
        port = find_available_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_returns_different_ports(self):
        ports = [find_available_port() for _ in range(5)]
        assert len(set(ports)) >= 1

    def test_custom_start(self):
        port = find_available_port(start=6000)
        assert port >= 6000


class TestBasicAuthMiddleware:
    def test_allows_valid_credentials(self):
        async def app(scope, receive, send):
            await JSONResponse({"status": "ok"})(scope, receive, send)

        middleware = BasicAuthMiddleware(app, "admin", "secret")
        client = TestClient(middleware)

        credentials = base64.b64encode(b"admin:secret").decode()
        response = client.get("/", headers={"Authorization": f"Basic {credentials}"})

        assert response.status_code == 200

    def test_rejects_invalid_credentials(self):
        async def app(scope, receive, send):
            await JSONResponse({"status": "ok"})(scope, receive, send)

        middleware = BasicAuthMiddleware(app, "admin", "secret")
        client = TestClient(middleware)

        credentials = base64.b64encode(b"admin:wrong").decode()
        response = client.get("/", headers={"Authorization": f"Basic {credentials}"})

        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == "Basic"

    def test_rejects_missing_header(self):
        async def app(scope, receive, send):
            await JSONResponse({"status": "ok"})(scope, receive, send)

        middleware = BasicAuthMiddleware(app, "admin", "secret")
        client = TestClient(middleware)

        response = client.get("/")

        assert response.status_code == 401

    def test_rejects_invalid_header_format(self):
        async def app(scope, receive, send):
            await JSONResponse({"status": "ok"})(scope, receive, send)

        middleware = BasicAuthMiddleware(app, "admin", "secret")
        client = TestClient(middleware)

        response = client.get("/", headers={"Authorization": "Bearer token"})

        assert response.status_code == 401

    def test_rejects_malformed_base64(self):
        async def app(scope, receive, send):
            await JSONResponse({"status": "ok"})(scope, receive, send)

        middleware = BasicAuthMiddleware(app, "admin", "secret")
        client = TestClient(middleware)

        response = client.get("/", headers={"Authorization": "Basic !!!invalid"})

        assert response.status_code == 401


class TestCreateProxyApp:
    def test_creates_starlette_app(self):
        app = create_proxy_app("http://localhost:8080", "user", "pass")
        assert app is not None
        assert len(app.routes) == 2

    def test_app_auth_required(self):
        app = create_proxy_app("http://localhost:8080", "user", "pass")
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 401
