# NoteGuide Backend

Step verification for the NoteGuide editor. SymPy decides whether a step is
right; an LLM is only ever asked to explain a step SymPy has already proved
wrong.

## Run it

```bash
cd backend
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

On macOS/Linux the interpreter is `.venv/bin/python` instead.

```bash
.venv/Scripts/python.exe -m pytest
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness check |
| `POST /verify` | One-shot verification — easy to curl and to test |
| `WS /ws/verify` | The flowchart's path; the editor holds this open per note |

Both take the same payload and return the same verdict shape the editor shell
already renders:

```jsonc
// request
{"step_id": "step-3", "text": "2x + 5 = 14", "context": ["x + 3 = 7", "2x + 6 = 14"]}

// response
{
  "step_id": "step-3",
  "status": "incorrect",              // correct | incorrect | uncertain
  "confidence": 1.0,
  "short": "Does not follow from the previous step",
  "details": "SymPy proved this line is not equivalent to the previous one: ... For example, x = 4 solves the previous line but not this one.",
  "fix": "Recheck the operation you applied ...",
  "source": "sympy"
}
```

`context` is the earlier lines of the note, oldest first. The last non-blank
entry is the reference the current step must follow from; blank entries are
skipped. An empty `context` means this is the first line.

## What "correct" means

A step is correct when it is **equivalent to the previous step**, not when it
looks similar to it. For equations that means the two lines are satisfied by
exactly the same values, checked in three escalating ways:

1. `(lhs - rhs)` is identical after simplification — the same equation rearranged.
2. The two differences are related by a **nonzero constant** factor — both sides
   were scaled. A symbolic factor is deliberately rejected, since it could be
   zero for some value and would change the solution set.
3. Single-unknown lines are settled by comparing solution sets outright.

So `x + 3 = 7` → `2x + 6 = 14` passes, and `x^2 = 4` → `x = 2` fails, because
`x = -2` satisfies the first line and not the second.

## Counterexamples

When a step is wrong, the backend tries to produce a **witness**: a concrete
value that satisfies the previous line but not the current one. This is what
makes the feedback actionable, and it is the reason the LLM is optional rather
than load-bearing — the interesting content is already proved.

## Confidence

SymPy is a decision procedure, not a classifier, so confidence is not a
gradient: proved verdicts are `1.0` and anything unsettled is reported as
`uncertain` at `0.3` rather than guessed at. `uncertain` specifically means
*SymPy could not decide* — an unreadable line, a comparison it timed out on,
or an equation compared against a bare expression. It never means "probably
wrong".

## Input handling

Students can write `2x` for `2*x` and `x^2` for `x**2` — implicit
multiplication and caret-as-power are both enabled.

SymPy's parser calls `eval` under the hood, so untrusted input passes a
character whitelist first (`app/parsing.py`). Underscores are rejected outright,
which is what blocks dunder-attribute attacks like `(1).__class__.__bases__`;
the tokenizer's `auto_symbol` pass turns other unknown names into symbols.
`tests/test_parsing.py` covers the injection attempts.

Each SymPy call is bounded by a 3-second timeout on a worker thread, so a
pathological input returns `uncertain` instead of hanging the request. The
thread itself is not killed — Python offers no way to do that — so a stream of
pathological inputs could still saturate the small pool.

## LLM explanations (optional)

With `ANTHROPIC_API_KEY` set, an incorrect step's `details` field is reworded by
Claude, and `source` becomes `sympy + claude-opus-5`. Without a key, the
deterministic explanation (counterexample included) is used verbatim. The LLM
is never consulted on the `correct` or `uncertain` branches, and its output is
never allowed to change the verdict — if the call fails or is refused, the
deterministic wording stands.

## Not supported yet

- Inequalities (`<`, `>`, `<=`) — rejected by the character whitelist.
- Chained equalities (`a = b = c`).
- Systems of equations as a unit; each line is checked against the one above it.
- Multi-variable steps fall back to numeric sampling for a counterexample, so a
  wrong step with several unknowns may come back `uncertain` rather than
  `incorrect`.

## Connecting the editor

`editor-shell/app.js` still calls its local `mockVerifier()`. To switch it over,
replace that call with a `fetch` to `POST /verify` (or a WebSocket to
`/ws/verify`) passing `step.id`, the step text, and `getContextForStep(index)` —
the response already matches what `updateBadge` and `updateAnnotation` expect.
Note that `app.js` interpolates `short`/`details` via `innerHTML`, so switch
those to `textContent` before wiring in server-supplied text.
