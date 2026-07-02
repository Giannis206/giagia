"""Local Flask UI for the Greek crossword generator."""

from __future__ import annotations

import random
import sys
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from main import ALLOWED_SIZES, do_generate

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
STATIC_DIR = ROOT / "static"
HTML_PATH = OUTPUT_DIR / "crossword.html"

app = Flask(__name__, template_folder=str(ROOT / "templates"))


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (AttributeError, ValueError, OSError):
                pass


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    try:
        size = int(payload.get("size", 7))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Μη έγκυρο μέγεθος πλέγματος"), 400

    if size not in ALLOWED_SIZES:
        return jsonify(ok=False, error=f"Μη υποστηριζόμενο μέγεθος: {size}"), 400

    mode = payload.get("mode", "new")
    seed = None if mode == "regenerate" else random.randrange(1_000_000_000)

    try:
        result = do_generate(
            seed=seed,
            size=size,
            allow_reuse=False,
            css_href="/static/print.css",
        )
        return jsonify(ok=True, words=result["words"], size=result["size"])
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


@app.get("/preview")
def preview():
    if not HTML_PATH.exists():
        return Response(
            (
                "<!DOCTYPE html><html lang='el'><meta charset='utf-8'>"
                "<body style='font:20px sans-serif;padding:2rem'>"
                "<p>Δεν υπάρχει σταυρόλεξο. Δημιούργησε πρώτα ένα από την αρχική σελίδα.</p>"
                "</body></html>"
            ),
            mimetype="text/html; charset=utf-8",
        )
    return Response(
        HTML_PATH.read_text(encoding="utf-8"),
        mimetype="text/html; charset=utf-8",
    )


@app.get("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@app.get("/shutdown")
def shutdown():
    def _stop() -> None:
        import os

        os._exit(0)

    threading.Timer(0.4, _stop).start()
    return jsonify(status="ok", message="Ο server κλείνει")


def main() -> None:
    _configure_stdio()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Σταυρόλεξο UI: http://127.0.0.1:5000/")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
