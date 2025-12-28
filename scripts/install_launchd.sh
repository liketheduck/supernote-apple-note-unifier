#!/bin/bash
# Install launchd service for scheduled bidirectional sync
# Usage: ./scripts/install_launchd.sh [interval_minutes]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.supernote-unifier.sync"
PLIST_SOURCE="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$HOME/.local/share/supernote-unifier/logs"

# Default interval: 15 minutes
INTERVAL_MINUTES="${1:-15}"
INTERVAL_SECONDS=$((INTERVAL_MINUTES * 60))

echo "Supernote Unifier - launchd Installation"
echo "========================================="
echo "Sync interval: $INTERVAL_MINUTES minutes"
echo ""

# Create log directory
mkdir -p "$LOG_DIR"

# Check if already installed
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Generate customized plist
echo "Generating plist with your settings..."

cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/.venv/bin/python</string>
        <string>-m</string>
        <string>unifier.cli</string>
        <string>sync</string>
        <string>--direction</string>
        <string>both</string>
        <string>--backup</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>

    <key>StartInterval</key>
    <integer>$INTERVAL_SECONDS</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/sync.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/sync-error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONPATH</key>
        <string>$PROJECT_DIR/src</string>
    </dict>

    <key>ThrottleInterval</key>
    <integer>60</integer>
</dict>
</plist>
EOF

echo "Loading service..."
launchctl load "$PLIST_DEST"

echo ""
echo "Installation complete!"
echo ""
echo "Service status:"
launchctl list | grep "$PLIST_NAME" || echo "  (not running yet - will start on next interval)"
echo ""
echo "Useful commands:"
echo "  View logs:     tail -f $LOG_DIR/sync.log"
echo "  View errors:   tail -f $LOG_DIR/sync-error.log"
echo "  Stop service:  launchctl unload $PLIST_DEST"
echo "  Start service: launchctl load $PLIST_DEST"
echo "  Run now:       launchctl start $PLIST_NAME"
echo "  Uninstall:     ./scripts/uninstall_launchd.sh"
