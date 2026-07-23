# NoteGuide Editor Shell

This is the editor-first shell for NoteGuide.

## What is included

- One note workspace
- One math step per row
- Enter-to-submit behavior
- Inline annotations
- A mock verifier so you can design the UI before wiring the backend

## How to run

Open `index.html` directly in a browser, or serve this folder with a simple local server:

```bash
cd /Users/dannyhu/Desktop/NoteGuide/NoteGuide/editor-shell
python3 -m http.server 8000
```

Then open `http://127.0.0.1:8000/` in your browser.

## Goal

Prove the editor interaction model before connecting SymPy and FastAPI.
