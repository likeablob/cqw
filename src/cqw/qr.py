import io

import qrcode
from rich.console import Console

from . import __version__

console = Console(force_terminal=True)


def get_qr_code(url: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)

    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    lines = [line for line in buffer.getvalue().split("\n") if line]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def display_startup_screen(
    tunnel_url: str,
    username: str | None,
    password: str | None,
    target: str,
    show_qr: bool = True,
) -> None:
    if username is not None and password is not None:
        authenticated_url = (
            f"https://{username}:{password}@{tunnel_url.replace('https://', '')}"
        )
    else:
        authenticated_url = tunnel_url

    header_lines = [
        f"[bold cyan]cqw[/bold cyan][bold](v{__version__})[/bold]",
        "",
        "[green]Tunnel active[/green]",
        "",
        f"[bold]Target:[/bold] [cyan]{target}[/cyan]",
        f"[bold]Tunnel:[/bold] [cyan]{tunnel_url}[/cyan]",
    ]

    if username is not None and password is not None:
        header_lines.extend(
            [
                "",
                f"[bold]Username:[/bold] {username}",
                f"[bold]Password:[/bold] {password}",
                "",
                "[dim]Authenticated URL:[/dim]",
                f"[cyan]{authenticated_url}[/cyan]",
            ]
        )
    else:
        header_lines.extend(
            [
                "",
                "[dim]URL:[/dim]",
                f"[cyan]{authenticated_url}[/cyan]",
            ]
        )

    header_lines.extend(["", "[dim]Ctrl+C to stop[/dim]"])

    console.print("\n".join(header_lines))

    if show_qr:
        console.print()
        try:
            qr_code = get_qr_code(authenticated_url)
            console.print(qr_code)
        except Exception:
            console.print("[red]QR code unavailable[/red]")
