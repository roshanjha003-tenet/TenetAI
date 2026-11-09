#!/usr/bin/env bash
# Start the API in dev mode (used by .claude/launch.json and by hand).
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/../backend" && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
