"""Package the backend for Lambda x86_64/Python 3.12, locally or in Docker."""

from pathlib import Path
import shutil
import subprocess
import sys


def bundle(source: Path, target: Path) -> None:
    requirements = source / "requirements.txt"
    if not requirements.is_file():
        raise SystemExit("Backend packaging requires backend/requirements.txt.")
    for handler in ("app/handlers/api.py", "app/handlers/worker.py"):
        if not (source / handler).is_file():
            raise SystemExit(f"Backend packaging requires {handler}.")
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--no-compile",
            "--only-binary=:all:",
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.12",
            "--abi",
            "cp312",
            "--target",
            str(target),
            "-r",
            str(requirements),
        ],
        check=True,
    )
    shutil.copytree(
        source / "app",
        target / "app",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".env", ".env.*", "tests"
        ),
    )
    for package in ("boto3", "pypdf", "mangum"):
        if not (target / package).is_dir():
            raise SystemExit(
                f"backend/requirements.txt must include {package} for AWS packaging."
            )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: bundle_backend.py BACKEND_ROOT OUTPUT_DIRECTORY")
    bundle(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
