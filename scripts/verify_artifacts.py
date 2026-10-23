"""Check built distributions contain no local runtime, cache or secret-bearing paths."""

import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def main():
    artifacts = list(Path("dist").glob("*.whl")) + list(Path("dist").glob("*.tar.gz"))
    if len(artifacts) != 2:
        raise SystemExit("Expected one wheel and one source distribution")
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                names = archive.namelist()
        else:
            with tarfile.open(artifact) as archive:
                names = archive.getnames()
        for name in names:
            path = PurePosixPath(name)
            if any(
                part in {".venv", ".uv-cache", ".python", ".local", ".git", "__pycache__"}
                for part in path.parts
            ):
                raise SystemExit(f"Forbidden generated content in {artifact.name}")
            if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix in {
                ".sqlite",
                ".db",
                ".pem",
                ".key",
                ".log",
            }:
                raise SystemExit(f"Forbidden sensitive path in {artifact.name}")
        print(f"Artifact path check passed: {artifact.name} ({len(names)} entries)")


if __name__ == "__main__":
    main()
