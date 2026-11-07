#!/usr/bin/env python3
"""
Best-effort repository-wide C/C++ -> Swift migration helper.

Requires a local Ollama server. This writes translated files under SwiftPort/
and never modifies the original source files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx",
    ".h", ".hh", ".hpp", ".hxx",
    ".inc", ".inl", ".ipp", ".tpp",
}
DEFAULT_IGNORED_DIRS = {
    ".git", ".github", ".build", "build", "dist",
    "node_modules", ".idea", ".vscode", "SwiftPort",
    "__pycache__",
}

SYSTEM_PROMPT = """You are a careful C and C++ to Swift migration engineer.
Translate only the supplied source fragment into Swift.
Preserve behavior, algorithms, names where practical, comments, and all logic.
Use idiomatic Swift types and syntax. Do not invent unavailable APIs.
For C/C++ APIs with no direct Swift equivalent, preserve the intent using
clearly marked TODO comments and explain the required interoperability.
The input may be a fragment from a larger file: do not add a new type,
namespace, import list, or wrapper unless the fragment requires it.
Return code only, without Markdown fences or explanations.
Never replace implementation with pseudocode or omit code to save tokens.
"""

def chunks_by_lines(source: str, max_chars: int) -> list[str]:
    """Split long source into line-aligned chunks."""
    lines = source.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if current and size + len(line) > max_chars:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks

def strip_fences(text: str) -> str:
    text = re.sub(r"^\s*```(?:swift)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()

def ask_ollama(
    session: requests.Session,
    endpoint: str,
    model: str,
    fragment: str,
    relative_path: str,
    part: int,
    total: int,
    num_ctx: int,
    timeout: int,
    retries: int,
) -> str:
    user_prompt = (
        f"Original repository path: {relative_path}\n"
        f"Fragment {part} of {total}.\n"
        "Translate every line in this fragment. Preserve fragment boundaries; "
        "do not claim this fragment is a complete file.\n\n"
        "SOURCE CODE:\n"
        + fragment
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"temperature": 0.1, "num_ctx": num_ctx},
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = session.post(endpoint, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json()["message"]["content"]
            if not result or not result.strip():
                raise RuntimeError("Model returned an empty translation")
            return strip_fences(result) + "\n"
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                wait = min(2 ** attempt, 30)
                print(f"  Request failed ({exc}); retrying in {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"Ollama request failed: {last_error}")

def discover_files(root: Path, output: Path, extra_ignored: set[str]) -> list[Path]:
    ignored = DEFAULT_IGNORED_DIRS | extra_ignored
    found: list[Path] = []
    for current, dirs, filenames in os.walk(root):
        dirs[:] = [
            name for name in dirs
            if name not in ignored and not name.startswith(".")
        ]
        for filename in filenames:
            path = Path(current) / filename
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                try:
                    path.relative_to(output)
                    continue
                except ValueError:
                    pass
                found.append(path)
    return sorted(found)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate C/C++ source and header files into SwiftPort/."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", default="SwiftPort")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:32b"))
    parser.add_argument("--endpoint", default=os.getenv(
        "OLLAMA_URL", "http://localhost:11434/api/chat"
    ))
    parser.add_argument("--chunk-chars", type=int, default=12000)
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-hidden", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    output = (root / args.output).resolve()
    if not root.is_dir():
        parser.error(f"Repository root does not exist: {root}")
    if args.chunk_chars < 1000:
        parser.error("--chunk-chars must be at least 1000")

    output.mkdir(parents=True, exist_ok=True)
    extra_ignored = set() if args.include_hidden else set()
    files = discover_files(root, output, extra_ignored)

    print(f"Found {len(files)} C/C++ source/header files.")
    print(f"Model: {args.model}")
    print(f"Output: {output}")
    print("Original files will not be changed.")

    session = requests.Session()
    successful: list[dict] = []
    failed: list[dict] = []
    skipped: list[str] = []

    for index, source_path in enumerate(files, 1):
        relative = source_path.relative_to(root)
        destination = (output / relative).with_suffix(".swift")
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and not args.overwrite:
            print(f"[{index}/{len(files)}] SKIP existing: {relative}")
            skipped.append(str(relative))
            continue

        print(f"[{index}/{len(files)}] {relative}")
        try:
            source = source_path.read_text(encoding="utf-8", errors="replace")
            chunks = chunks_by_lines(source, args.chunk_chars)
            translated_parts: list[str] = []

            for part_number, chunk in enumerate(chunks, 1):
                print(f"  Translating part {part_number}/{len(chunks)}...")
                translated_parts.append(
                    ask_ollama(
                        session=session,
                        endpoint=args.endpoint,
                        model=args.model,
                        fragment=chunk,
                        relative_path=str(relative),
                        part=part_number,
                        total=len(chunks),
                        num_ctx=args.num_ctx,
                        timeout=args.timeout,
                        retries=args.retries,
                    )
                )

            destination.write_text(
                "\n".join(translated_parts),
                encoding="utf-8"
            )
            successful.append({
                "source": str(relative),
                "output": str(destination.relative_to(root)),
                "parts": len(chunks),
                "chunked": len(chunks) > 1,
            })
            print(f"  Wrote {destination.relative_to(root)}")
        except Exception as exc:
            failed.append({"source": str(relative), "error": str(exc)})
            print(f"  FAILED: {exc}", file=sys.stderr)

    report = {
        "source_file_count": len(files),
        "translated_count": len(successful),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "translated": successful,
        "failed": failed,
        "skipped": skipped,
        "warning": (
            "AI-generated Swift is not guaranteed to compile. Chunked files "
            "may need manual integration. Validate all imports, APIs, symbols, "
            "memory ownership, build settings, and runtime behavior."
        ),
    }
    report_path = output / "conversion_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nConversion run complete.")
    print(f"Translated: {len(successful)}")
    print(f"Failed:     {len(failed)}")
    print(f"Skipped:    {len(skipped)}")
    print(f"Report:     {report_path}")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
