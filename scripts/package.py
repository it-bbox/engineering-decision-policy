#!/usr/bin/env python3
"""Package only public project files; exclude .git, work, caches and dist itself."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = [ROOT / name for name in ("index.html", "README.md", "SKILL.md", "AGENTS.md", "CLAUDE.md", ".nojekyll", ".gitignore")]
    for directory in ("agents", "assets", "configs", "docs", "scripts", "tests", "demo"):
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    paths = sorted(paths)
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n" for p in paths)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / "engineering-decision-policy-v2.zip"
    prefix = "engineering-decision-policy-v2/"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in paths:
            bundle.write(path, prefix + path.relative_to(ROOT).as_posix())
        bundle.writestr(prefix + "SHA256SUMS.txt", manifest)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
    (dist / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
    print(f"Packaged {len(paths)} files + manifest: {archive.name} ({archive.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
