"""Create the application archive and checksum used by the launcher."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "kadr-app.zip"


def main() -> None:
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for directory in (ROOT / "backend", ROOT / "frontend" / "dist"):
            if not directory.is_dir():
                raise RuntimeError(f"Missing build output: {directory}")
            for path in sorted(directory.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
                    archive.write(path, path.relative_to(ROOT).as_posix())
        for name in ("requirements-runtime.txt", "README.md"):
            archive.write(ROOT / name, name)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    OUTPUT.with_suffix(".zip.sha256").write_text(f"{digest}  {OUTPUT.name}\n", encoding="ascii")
    print(f"{OUTPUT}: {OUTPUT.stat().st_size:,} bytes; SHA-256 {digest}")


if __name__ == "__main__":
    main()
