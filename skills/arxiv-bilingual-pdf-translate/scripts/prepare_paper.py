#!/usr/bin/env python3
"""Prepare an arXiv paper or local PDF for the bilingual translation workflow."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


ARXIV_ID_RE = re.compile(
    r"(?P<id>(?:\d{4}\.\d{4,5})(?:v\d+)?|[a-zA-Z.-]+/\d{7}(?:v\d+)?)"
)


def parse_arxiv_id(value: str) -> Optional[str]:
    text = value.strip()
    if re.match(r"^https?://", text):
        for marker in ("/abs/", "/pdf/", "/e-print/"):
            if marker in text:
                tail = text.split(marker, 1)[1]
                tail = tail.removesuffix(".pdf")
                match = ARXIV_ID_RE.search(tail)
                return match.group("id") if match else None
    match = ARXIV_ID_RE.fullmatch(text)
    return match.group("id") if match else None


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "paper"


def download(url: str, dest: Path, timeout: int = 90) -> bool:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "codex-arxiv-bilingual-pdf-translate/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            dest.write_bytes(response.read())
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def extract_source(source_archive: Path, source_dir: Path) -> str:
    source_dir.mkdir(parents=True, exist_ok=True)

    if tarfile.is_tarfile(source_archive):
        with tarfile.open(source_archive) as tar:
            safe_members = []
            for member in tar.getmembers():
                member_path = source_dir / member.name
                if member_path.resolve().is_relative_to(source_dir.resolve()):
                    safe_members.append(member)
            tar.extractall(source_dir, members=safe_members)
        return "tar"

    try:
        data = gzip.decompress(source_archive.read_bytes())
    except OSError:
        data = source_archive.read_bytes()

    tex_path = source_dir / "main.tex"
    tex_path.write_bytes(data)
    return "single_tex"


def prepare(input_value: str, output_root: Path, force: bool) -> Path:
    input_path = Path(input_value).expanduser()
    arxiv_id = None if input_path.exists() else parse_arxiv_id(input_value)

    if input_path.exists():
        run_name = safe_name(input_path.stem)
        run_dir = output_root / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = run_dir / "source.pdf"
        if force or not pdf_path.exists():
            shutil.copy2(input_path, pdf_path)
        manifest = {
            "kind": "local_pdf",
            "input": str(input_path.resolve()),
            "run_dir": str(run_dir.resolve()),
            "pdf": str(pdf_path.resolve()),
            "source_tex_dir": None,
        }
    elif arxiv_id:
        run_name = safe_name(arxiv_id)
        run_dir = output_root / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = run_dir / "source.pdf"
        source_archive = run_dir / "source.e-print"
        source_dir = run_dir / "source_tex"

        if force or not pdf_path.exists():
            ok = download(f"https://arxiv.org/pdf/{arxiv_id}.pdf", pdf_path)
            if not ok:
                raise SystemExit(f"failed to download arXiv PDF: {arxiv_id}")

        source_status = "not_downloaded"
        if force or not source_dir.exists():
            ok = download(f"https://arxiv.org/e-print/{arxiv_id}", source_archive)
            if ok:
                try:
                    source_status = extract_source(source_archive, source_dir)
                except Exception as exc:  # noqa: BLE001
                    source_status = f"extract_failed: {exc}"

        manifest = {
            "kind": "arxiv",
            "input": input_value,
            "arxiv_id": arxiv_id,
            "run_dir": str(run_dir.resolve()),
            "pdf": str(pdf_path.resolve()),
            "source_archive": str(source_archive.resolve()) if source_archive.exists() else None,
            "source_tex_dir": str(source_dir.resolve()) if source_dir.exists() else None,
            "source_status": source_status,
        }
    else:
        raise SystemExit(f"input is neither an existing PDF nor a parsable arXiv id/url: {input_value}")

    for dirname in ("babeldoc_work", "batches", "batch_results", "output"):
        (run_dir / dirname).mkdir(exist_ok=True)

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(run_dir.resolve()))
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="arXiv id/url or local PDF path")
    parser.add_argument("--output-root", default=".chinarxiv_work", help="hidden directory for run artifacts")
    parser.add_argument("--force", action="store_true", help="overwrite downloaded/copied source files")
    args = parser.parse_args()

    prepare(args.input, Path(args.output_root), args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
