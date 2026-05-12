import re
import subprocess
import sys
import time

import httpx
import pytest

from cqw.installer import get_cloudflared_path, install, is_installed
from cqw.proxy import find_available_port
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

    def _run_cqw_and_parse_url(
        self, backend_port: int, username: str, password: str, timeout: int = 30
    ) -> tuple[subprocess.Popen, str | None]:
        cmd = [
            sys.executable,
            "-m",
            "cqw.main",
            "-f",
            f"127.0.0.1:{backend_port}",
            "--user",
            username,
            "--pass",
            password,
            "--cloudflared-extra-args",
            "--protocol http2",
            "-v",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        tunnel_url = None
        url_pattern = re.compile(
            r"https://[a-z0-9-]+\.(trycloudflare\.com|cloudflare-tunnel\.com)"
        )

        start_time = time.time()
        while time.time() - start_time < timeout:
            if process.stdout is None:
                break
            line = process.stdout.readline()
            if not line:
                break

            print(f"[cqw] {line.strip()}")

            match = url_pattern.search(line)
            if match:
                tunnel_url = match.group(0)
                break

        return process, tunnel_url

    def test_full_tunnel_flow(self, cloudflared_path):
        backend_port = find_available_port(start=9000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        username = "e2euser"
        password = "e2epass"

        cqw_process, tunnel_url = self._run_cqw_and_parse_url(
            backend_port, username, password
        )
        self.processes.append(cqw_process)

        if not tunnel_url:
            print("Tunnel URL not obtained. See logs above.")
            pytest.skip("Failed to establish tunnel (quota or network issue)")

        time.sleep(2)

        url_with_auth = (
            f"https://{username}:{password}@{tunnel_url.replace('https://', '')}/health"
        )

        try:
            response = httpx.get(url_with_auth, timeout=30.0, verify=False)
            assert response.status_code == 200
            assert response.text == "OK"
        except httpx.ConnectError as e:
            print(f"Connection failed: {e}")
            pytest.skip(f"Tunnel connection failed: {e}")

    def test_tunnel_with_post(self, cloudflared_path):
        backend_port = find_available_port(start=9000)

        backend_process = start_backend(backend_port)
        self.processes.append(backend_process)

        username = "e2euser"
        password = "e2epass"

        cqw_process, tunnel_url = self._run_cqw_and_parse_url(
            backend_port, username, password
        )
        self.processes.append(cqw_process)

        if not tunnel_url:
            print("Tunnel URL not obtained. See logs above.")
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
        except httpx.ConnectError as e:
            print(f"Connection failed: {e}")
            pytest.skip(f"Tunnel connection failed: {e}")
