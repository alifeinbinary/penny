#!/usr/bin/env bash
# Starts Penny, tails logs, and auto-restarts when main has new commits.
#
# Usage:
#   ./scripts/deploy-watch.sh              # Check for updates every 5 minutes
#   ./scripts/deploy-watch.sh 60           # Check every 60 seconds

set -euo pipefail

INTERVAL="${1:-300}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

log() { echo "[deploy $(date +%H:%M:%S)] $*"; }

# Cleanup on exit
cleanup() {
    log "shutting down..."
    kill "$WATCH_PID" 2>/dev/null || true
    docker compose down
    log "stopped"
    exit
}
trap cleanup INT TERM

# Start penny
log "starting penny in $DIR"
docker compose up -d --build
log "penny started (checking for updates every ${INTERVAL}s)"

# Background: poll git for changes and restart on new commits
(
    while true; do
        sleep "$INTERVAL"
        git fetch origin main --quiet 2>/dev/null || continue

        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse origin/main)

        if [ "$LOCAL" != "$REMOTE" ]; then
            log "new commits detected ($(git log --oneline HEAD..origin/main | head -3))"
            git pull origin main --ff-only
            log "rebuilding and restarting..."
            docker compose down
            docker compose up -d --build
            log "restarted"
        fi
    done
) &
WATCH_PID=$!

# Foreground: tail logs (restarts if containers are recreated)
while true; do
    docker compose logs -f --tail 50 2>/dev/null || true
    sleep 2
done
