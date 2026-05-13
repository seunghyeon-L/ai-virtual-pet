**IMPORTANT: All rules in this file are absolute. Never ignore or violate them under any circumstances.**

# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
---
---

# AI Virtual Pet - Project Notes

## Project Summary

This is a Windows desktop virtual pet prototype built with PyQt5 and pywin32. The app asks the user for today's goals, shows a chibi lion mascot on screen, checks the active window title every 5 seconds, and reacts with praise or warning messages depending on whether the active window appears related to the goals.

The current implementation is a local demo/prototype. It does not call any LLM or external AI service.

## Main Files

- `pet.py`: Main application entry point. Contains the goal dialog, floating lion widget, speech typing effect, active-window watch timer, 5-minute escalation, completion flow, celebration overlay, and final dialog.
- `watcher.py`: Windows foreground-window integration via `pywin32`. Reads the active window title and can send `WM_CLOSE` to close the active window. It avoids acting on the app's own process.
- `judge.py`: Simple rule-based on-task check. Splits each goal by whitespace and returns true if any goal word is a case-insensitive substring of the active window title.
- `messages.py`: Message pools for praise, angry, sad, and celebration moods.
- `requirements.txt`: Runtime dependencies: `PyQt5`, `pywin32`.

## Assets

- Lion PNGs live in `images/`.
- Current image files: `lion_default.png`, `lion_praise.png`, `lion_angry.png`, `lion_sad.png`, `lion_hidden.png`.
- `pet.py` currently looks for `lion_celebrate.png` for the celebration mood, but that file is not present. The code falls back to `lion_default.png`.
- The custom font is `fonts/Hakgyoansim Nadeuri TTF B.ttf`.
- `images.zip` is an empty 22-byte zip and should not be treated as a useful asset bundle.

## How To Run

Use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\python.exe .\pet.py
```

To check syntax without launching the GUI:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\pet.py .\watcher.py .\judge.py .\messages.py
```

## Current Behavior

1. App starts and loads the custom font.
2. A frameless notebook-style goal dialog appears.
3. User adds one or more goals and clicks start.
4. A frameless always-on-top lion widget appears near the bottom-right.
5. Every 5 seconds, the app reads the active window title.
6. If the title matches any goal word, it resets the off-task counter and shows a random praise message.
7. If not, it increments the off-task counter and shows a random angry or sad message.
8. After 300 seconds of continuous off-task time, it warns the user and attempts to close the active window after 2 seconds.
9. Clicking the lion without dragging marks the goals complete, hides the pet, shows a full-screen star celebration overlay, then shows a completion dialog.

## Important Implementation Notes

- Keep changes small and direct. This project is a prototype, not a framework.
- Do not introduce abstractions or new files unless there is a clear need.
- Prefer editing the existing simple files over adding a new architecture.
- The active-window matching is intentionally simple substring matching.
- The app is Windows-specific because `watcher.py` depends on `pywin32`.
- The UI intentionally avoids separate top-level speech-bubble windows because previous attempts had Windows/PyQt5 rendering issues. See `TROUBLESHOOTING.md`.
- Be careful with frameless transparent PyQt windows. The current working pattern is to keep visual changes inside the existing visible widgets where possible.
- Do not remove or rewrite `PLAN.md`, `BRIEF.md`, `CLAUDE.md`, or `TROUBLESHOOTING.md` unless the user explicitly asks.

## Known Cleanup Candidates

- Add or generate `images/lion_celebrate.png`, or update `LION_IMAGES` in `pet.py` to use an existing celebration asset.
- `lion_celebrade.md` appears to be a prompt for generating the celebration image. The filename likely has a typo: `celebrade` should probably be `celebrate`.
- `MOOD_STYLES`, `BUTTON_STYLE`, and `DIALOG_STYLE` in `pet.py` appear unused. Mention before removing; do not delete as incidental cleanup.

## User Preference

The user prefers Korean explanations. Keep responses concise and practical.
