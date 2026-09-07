"""Configuration must not depend on where a process was started.

`env_file` accepts relative paths, which resolve against the current working
directory — so a relative default works from the repository root and fails
everywhere else: a cron job, an experiment CLI run from a package directory, a
debugger with its own working directory. The failure is a wall of Pydantic
"Field required" errors that looks like missing configuration rather than a
missing file, which is what makes it worth a test.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = """
from core.config import PROJECT_ROOT, get_settings

settings = get_settings()
print(PROJECT_ROOT)
print(settings.app_env)
"""


def test_settings_load_from_an_unrelated_working_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,  # deliberately not the repository root
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    project_root, app_env = result.stdout.split()
    assert Path(project_root) == ROOT
    assert app_env  # came from .env.example, which was found by absolute path
