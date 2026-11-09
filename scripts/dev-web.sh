#!/usr/bin/env bash
# Start the web app in dev mode (used by .claude/launch.json and by hand).
export PATH="$HOME/.local/node/bin:$PATH"
cd "$(dirname "$0")/../web" && exec npx next dev -p 3000
