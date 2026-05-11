import json
import os
import re
import subprocess
import threading
from collections.abc import Generator

from rich.console import Console

console = Console()


def start_cloudflared(
    port: int,
    cloudflared_path: str = "cloudflared",
    verbose: bool = False,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, str | None]:
    target_url = f"http://127.0.0.1:{port}"
    return _start_cloudflared_process(target_url, cloudflared_path, verbose, extra_args)


def start_cloudflared_direct(
    target_url: str,
    cloudflared_path: str = "cloudflared",
    verbose: bool = False,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, str | None]:
    return _start_cloudflared_process(target_url, cloudflared_path, verbose, extra_args)


def _start_cloudflared_process(
    target_url: str, cloudflared_path: str, verbose: bool, extra_args: list[str] | None
) -> tuple[subprocess.Popen, str | None]:
    cmd = [
        cloudflared_path,
        "tunnel",
        "--no-autoupdate",
        "--url",
        target_url,
        "--output",
        "json",
    ]

    if extra_args:
        cmd.extend(extra_args)

    env = {k: v for k, v in os.environ.items() if v is not None}
    env["NO_AUTOUPDATE"] = "true"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )

    url = None
    url_pattern = re.compile(
        r"https://[a-z0-9-]+\.(trycloudflare\.com|cloudflare-tunnel\.com)"
    )

    for line in _iter_lines(process):
        if verbose:
            console.print(f"[dim]{line.strip()}[/dim]")

        try:
            data = json.loads(line)
            msg = data.get("message", "")
            match = url_pattern.search(msg)
            if match:
                url = match.group(0)
                break
        except json.JSONDecodeError:
            match = url_pattern.search(line)
            if match:
                url = match.group(0)
                break

        if "error" in line.lower():
            console.print(f"[red]cloudflared error: {line.strip()}[/red]")

    return process, url


def _iter_lines(process: subprocess.Popen) -> Generator[str, None, None]:
    if process.stdout is None:
        return
    stdout = process.stdout
    try:
        for line in iter(stdout.readline, ""):
            if line:
                yield line
    except ValueError:
        pass


def drain_output(process: subprocess.Popen, show_logs: bool = True) -> threading.Thread:
    def _drain():
        if process.stdout is None:
            return
        stdout = process.stdout
        try:
            for line in iter(stdout.readline, ""):
                if line and show_logs:
                    console.print(f"[dim]{line.strip()}[/dim]")
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    return thread
