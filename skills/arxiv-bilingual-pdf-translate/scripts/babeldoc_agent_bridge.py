#!/usr/bin/env python3
"""Bridge BabelDOC translation calls to Codex-agent JSONL translations."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import re
import sys
import threading
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable, Optional


PLACEHOLDER_PATTERNS = [
    re.compile(r"\{v\d+\}"),
    re.compile(r"\{\{[^{}\n]{1,80}\}\}"),
    re.compile(r"<\|[^|\n]{1,80}\|>"),
    re.compile(r"@@[^@\s]{1,80}@@"),
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unit_id_for(text: str) -> str:
    return f"u_{sha256_text(text)[:16]}"


def placeholders(text: str) -> list[str]:
    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        found.extend(pattern.findall(text))
    return list(dict.fromkeys(found))


def translation_input_from_request(text: str) -> str:
    json_marker = "## Here is the input:"
    if json_marker in text:
        payload = text.split(json_marker, 1)[1].strip()
        try:
            items = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        if isinstance(items, list):
            inputs = []
            for item in items:
                if isinstance(item, dict) and "input" in item:
                    inputs.append(str(item["input"]))
            if inputs:
                return "\n".join(inputs)
        return payload

    text_marker = "Now translate the following text:"
    if text_marker in text:
        return text.split(text_marker, 1)[1].strip()

    return text


def json_default(value: Any) -> str:
    return repr(value)


def load_base_translator() -> type:
    try:
        module = import_module("babeldoc.translator.translator")
        return getattr(module, "BaseTranslator")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Cannot import babeldoc.translator.translator.BaseTranslator. "
            "Run this script in a Python environment where the BabelDOC package, "
            "not only this project's babeldoc wrapper directory, is importable."
        ) from exc


def load_translations(path: Path) -> dict[str, str]:
    translations: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{lineno}: invalid JSONL: {exc}") from exc
            source_hash = item.get("source_hash")
            translated_text = item.get("translated_text")
            if not source_hash or not isinstance(translated_text, str):
                raise RuntimeError(f"{path}:{lineno}: missing source_hash or translated_text")
            translations[source_hash] = translated_text
    return translations


def make_translator_class(base_translator: type) -> type:
    class AgentJsonTranslator(base_translator):  # type: ignore[misc, valid-type]
        """BabelDOC translator that records or replays JSONL translations."""

        name = "codex-agent-json"

        def __init__(
            self,
            mode: str,
            units_path: Optional[Path],
            translations_path: Optional[Path],
            lang_in: str,
            lang_out: str,
            strict: bool = True,
        ) -> None:
            try:
                super().__init__(lang_in=lang_in, lang_out=lang_out, ignore_cache=True)
            except TypeError:
                try:
                    super().__init__(lang_in, lang_out, True)
                except TypeError:
                    super().__init__()

            self.mode = mode
            self.units_path = units_path
            self.strict = strict
            self._lock = threading.Lock()
            self._seen: set[str] = set()
            self._translations = load_translations(translations_path) if translations_path else {}
            self._handle = None

            if self.mode == "extract":
                if not self.units_path:
                    raise RuntimeError("extract mode requires --units")
                self.units_path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = self.units_path.open("w", encoding="utf-8")

        def __str__(self) -> str:
            return self.name

        def close(self) -> None:
            if self._handle:
                self._handle.close()
                self._handle = None

        def translate(self, text: Any, *args: Any, **kwargs: Any) -> Any:
            return self._handle_text(text, call_type="translate", extra_args=args, extra_kwargs=kwargs)

        def llm_translate(self, text: Any, *args: Any, **kwargs: Any) -> Any:
            return self._handle_text(text, call_type="llm_translate", extra_args=args, extra_kwargs=kwargs)

        def do_translate(self, text: Any, *args: Any, **kwargs: Any) -> Any:
            return self._handle_text(text, call_type="do_translate", extra_args=args, extra_kwargs=kwargs)

        def do_llm_translate(self, text: Any, *args: Any, **kwargs: Any) -> Any:
            return self._handle_text(text, call_type="do_llm_translate", extra_args=args, extra_kwargs=kwargs)

        def _handle_text(
            self,
            text: str,
            call_type: str,
            extra_args: tuple[Any, ...],
            extra_kwargs: dict[str, Any],
        ) -> Any:
            if text is None:
                return None
            if not isinstance(text, str):
                text = str(text)
            source_hash = sha256_text(text)

            if self.mode == "extract":
                self._record(text, source_hash, call_type, extra_args, extra_kwargs)
                return text

            translated = self._translations.get(source_hash)
            if translated is not None:
                return translated
            if self.strict:
                raise RuntimeError(f"missing translation for source_hash={source_hash} unit_id={unit_id_for(text)}")
            return text

        def _record(
            self,
            text: str,
            source_hash: str,
            call_type: str,
            extra_args: tuple[Any, ...],
            extra_kwargs: dict[str, Any],
        ) -> None:
            if source_hash in self._seen:
                return
            translation_input = translation_input_from_request(text)
            item = {
                "unit_id": unit_id_for(text),
                "source_hash": source_hash,
                "source_text": text,
                "translation_input": translation_input,
                "placeholder_tokens": placeholders(translation_input),
                "context": {
                    "call_type": call_type,
                    "args": json.loads(json.dumps(extra_args, default=json_default)),
                    "kwargs": json.loads(json.dumps(extra_kwargs, default=json_default)),
                },
            }
            line = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            with self._lock:
                if source_hash in self._seen:
                    return
                self._seen.add(source_hash)
                if not self._handle:
                    raise RuntimeError("extract output handle is closed")
                self._handle.write(line + "\n")
                self._handle.flush()

    return AgentJsonTranslator


def import_first(candidates: list[tuple[str, str]]) -> tuple[str, Any]:
    errors: list[str] = []
    for module_name, attr in candidates:
        try:
            module = import_module(module_name)
            value = getattr(module, attr)
            return f"{module_name}.{attr}", value
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{module_name}.{attr}: {exc}")
    raise RuntimeError("No supported BabelDOC high-level runner found:\n" + "\n".join(errors))


def filtered_kwargs(callable_obj: Any, candidate_kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return candidate_kwargs

    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return {key: value for key, value in candidate_kwargs.items() if value is not None}
    filtered: dict[str, Any] = {}
    for key, value in candidate_kwargs.items():
        param = params.get(key)
        if not param:
            continue
        if value is not None or param.default is inspect.Parameter.empty:
            filtered[key] = value
    return filtered


def build_translation_config(args: argparse.Namespace, translator: Any) -> Any:
    try:
        config_cls = import_module("babeldoc.format.pdf.translation_config").TranslationConfig
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Cannot import babeldoc.format.pdf.translation_config.TranslationConfig") from exc

    common = {
        "input_file": str(args.pdf),
        "file_path": str(args.pdf),
        "pdf_path": str(args.pdf),
        "files": [str(args.pdf)],
        "output_dir": str(args.output_dir),
        "output": str(args.output_dir),
        "working_dir": str(args.work_dir),
        "lang_in": args.lang_in,
        "lang_out": args.lang_out,
        "doc_layout_model": None,
        "qps": args.qps,
        "pool_max_workers": args.pool_max_workers,
        "translator": translator,
        "translate_engine": translator,
        "translator_engine": translator,
        "no_dual": False,
        "no_mono": args.no_mono,
        "use_side_by_side_dual": True,
        "use_alternating_pages_dual": False,
        "enhance_compatibility": args.enhance_compatibility,
        "auto_extract_glossary": False,
        "pages": args.pages,
        "skip_clean": args.skip_clean or args.enhance_compatibility,
        "disable_rich_text_translate": args.disable_rich_text_translate or args.enhance_compatibility,
    }

    kwargs = filtered_kwargs(config_cls, common)
    if not any(key in kwargs for key in ("input_file", "file_path", "pdf_path", "files")):
        raise RuntimeError("Unsupported TranslationConfig signature: no recognized PDF input parameter")
    if not any(key in kwargs for key in ("translator", "translate_engine", "translator_engine")):
        raise RuntimeError("Unsupported TranslationConfig signature: no recognized translator parameter")

    try:
        return config_cls(**kwargs)
    except TypeError as exc:
        raise RuntimeError(
            "Failed to construct BabelDOC TranslationConfig with the installed version. "
            f"Accepted kwargs were: {sorted(kwargs)}"
        ) from exc


async def consume_async_iter(value: Any) -> Any:
    last = None
    async for item in value:
        last = item
        if item is not None:
            print(json.dumps({"event": "babeldoc", "value": repr(item)}, ensure_ascii=False))
    return last


def consume_result(value: Any) -> Any:
    if inspect.isasyncgen(value):
        return asyncio.run(consume_async_iter(value))
    if inspect.iscoroutine(value):
        return asyncio.run(value)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict, list, tuple)):
        last = None
        for item in value:
            last = item
            if item is not None:
                print(json.dumps({"event": "babeldoc", "value": repr(item)}, ensure_ascii=False))
        return last
    return value


def run_babeldoc(args: argparse.Namespace) -> Any:
    base_translator = load_base_translator()
    translator_cls = make_translator_class(base_translator)
    translator = translator_cls(
        mode=args.mode,
        units_path=args.units,
        translations_path=args.translations,
        lang_in=args.lang_in,
        lang_out=args.lang_out,
        strict=not args.allow_missing,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    try:
        config = build_translation_config(args, translator)
        runner_name, runner = import_first(
            [
                ("babeldoc.format.pdf.high_level", "do_translate_async_stream"),
                ("babeldoc.format.pdf.high_level", "translate"),
                ("pdf2zh.high_level", "do_translate_async_stream"),
                ("pdf2zh.high_level", "translate"),
            ]
        )
        print(json.dumps({"event": "runner", "name": runner_name}, ensure_ascii=False))
        return consume_result(runner(config))
    finally:
        translator.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--pdf", type=Path, required=True)
        subparser.add_argument("--work-dir", type=Path, required=True)
        subparser.add_argument("--output-dir", type=Path, required=True)
        subparser.add_argument("--lang-in", default="en")
        subparser.add_argument("--lang-out", default="zh-CN")
        subparser.add_argument("--qps", type=int, default=4)
        subparser.add_argument("--pool-max-workers", type=int)
        subparser.add_argument("--pages")
        subparser.add_argument("--no-mono", action="store_true")
        subparser.add_argument("--skip-clean", action="store_true")
        subparser.add_argument("--disable-rich-text-translate", action="store_true")
        subparser.add_argument("--enhance-compatibility", action="store_true")
        subparser.add_argument("--allow-missing", action="store_true")

    extract = subparsers.add_parser("extract", help="record BabelDOC translation requests")
    add_common(extract)
    extract.add_argument("--units", type=Path, required=True)
    extract.set_defaults(translations=None)

    render = subparsers.add_parser("render", help="render with completed JSONL translations")
    add_common(render)
    render.add_argument("--translations", type=Path, required=True)
    render.set_defaults(units=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 2
    if args.mode == "render" and not args.translations.exists():
        print(f"translations file not found: {args.translations}", file=sys.stderr)
        return 2

    try:
        run_babeldoc(args)
    except Exception as exc:  # noqa: BLE001
        print(f"babeldoc_agent_bridge failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "mode": args.mode}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
