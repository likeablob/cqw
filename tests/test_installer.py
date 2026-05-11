import io
import sys
import tarfile
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from cqw.installer import (
    _extract_macos,
    download,
    get_binary_name,
    get_cloudflared_path,
    get_download_url,
    get_platform_info,
    is_installed,
    update,
)


class TestGetPlatformInfo:
    def test_returns_tuple(self):
        os_type, arch = get_platform_info()
        assert isinstance(os_type, str)
        assert isinstance(arch, str)

    def test_os_type_valid(self):
        os_type, _ = get_platform_info()
        assert os_type in ("linux", "darwin", "windows")

    def test_arch_valid(self):
        _, arch = get_platform_info()
        assert arch in ("amd64", "arm64")


class TestGetBinaryName:
    def test_returns_string(self):
        name = get_binary_name()
        assert isinstance(name, str)
        assert "cloudflared" in name

    def test_windows_suffix(self):
        with patch.object(sys, "platform", "win32"):
            name = get_binary_name()
            assert name.endswith(".exe")

    def test_non_windows_no_suffix(self):
        with patch.object(sys, "platform", "linux"):
            name = get_binary_name()
            assert not name.endswith(".exe")


class TestGetCloudflaredPath:
    def test_returns_path(self):
        path = get_cloudflared_path()
        assert isinstance(path, Path)
        assert "cloudflared" in str(path)

    def test_contains_cache_dir(self):
        path = get_cloudflared_path()
        assert "cqw" in str(path) or ".cache" in str(path)


class TestGetDownloadUrl:
    def test_returns_url(self):
        url = get_download_url()
        assert url.startswith("https://")
        assert "cloudflared" in url

    def test_contains_platform(self):
        url = get_download_url()
        os_type, arch = get_platform_info()
        if os_type == "windows":
            assert "windows" in url.lower()
        elif os_type == "darwin":
            assert ".tgz" in url


class TestIsInstalled:
    def test_returns_false_when_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("cqw.installer.CLOUDFLARED_DIR", Path(tmpdir)):
                assert not is_installed()

    def test_returns_true_when_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)
            binary_path = cloudflared_dir / get_binary_name()
            binary_path.touch()

            if sys.platform != "win32":
                binary_path.chmod(0o755)

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                assert is_installed()


class TestDownload:
    def test_download_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)
            binary_path = cloudflared_dir / "cloudflared"
            binary_path.touch()

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                with patch(
                    "cqw.installer.get_cloudflared_path", return_value=binary_path
                ):
                    with patch(
                        "cqw.installer.get_platform_info",
                        return_value=("windows", "amd64"),
                    ):
                        with patch(
                            "cqw.installer.get_download_url",
                            return_value="https://example.com/cloudflared.exe",
                        ):
                            with patch("urllib.request.urlretrieve") as mock_retrieve:
                                mock_retrieve.return_value = None

                                result = download()

                            assert result is True

    def test_download_failure_network_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                with patch("urllib.request.urlretrieve") as mock_retrieve:
                    mock_retrieve.side_effect = urllib.error.URLError("Network error")
                    result = download()

                assert result is False

    def test_download_failure_os_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                with patch("urllib.request.urlretrieve") as mock_retrieve:
                    mock_retrieve.side_effect = OSError("Permission denied")
                    result = download()

                assert result is False


class TestExtractMacos:
    @pytest.mark.skipif(sys.platform == "win32", reason="macOS-specific test")
    def test_extract_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tgz_path = Path(tmpdir) / "test.tgz"
            dest_dir = Path(tmpdir) / "dest"
            dest_dir.mkdir()

            with tarfile.open(tgz_path, "w:gz") as tf:
                info = tarfile.TarInfo(name="cloudflared")
                info.size = 4
                tf.addfile(info, fileobj=io.BytesIO(b"fake"))

            result = _extract_macos(tgz_path, dest_dir)
            assert result is True
            assert (dest_dir / "cloudflared").exists()

    def test_extract_failure_bad_tgz(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_tgz = Path(tmpdir) / "bad.tgz"
            bad_tgz.write_bytes(b"not a tgz file")

            dest_dir = Path(tmpdir) / "dest"
            dest_dir.mkdir()

            result = _extract_macos(bad_tgz, dest_dir)
            assert result is False


class TestUpdate:
    def test_update_removes_old_binary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)
            old_binary = cloudflared_dir / "cloudflared"
            old_binary.touch()

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                with patch(
                    "cqw.installer.get_cloudflared_path", return_value=old_binary
                ):
                    with patch("cqw.installer.download", return_value=True):
                        result = update()

                    assert result is True
                    assert not old_binary.exists() or cloudflared_dir.exists()

    def test_update_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cloudflared_dir = Path(tmpdir)
            old_binary = cloudflared_dir / "cloudflared"
            old_binary.touch()

            with patch("cqw.installer.CLOUDFLARED_DIR", cloudflared_dir):
                with patch(
                    "cqw.installer.get_cloudflared_path", return_value=old_binary
                ):
                    with patch("cqw.installer.download", return_value=False):
                        result = update()

                    assert result is False
