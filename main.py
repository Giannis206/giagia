#!/usr/bin/env python3
"""Local Greek crossword generator — CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from crossword.difficulty import DifficultyMode, parse_difficulty
from crossword.puzzle_hints import finalize_puzzle_hints, prefilled_letters_from_hints, validate_puzzle_hints
from crossword.render import render_printable_html
from crossword.solver import CrosswordGenerationError, generate_crossword

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


def _save_meta(
    seed: int | None,
    size: int,
    word_count: int,
    result=None,
    *,
    difficulty: str = "normal",
) -> None:
    payload: dict = {"seed": seed, "size": size, "word_count": word_count, "difficulty": difficulty}
    hints = getattr(result, "puzzle_hints", None) if result is not None else None
    if hints is not None:
        payload["hints"] = {
            "primary": hints.primary_helper.helper_word,
            "secondary": (
                hints.secondary_helper.helper_word
                if hints.secondary_helper is not None
                else None
            ),
            "extra_letters": len(hints.extra_hint_cells),
        }
    elif result is not None and result.helper is not None:
        payload["helper"] = {
            "helper_entry_id": result.helper.helper_entry_id,
            "helper_word": result.helper.helper_word,
            "helper_direction": result.helper.helper_direction,
            "helper_cells": [list(cell) for cell in result.helper.helper_cells],
        }
    META_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def do_generate(
    *,
    seed: int | None,
    size: int,
    allow_reuse: bool = False,
    css_href: str | None = None,
    difficulty: DifficultyMode = "normal",
) -> dict[str, int | str]:
    if allow_reuse:
        print("Σημείωση: η επανάχρηση λέξεων απενεργοποιείται — μόνο πραγματικές λέξεις.")
    mode_label = "εύκολο" if difficulty == "easy" else "κανονικό"
    print(f"Δημιουργία σταυρόλεξου ({mode_label} mode)...")
    try:
        result = generate_crossword(
            data_dir=DATA_DIR,
            size=size,
            seed=seed,
        )
    except CrosswordGenerationError as exc:
        if exc.diagnostics:
            print(f"Αποτυχία: {exc.diagnostics}")
        raise
    if difficulty == "easy":
        result = finalize_puzzle_hints(result, difficulty="easy")
    else:
        validate_puzzle_hints(result)
    render_printable_html(
        result.grid,
        result.clue_words or result.words,
        HTML_PATH,
        project_root=ROOT,
        show_letters=False,
        css_href=css_href,
        helper=result.helper,
        puzzle_hints=result.puzzle_hints,
        prefilled_letters=prefilled_letters_from_hints(result),
        difficulty=difficulty,
    )
    clue_count = len(result.clue_words or result.words)
    _save_meta(seed, size, clue_count, result=result, difficulty=difficulty)
    print(f"Έτοιμο: {HTML_PATH}")
    hints = result.puzzle_hints
    if hints is not None:
        d1 = "Οριζόντια" if hints.primary_helper.helper_direction == "across" else "Κάθετα"
        print(
            f"Βοήθεια 1: #{hints.primary_helper.helper_entry_id} "
            f"{hints.primary_helper.helper_word} ({d1})"
        )
        if hints.secondary_helper is not None:
            d2 = (
                "Οριζόντια"
                if hints.secondary_helper.helper_direction == "across"
                else "Κάθετα"
            )
            print(
                f"Βοήθεια 2: #{hints.secondary_helper.helper_entry_id} "
                f"{hints.secondary_helper.helper_word} ({d2})"
            )
        if hints.extra_hint_cells:
            print(f"Επιπλέον γράμματα: {hints.extra_letter_count}")
    elif result.helper is not None:
        direction = "Οριζόντια" if result.helper.helper_direction == "across" else "Κάθετα"
        print(
            f"Βοήθεια: #{result.helper.helper_entry_id} {result.helper.helper_word} ({direction})"
        )
    print(f"Λέξεις: {clue_count} | Μέγεθος πλέγματος: {size}x{size}")
    return {
        "words": clue_count,
        "size": result.grid.size,
        "path": str(HTML_PATH),
        "difficulty": difficulty,
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
        "--difficulty",
        choices=["normal", "easy"],
        default="normal",
        help="Κανονικό ή εύκολο mode (περισσότερη βοήθεια στο πλέγμα)",
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
        do_generate(
            seed=args.seed,
            size=args.size,
            allow_reuse=args.allow_reuse,
            difficulty=parse_difficulty(args.difficulty),
        )
        if args.open:
            do_open_preview()
        return 0

    interactive_menu(args.seed, args.size, args.allow_reuse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
