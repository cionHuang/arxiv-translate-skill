#!/usr/bin/env python3
"""Split BabelDOC translation units into subagent-sized JSONL batches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSONL: {exc}") from exc


def write_batch(output_dir: Path, index: int, units: list[dict]) -> dict:
    path = output_dir / f"batch_{index:04d}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(json.dumps(unit, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {
        "batch": path.name,
        "path": str(path),
        "units": len(units),
        "chars": sum(len(unit.get("source_text", "")) for unit in units),
    }


def build_batches(units_path: Path, output_dir: Path, max_units: int, max_chars: int) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    batch: list[dict] = []
    batch_chars = 0
    manifest: list[dict] = []

    for unit in read_jsonl(units_path):
        text_len = len(unit.get("source_text", ""))
        would_exceed_units = len(batch) >= max_units
        would_exceed_chars = batch and batch_chars + text_len > max_chars
        if would_exceed_units or would_exceed_chars:
            manifest.append(write_batch(output_dir, len(manifest) + 1, batch))
            batch = []
            batch_chars = 0
        batch.append(unit)
        batch_chars += text_len

    if batch:
        manifest.append(write_batch(output_dir, len(manifest) + 1, batch))

    manifest_path = output_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", type=Path, help="translation_units.jsonl from babeldoc_agent_bridge.py extract")
    parser.add_argument("--output-dir", type=Path, default=Path("batches"))
    parser.add_argument("--max-units", type=int, default=50)
    parser.add_argument("--max-chars", type=int, default=12000)
    args = parser.parse_args()

    manifest = build_batches(args.units, args.output_dir, args.max_units, args.max_chars)
    print(json.dumps({"batches": len(manifest), "units": sum(item["units"] for item in manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
