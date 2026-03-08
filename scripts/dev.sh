#!/usr/bin/env bash
# Unified dev startup: Flask API + Vite dashboard
set -e

# Kill anything on port 7070
lsof -ti:7070 | xargs kill -9 2>/dev/null || true

cleanup() {
  echo ""
  echo "Shutting down..."
  kill 0 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# Start Flask dev server
echo "Starting Flask on :7070..."
(cd server && python -m open_uplift.cli serve --port 7070) &

# Start Vite dev server
echo "Starting Vite..."
(cd dashboard && npx vite --port 5173) &

wait
