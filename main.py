#!/usr/bin/env python3
"""Local Greek crossword generator — CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from crossword.render import render_printable_html
from crossword.solver import generate_crossword_with_fallback

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
HTML_PATH = OUTPUT_DIR / "crossword.html"
META_PATH = OUTPUT_DIR / "crossword_meta.json"

ALLOWED_SIZES = (7, 8, 10, 12, 15)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (AttributeError, ValueError, OSError):
                pass


def _save_meta(seed: int | None, size: int, word_count: int) -> None:
    META_PATH.write_text(
        json.dumps(
            {"seed": seed, "size": size, "word_count": word_count},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def do_generate(
    *,
    seed: int | None,
    size: int,
    allow_reuse: bool = False,
    css_href: str | None = None,
) -> dict[str, int | str]:
    print("Δημιουργία σταυρόλεξου...")
    result = generate_crossword_with_fallback(
        data_dir=DATA_DIR,
        size=size,
        seed=seed,
        allow_reuse=allow_reuse,
    )
    render_printable_html(
        result.grid,
        result.words,
        HTML_PATH,
        project_root=ROOT,
        show_letters=False,
        css_href=css_href,
    )
    _save_meta(seed, size, len(result.words))
    print(f"Έτοιμο: {HTML_PATH}")
    print(f"Λέξεις: {len(result.words)} | Μέγεθος πλέγματος: {size}x{size}")
    return {
        "words": len(result.words),
        "size": result.grid.size,
        "path": str(HTML_PATH),
    }


def do_open_preview() -> None:
    if not HTML_PATH.exists():
        print("Δεν υπάρχει preview. Δημιούργησε πρώτα σταυρόλεξο (επιλογή 1).")
        return
    uri = HTML_PATH.resolve().as_uri()
    print(f"Άνοιγμα: {uri}")
    webbrowser.open(uri)


def interactive_menu(default_seed: int | None, size: int, allow_reuse: bool) -> None:
    last_seed = default_seed

    while True:
        print()
        print("=== Σταυρόλεξο — Τοπικός Γεννήτορας ===")
        print("1. Generate new crossword")
        print("2. Open printable preview")
        print("3. Regenerate")
        print("4. Exit")
        choice = input("Επιλογή: ").strip()

        if choice == "1":
            do_generate(seed=last_seed, size=size, allow_reuse=allow_reuse)
        elif choice == "2":
            do_open_preview()
        elif choice == "3":
            last_seed = None
            do_generate(seed=None, size=size, allow_reuse=allow_reuse)
        elif choice in ("4", "q", "quit", "exit"):
            print("Αντίο.")
            break
        else:
            print("Μη έγκυρη επιλογή.")


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Τοπικός γεννήτορας ελληνικού σταυρόλεξου")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Deterministic seed για επαναλήψιμη δημιουργία",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=7,
        choices=[7, 8, 10, 12, 15],
        help="Μέγεθος πλέγματος (προεπιλογή: 7 για μεγαλύτερα κελιά στην εκτύπωση)",
    )
    parser.add_argument(
        "--allow-reuse",
        action="store_true",
        help="Επανάχρηση ίδιας λέξης σε πολλά slots",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Δημιουργία χωρίς διαδραστικό μενού",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Άνοιγμα preview στον browser μετά τη δημιουργία",
    )
    args = parser.parse_args(argv)

    if args.generate:
        do_generate(seed=args.seed, size=args.size, allow_reuse=args.allow_reuse)
        if args.open:
            do_open_preview()
        return 0

    interactive_menu(args.seed, args.size, args.allow_reuse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
