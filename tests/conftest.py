import subprocess
import sys
import tempfile
import time


def start_backend(port: int) -> subprocess.Popen:
    backend_code = f"""
import json
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

async def health(request):
    return PlainTextResponse("OK")

async def json_endpoint(request):
    body = await request.json()
    return JSONResponse({{"method": "POST", "received": body}})

async def echo(request):
    body = await request.body()
    headers = dict(request.headers)
    return JSONResponse({{
        "method": request.method,
        "path": request.url.path,
        "headers": {{k: v for k, v in headers.items() if k.lower() not in ("authorization", "host")}},
        "body": body.decode() if body else None,
    }})

routes = [
    Route("/health", health, methods=["GET"]),
    Route("/json", json_endpoint, methods=["POST"]),
    Route("/{{path:path}}", echo, methods=["GET", "POST", "PUT", "DELETE"]),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port={port})
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(backend_code)
        f.flush()
        backend_path = f.name

    process = subprocess.Popen(
        [sys.executable, backend_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    time.sleep(1)
    return process
