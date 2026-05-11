import subprocess
import time

import httpx
import pytest

from cqw.installer import get_cloudflared_path, install, is_installed
from cqw.proxy import find_available_port, start_proxy, wait_for_proxy
from cqw.tunnel import start_cloudflared
from tests.conftest import start_backend


@pytest.fixture(scope="module")
def ensure_cloudflared():
    if not is_installed():
        assert install(), "Failed to install cloudflared"
    return str(get_cloudflared_path())


@pytest.fixture(scope="module")
def cloudflared_path(ensure_cloudflared):
    return ensure_cloudflared


class TestE2E:
    @pytest.fixture(autouse=True)
    def cleanup_processes(self):
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

    def test_full_tunnel_flow(self, cloudflared_path):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        username = "e2euser"
        password = "e2epass"

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username=username,
            password=password,
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=10):
            pytest.fail("Proxy failed to start")

        tunnel_process, tunnel_url = start_cloudflared(proxy_port, cloudflared_path)
        self.processes.append(tunnel_process)

        if not tunnel_url:
            pytest.skip("Failed to establish tunnel (quota or network issue)")

        time.sleep(2)

        url_with_auth = (
            f"https://{username}:{password}@{tunnel_url.replace('https://', '')}/health"
        )

        try:
            response = httpx.get(url_with_auth, timeout=30.0, verify=False)
            assert response.status_code == 200
            assert response.text == "OK"
        except httpx.ConnectError:
            pytest.skip("Tunnel connection failed (may be quota limited)")

    def test_tunnel_with_post(self, cloudflared_path):
        backend_port = find_available_port(start=9000)
        proxy_port = find_available_port(start=5000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        username = "e2euser"
        password = "e2epass"

        proxy_process = start_proxy(
            target_url=f"http://127.0.0.1:{backend_port}",
            username=username,
            password=password,
            port=proxy_port,
            verbose=False,
        )
        self.processes.append(proxy_process)

        if not wait_for_proxy("127.0.0.1", proxy_port, timeout=10):
            pytest.fail("Proxy failed to start")

        tunnel_process, tunnel_url = start_cloudflared(proxy_port, cloudflared_path)
        self.processes.append(tunnel_process)

        if not tunnel_url:
            pytest.skip("Failed to establish tunnel (quota or network issue)")

        time.sleep(2)

        url_with_auth = (
            f"https://{username}:{password}@{tunnel_url.replace('https://', '')}/test"
        )

        try:
            response = httpx.post(
                url_with_auth,
                json={"test": "data"},
                timeout=30.0,
                verify=False,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["method"] == "POST"
        except httpx.ConnectError:
            pytest.skip("Tunnel connection failed (may be quota limited)")
