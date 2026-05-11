# cqw

Cloudflare Quick Tunnel wrapper with Basic Auth reverse proxy.

```
[Client] -> [Cloudflare Tunnel] -> [cqw Proxy (Basic Auth)] -> [Target Service]
```

## Installation

```bash
uvx cqw
```

Or with uv tool:

```bash
uv tool install cqw
```

## Usage

```bash
cqw -f localhost:8080
cqw -f localhost:8080 --user admin --pass secret
cqw -f localhost:8080 --no-qr
cqw -f localhost:8080 -v
```

## CLI Options

| Option                     | Description                                                      |
| -------------------------- | ---------------------------------------------------------------- |
| `-f, --forward`            | Target address to forward (required)                             |
| `--user`                   | Basic auth username (default: env `CQW_USER` or random)          |
| `--pass`                   | Basic auth password (default: env `CQW_PASS` or random)          |
| `--cloudflared`            | Path to cloudflared binary (default: auto-download to cache)     |
| `--update-cloudflared`     | Update cloudflared to latest version                             |
| `--qr`                     | Enable QR code display (default: True)                           |
| `--no-qr`                  | Disable QR code display                                          |
| `-v, --verbose`            | Enable verbose logging                                           |
| `--no-proxy`               | Disable proxy and Basic Auth (tunnel only)                       |
| `--quiet`                  | Suppress cloudflared tunnel logs                                 |
| `--cloudflared-extra-args` | Extra arguments passed to cloudflared (e.g., '--protocol http2') |

## Environment Variables

- `CQW_USER`: Basic auth username (fallback: random)
- `CQW_PASS`: Basic auth password (fallback: random)

## `cloudflared` Installation

`cloudflared` is automatically downloaded to the user cache directory on first run:

- Linux: `~/.cache/cqw/cloudflared/`
- macOS: `~/Library/Caches/cqw/cloudflared/`
- Windows: `%LOCALAPPDATA%\cqw\cloudflared\`

To update to the latest version:
```bash
cqw -f localhost:8080 --update-cloudflared
```

Manual download: https://github.com/cloudflare/cloudflared/releases

## Development

```bash
# Install tools
mise trust && mise install

# Install dependencies:
uv sync

# Install pre-commit hooks:
uv run pre-commit install

# Testing
uv run pytest tests/ -v

# Linting
uv run ruff check src/
uv run ruff format src/
uv run ty check src/ tests/
```

## LICENSE

MIT
