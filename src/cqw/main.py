import asyncio
import signal
import subprocess
import sys
import time

from rich.console import Console

from . import __version__
from .config import CLISettings
from .installer import (
    get_cloudflared_path,
    get_manual_install_url,
    install,
    is_installed,
    update,
)
from .proxy import (
    close_http_client,
    drain_proxy_output,
    find_available_port,
    start_proxy,
    wait_for_proxy,
)
from .qr import display_startup_screen
from .tunnel import drain_output, start_cloudflared, start_cloudflared_direct

console = Console()


def cleanup_process(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def wait_for_shutdown(
    tunnel_process: subprocess.Popen,
    proxy_process: subprocess.Popen | None = None,
) -> bool:
    shutdown_event = False

    def signal_handler(signum: int, frame: object) -> None:
        nonlocal shutdown_event
        shutdown_event = True

    old_sigint = signal.signal(signal.SIGINT, signal_handler)
    old_sigterm = signal.signal(signal.SIGTERM, signal_handler)

    try:
        while not shutdown_event:
            if proxy_process is not None and proxy_process.poll() is not None:
                console.print(
                    f"\n[dim]Proxy stopped (code: {proxy_process.returncode})[/dim]"
                )
                break
            if tunnel_process.poll() is not None:
                console.print(
                    f"\n[dim]Tunnel stopped (code: {tunnel_process.returncode})[/dim]"
                )
                break
            time.sleep(0.1)
    finally:
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)

    return shutdown_event


def final_cleanup(
    tunnel_process: subprocess.Popen,
    proxy_process: subprocess.Popen | None = None,
) -> None:
    old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    old_sigterm = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        if proxy_process is not None:
            cleanup_process(proxy_process, "proxy")
        cleanup_process(tunnel_process, "tunnel")
        try:
            asyncio.run(close_http_client())
        except RuntimeError:
            pass
    finally:
        signal.signal(signal.SIGINT, old_handler)
        signal.signal(signal.SIGTERM, old_sigterm)


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        console.print(f"cqw(v{__version__})")
        return 0

    config = CLISettings()

    cloudflared_path = config.cloudflared
    if cloudflared_path:
        console.print(f"[dim]Using specified cloudflared: {cloudflared_path}[/dim]")
    elif config.update_cloudflared:
        console.print("[cyan]Updating cloudflared...[/cyan]")
        if not update(console):
            console.print("[red]Failed to update cloudflared[/red]")
            console.print(f"[dim]Manual download: {get_manual_install_url()}[/dim]")
            return 1
        cloudflared_path = str(get_cloudflared_path())
    elif is_installed():
        cloudflared_path = str(get_cloudflared_path())
        console.print(f"[dim]Using cached cloudflared: {cloudflared_path}[/dim]")
    else:
        console.print("[cyan]Installing cloudflared...[/cyan]")
        if not install(console):
            console.print("[red]Failed to install cloudflared[/red]")
            console.print(f"[dim]Manual download: {get_manual_install_url()}[/dim]")
            return 1
        cloudflared_path = str(get_cloudflared_path())

    if config.no_proxy:
        with console.status("[cyan]Establishing tunnel...[/cyan]", spinner="dots"):
            tunnel_process, tunnel_url = start_cloudflared_direct(
                config.forward_url,
                cloudflared_path,
                config.verbose,
                config.cloudflared_args_list,
            )

            if not tunnel_url:
                console.print("[red]Error: Failed to establish tunnel[/red]")
                cleanup_process(tunnel_process, "tunnel")
                return 1

        display_startup_screen(
            tunnel_url=tunnel_url,
            username=None,
            password=None,
            target=config.forward,
            show_qr=config.qr,
        )

        drain_output(tunnel_process, show_logs=not config.quiet)

        shutdown_event = wait_for_shutdown(tunnel_process)

        if shutdown_event:
            console.print("\n[dim]Shutting down...[/dim]")

        final_cleanup(tunnel_process)

        return 0

    proxy_port = find_available_port()

    with console.status("[cyan]Starting proxy...[/cyan]", spinner="dots"):
        proxy_process = start_proxy(
            target_url=config.forward_url,
            username=config.user,
            password=config.password,
            port=proxy_port,
            verbose=config.verbose,
        )

        if not wait_for_proxy("127.0.0.1", proxy_port):
            console.print("[red]Error: Proxy failed to start[/red]")
            cleanup_process(proxy_process, "proxy")
            return 1

    with console.status("[cyan]Establishing tunnel...[/cyan]", spinner="dots"):
        tunnel_process, tunnel_url = start_cloudflared(
            proxy_port, cloudflared_path, config.verbose, config.cloudflared_args_list
        )

        if not tunnel_url:
            console.print("[red]Error: Failed to establish tunnel[/red]")
            cleanup_process(proxy_process, "proxy")
            cleanup_process(tunnel_process, "tunnel")
            return 1

    display_startup_screen(
        tunnel_url=tunnel_url,
        username=config.user,
        password=config.password,
        target=config.forward,
        show_qr=config.qr,
    )

    drain_proxy_output(proxy_process, config.verbose)
    drain_output(tunnel_process, show_logs=not config.quiet)

    shutdown_event = wait_for_shutdown(tunnel_process, proxy_process)

    if shutdown_event:
        console.print("\n[dim]Shutting down...[/dim]")

    final_cleanup(tunnel_process, proxy_process)

    return 0


if __name__ == "__main__":
    sys.exit(main())
