import subprocess
import sys


def run_cqw(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "cqw.main"] + args,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode, result.stdout, result.stderr


class TestCLIHelp:
    def test_help_output(self):
        code, stdout, stderr = run_cqw(["--help"])
        assert code == 0
        assert "usage: cqw" in stdout or "usage: cqw" in stderr
        assert "--forward" in stdout or "--forward" in stderr
        assert "--help" in stdout or "--help" in stderr

    def test_help_short_flag(self):
        code, stdout, stderr = run_cqw(["-h"])
        assert code == 0
        assert "usage: cqw" in stdout or "usage: cqw" in stderr


class TestCLIRequiredArgs:
    def test_missing_forward_error(self):
        code, stdout, stderr = run_cqw([])
        assert code != 0
        assert "required: --forward" in stderr or "required: --forward/-f" in stderr

    def test_forward_required_message(self):
        code, stdout, stderr = run_cqw(["--user", "test"])
        assert code != 0
        assert "forward" in stderr.lower()


class TestCLIVersion:
    def test_version_output(self):
        code, stdout, stderr = run_cqw(["--version"])
        assert code == 0
        assert "cqw(v" in stdout

    def test_version_short_flag(self):
        code, stdout, stderr = run_cqw(["-V"])
        assert code == 0
        assert "cqw(v" in stdout


class TestCLIShortFlags:
    def test_forward_short_flag_in_help(self):
        code, stdout, stderr = run_cqw(["--help"])
        assert code == 0
        assert "-f" in stdout or "-f" in stderr

    def test_verbose_short_flag_in_help(self):
        code, stdout, stderr = run_cqw(["--help"])
        assert code == 0
        assert "-v" in stdout or "-v" in stderr
