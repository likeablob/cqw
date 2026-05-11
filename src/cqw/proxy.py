import asyncio
import base64
import logging
import os
import socket
import subprocess
import sys
import threading
import time

import httpx
import websockets
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


def find_available_port(
    host: str = "127.0.0.1", start: int = 5000, tries: int = 100
) -> int:
    for offset in range(tries):
        port = start + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((host, port))
                return port
        except OSError:
            continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp, username: str, password: str):
        self.app = app
        self.username = username
        self.password = password

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Basic "):
            response = Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
            )
            await response(scope, receive, send)
            return

        if not self._validate_auth(auth_header):
            response = Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    async def _handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        request = Request(scope, receive)
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Basic ") or not self._validate_auth(auth_header):
            await send(
                {"type": "websocket.close", "code": 1008, "reason": "Unauthorized"}
            )
            return

        await self.app(scope, receive, send)

    def _validate_auth(self, auth_header: str) -> bool:
        try:
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode("utf-8")
            user, pwd = decoded.split(":", 1)
            return user == self.username and pwd == self.password
        except (ValueError, UnicodeDecodeError):
            return False


_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def proxy_request(request: Request, target_url: str) -> StreamingResponse:
    url = f"{target_url}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    client = get_http_client()
    req = client.build_request(
        method=request.method,
        url=url,
        headers=headers,
        content=body,
    )
    response = await client.send(req, stream=True)

    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    response_headers = {
        k: v for k, v in response.headers.items() if k.lower() not in excluded_headers
    }

    async def generate():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()

    media_type = response.headers.get("content-type")

    return StreamingResponse(
        generate(),
        status_code=response.status_code,
        headers=response_headers,
        media_type=media_type,
    )


async def websocket_proxy(websocket: WebSocket, target_url: str) -> None:
    await websocket.accept()

    path = websocket.url.path
    query = websocket.url.query
    ws_url = f"{target_url}{path}"
    if query:
        ws_url += f"?{query}"

    if ws_url.startswith("http://"):
        ws_url = ws_url.replace("http://", "ws://")
    elif ws_url.startswith("https://"):
        ws_url = ws_url.replace("https://", "wss://")

    headers = dict(websocket.headers)
    headers.pop("host", None)
    headers.pop("authorization", None)

    try:
        async with websockets.connect(ws_url, additional_headers=headers) as target_ws:

            async def forward_to_target():
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.receive":
                            if "text" in message:
                                await target_ws.send(message["text"])
                            elif "bytes" in message:
                                await target_ws.send(message["bytes"])
                        elif message["type"] == "websocket.disconnect":
                            break
                except websockets.exceptions.ConnectionClosed:
                    pass

            async def forward_to_client():
                try:
                    async for message in target_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)
                except websockets.exceptions.ConnectionClosed:
                    pass

            await asyncio.gather(
                forward_to_target(),
                forward_to_client(),
                return_exceptions=True,
            )
    except websockets.exceptions.ConnectionClosed as e:
        logger.debug("WebSocket connection closed: %s", e)
        await websocket.close(code=1011, reason="Target connection failed")
    except OSError as e:
        logger.debug("WebSocket OSError: %s", e)
        await websocket.close(code=1011, reason="Target connection failed")
    finally:
        try:
            await websocket.close()
        except websockets.exceptions.ConnectionClosed:
            pass


def create_proxy_app(target_url: str, username: str, password: str) -> Starlette:
    async def handle(request: Request) -> StreamingResponse:
        return await proxy_request(request, target_url)

    async def ws_handle(websocket: WebSocket) -> None:
        await websocket_proxy(websocket, target_url)

    routes = [
        Route(
            "/{path:path}",
            handle,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        ),
        WebSocketRoute("/{path:path}", ws_handle),
    ]

    middleware = [Middleware(BasicAuthMiddleware, username=username, password=password)]

    return Starlette(routes=routes, middleware=middleware)


def start_proxy(
    target_url: str,
    username: str,
    password: str,
    port: int,
    verbose: bool = False,
) -> subprocess.Popen:
    log_level = "debug" if verbose else "warning"

    env = {k: v for k, v in os.environ.items() if v is not None}
    env["CQW_TARGET_URL"] = target_url
    env["CQW_USER"] = username
    env["CQW_PASS"] = password

    stdout_val = subprocess.PIPE if not verbose else None
    stderr_val = subprocess.STDOUT if not verbose else None

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cqw.proxy:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            log_level,
            "--factory",
        ],
        env=env,
        stdout=stdout_val,
        stderr=stderr_val,
    )

    return process


def create_app() -> Starlette:
    import os

    target_url = os.environ.get("CQW_TARGET_URL", "http://localhost:8080")
    username = os.environ.get("CQW_USER", "user")
    password = os.environ.get("CQW_PASS", "pass")

    return create_proxy_app(target_url, username, password)


def wait_for_proxy(host: str, port: int, timeout: int = 10) -> bool:
    start_time = time.time()
    url = f"http://{host}:{port}"

    while time.time() - start_time < timeout:
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(url)
                if response.status_code in (200, 401):
                    return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(0.2)

    return False


def drain_proxy_output(
    process: subprocess.Popen, verbose: bool = False
) -> threading.Thread:
    def _drain():
        if process.stdout is None:
            return
        try:
            for line in iter(process.stdout.readline, ""):
                if line and verbose:
                    print(f"[proxy] {line.strip()}")
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    return thread
