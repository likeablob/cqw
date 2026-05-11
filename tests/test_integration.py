import base64
import subprocess

import httpx
import pytest

from cqw.proxy import find_available_port, start_proxy, wait_for_proxy
from tests.conftest import start_backend


class TestIntegration:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        self.processes = []
        yield
        for proc in self.processes:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def test_proxy_to_backend_get(self):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username="testuser",
            password="testpass",
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=5):
            pytest.fail("Proxy failed to start")

        credentials = base64.b64encode(b"testuser:testpass").decode()
        response = httpx.get(
            f"http://127.0.0.1:{proxy_port}/test",
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10.0,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "GET"
        assert "/test" in data["path"]

    def test_proxy_to_backend_post(self):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username="testuser",
            password="testpass",
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=5):
            pytest.fail("Proxy failed to start")

        credentials = base64.b64encode(b"testuser:testpass").decode()
        response = httpx.post(
            f"http://127.0.0.1:{proxy_port}/json",
            headers={"Authorization": f"Basic {credentials}"},
            json={"key": "value"},
            timeout=10.0,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "POST"
        assert data["received"]["key"] == "value"

    def test_proxy_rejects_unauthorized(self):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username="testuser",
            password="testpass",
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=5):
            pytest.fail("Proxy failed to start")

        response = httpx.get(
            f"http://127.0.0.1:{proxy_port}/test",
            timeout=10.0,
        )

        assert response.status_code == 401

    def test_proxy_headers_filtering(self):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username="testuser",
            password="testpass",
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=5):
            pytest.fail("Proxy failed to start")

        credentials = base64.b64encode(b"testuser:testpass").decode()
        response = httpx.get(
            f"http://127.0.0.1:{proxy_port}/",
            headers={
                "Authorization": f"Basic {credentials}",
                "X-Custom-Header": "custom-value",
            },
            timeout=10.0,
        )

        assert response.status_code == 200
        data = response.json()
        headers = data.get("headers", {})
        assert "x-custom-header" in headers
        assert headers["x-custom-header"] == "custom-value"
