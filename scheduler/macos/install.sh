#!/bin/bash
# Install the job-scheduler as a macOS Launch Agent
# This makes the scheduler start automatically on login and stay running

set -e

PLIST_NAME="com.earningstranscripts.job-scheduler.plist"
PLIST_SRC="$(dirname "$0")/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="/Users/arunath/src/learn/data/logs"

echo "=== Job Scheduler macOS Installation ==="
echo

# Create logs directory
mkdir -p "$LOG_DIR"
echo "✓ Created log directory: $LOG_DIR"

# Stop existing service if running
if launchctl list | grep -q "com.earningstranscripts.job-scheduler"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
cp "$PLIST_SRC" "$PLIST_DEST"
echo "✓ Installed plist to: $PLIST_DEST"

# Load the service
launchctl load "$PLIST_DEST"
echo "✓ Loaded service"

# Check if running
sleep 2
if launchctl list | grep -q "com.earningstranscripts.job-scheduler"; then
    echo "✓ Service is running!"
else
    echo "✗ Service failed to start. Check logs:"
    echo "  tail -f $LOG_DIR/scheduler-stderr.log"
    exit 1
fi

echo
echo "=== Installation Complete ==="
echo
echo "Commands:"
echo "  Check status:  launchctl list | grep job-scheduler"
echo "  View logs:     tail -f $LOG_DIR/scheduler-stdout.log"
echo "  Stop service:  launchctl unload $PLIST_DEST"
echo "  Start service: launchctl load $PLIST_DEST"
echo "  Uninstall:     launchctl unload $PLIST_DEST && rm $PLIST_DEST"
echo
echo "The scheduler will now:"
echo "  • Start automatically when you log in"
echo "  • Restart if it crashes"
echo "  • Run your scheduled jobs (see: job-scheduler list)"
