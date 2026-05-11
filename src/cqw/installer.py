import json
import os
import platform
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from platformdirs import user_cache_dir

CACHE_DIR = Path(user_cache_dir("cqw", "cqw"))
CLOUDFLARED_DIR = CACHE_DIR / "cloudflared"
RELEASES_URL = "https://github.com/cloudflare/cloudflared/releases"
LATEST_RELEASE_API = (
    "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
)


def get_platform_info() -> tuple[str, str]:
    """Return (os_type, arch) for download URL construction."""
    os_type = sys.platform
    if os_type == "win32":
        os_type = "windows"
    elif os_type == "darwin":
        os_type = "darwin"
    else:
        os_type = "linux"

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = "amd64"

    return os_type, arch


def get_binary_name() -> str:
    """Return the binary filename for current platform."""
    if sys.platform == "win32":
        return "cloudflared.exe"
    return "cloudflared"


def get_cloudflared_path() -> Path:
    """Return the path where cloudflared binary is cached."""
    return CLOUDFLARED_DIR / get_binary_name()


def get_download_url() -> str:
    """Construct the download URL for current platform."""
    os_type, arch = get_platform_info()

    base_url = "https://github.com/cloudflare/cloudflared/releases/latest/download"

    if os_type == "windows":
        filename = f"cloudflared-{os_type}-{arch}.exe"
    elif os_type == "darwin":
        filename = f"cloudflared-{os_type}-{arch}.tgz"
    else:
        filename = f"cloudflared-{os_type}-{arch}"

    return f"{base_url}/{filename}"


def get_manual_install_url() -> str:
    """Return the URL for manual download instructions."""
    return RELEASES_URL


def get_latest_version() -> str | None:
    """Get latest cloudflared version from GitHub API."""
    try:
        headers = {"Accept": "application/vnd.github+json"}
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        req = urllib.request.Request(LATEST_RELEASE_API, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("tag_name")
    except Exception:
        return None


def get_installed_version() -> str | None:
    """Get version string of installed cloudflared."""
    path = get_cloudflared_path()
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def is_installed() -> bool:
    """Check if cloudflared binary exists and is executable."""
    path = get_cloudflared_path()
    if not path.exists():
        return False
    if sys.platform != "win32":
        if not os.access(path, os.X_OK):
            return False
    return True


def _extract_macos(tgz_path: Path, dest_dir: Path) -> bool:
    """Extract cloudflared from macOS tgz file (atomic update)."""
    # TODO: Add console logging for extraction failure indication
    try:
        target_path = dest_dir / get_binary_name()
        tmp_path = dest_dir / f"{get_binary_name()}.tmp"

        with tarfile.open(tgz_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("cloudflared") and member.isfile():
                    member.name = tmp_path.name
                    tf.extract(member, dest_dir)
                    os.replace(str(tmp_path), str(target_path))
                    return True
    except tarfile.TarError:
        return False
    return False


def download(console=None) -> bool:
    """Download and install cloudflared from GitHub releases."""
    CLOUDFLARED_DIR.mkdir(parents=True, exist_ok=True)

    url = get_download_url()
    os_type, _ = get_platform_info()
    target_path = get_cloudflared_path()

    if console:
        latest_version = get_latest_version()
        if latest_version:
            console.print(f"[dim]Latest version: {latest_version}[/dim]")
        console.print(f"[dim]Downloading: {url}[/dim]")
        console.print(f"[dim]Destination: {target_path}[/dim]")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

            progress_data = {"count": 0, "total": 0}

            def progress_hook(count, block_size, total_size):
                progress_data["count"] = count
                progress_data["total"] = total_size
                if console and total_size > 0:
                    downloaded = count * block_size
                    percent = min(100, int(downloaded * 100 / total_size))
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    console.print(
                        f"[dim]Progress: {percent}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)[/dim]",
                        end="\r",
                    )

            urllib.request.urlretrieve(url, tmp_path, progress_hook)

        if console:
            console.print()

        if os_type == "windows":
            os.replace(str(tmp_path), str(target_path))
            success = True
        elif os_type == "darwin":
            success = _extract_macos(tmp_path, CLOUDFLARED_DIR)
        else:
            os.replace(str(tmp_path), str(target_path))
            success = True

        if tmp_path:
            tmp_path.unlink(missing_ok=True)

        if success:
            binary_path = get_cloudflared_path()
            if sys.platform != "win32":
                binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
            if console:
                installed_version = get_installed_version()
                if installed_version:
                    console.print(f"[green]Installed: {installed_version}[/green]")
            return True

    except (urllib.error.URLError, OSError) as e:
        if console:
            console.print(f"[red]Download failed: {e}[/red]")
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        return False

    return False


def update(console=None) -> bool:
    """Update cloudflared to latest version (atomic update)."""
    old_version = get_installed_version()
    if console and old_version:
        console.print(f"[dim]Previous version: {old_version}[/dim]")
    return download(console)


def install(console=None) -> bool:
    """Install cloudflared if not already installed."""
    if is_installed():
        return True
    return download(console)
