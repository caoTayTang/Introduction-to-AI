"""Package the two-game LMS submission without caches or legacy assignments."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "output" / "submission"
SKIP = {"__pycache__", ".DS_Store", "played", "artifacts", ".ruff_cache"}


def source_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name in ("main.py", "pyproject.toml", "uv.lock", ".python-version", "SUBMISSION.md"):
        files[name] = ROOT / name
    for folder in ("pipes_problem", "light_up_problem", "scripts"):
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if path.is_file() and not SKIP.intersection(relative.parts) and path.suffix != ".pyc":
                files[relative.as_posix()] = path
    for name in (
        "report/main-vi.tex", "report/preamble.tex", "report/metadata.tex",
        "report/pipes-vi.tex", "report/lightup-vi.tex", "report/lightup-per-input.tex", "report/README.md",
        "report/assets/hcmut-logo.png", "report/assets/lightup-board.tex",
        "slides/submission.tex", "slides/beamerthemeHCMUT.sty", "slides/SUBMISSION.md",
        "slides/lightup-board.tex", "slides/results-table.tex",
        "docs/pipes-analysis.md", "docs/lightup-analysis.md", "docs/pipes-plan.md",
        "docs/submission-validation.md",
    ):
        files[name] = ROOT / name
    for pattern in ("2026-10-25-pipes*", "2026-10-25-lightup*", "2026-10-31-lightup-dfs-csp*"):
        for path in (ROOT / "docs" / "benchmarks").glob(pattern):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path
    files["README.md"] = ROOT / "SUBMISSION.md"
    return files


def main() -> None:
    report = ROOT / "output/final/main-vi.pdf"
    slides = ROOT / "output/final/submission.pdf"
    for pdf in (report, slides):
        if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
            raise SystemExit(f"Compile the final PDF first: {pdf}")
    files = {f"source_code/{name}": path for name, path in source_files().items()}
    files.update({"report.pdf": report, "slides.pdf": slides, "README.md": ROOT / "SUBMISSION.md"})
    if any(not path.is_file() for path in files.values()):
        raise SystemExit("Submission dependency missing")
    assert sorted(name for name in files if name.endswith(".pdf")) == ["report.pdf", "slides.pdf"]
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "Introduction-to-AI-submission.zip"
    checksums = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, path in sorted(files.items()):
            data = path.read_bytes()
            bundle.writestr(name, data)
            checksums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
        bundle.writestr("SHA256SUMS.txt", "\n".join(checksums) + "\n")
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    shutil.copy2(report, DEST / "report.pdf")
    shutil.copy2(slides, DEST / "slides.pdf")
    print(f"Created {archive} ({archive.stat().st_size:,} bytes; {len(files)} files + checksums)")


if __name__ == "__main__":
    main()
