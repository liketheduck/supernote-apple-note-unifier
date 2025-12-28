#!/bin/bash
# Uninstall launchd service for scheduled sync

set -e

PLIST_NAME="com.supernote-unifier.sync"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "Supernote Unifier - launchd Uninstallation"
echo "==========================================="
echo ""

if [ -f "$PLIST_DEST" ]; then
    echo "Stopping and unloading service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true

    echo "Removing plist file..."
    rm "$PLIST_DEST"

    echo ""
    echo "Service uninstalled successfully!"
else
    echo "Service not installed (plist not found at $PLIST_DEST)"
fi

echo ""
echo "Note: Log files and backups are preserved in ~/.local/share/supernote-unifier/"
echo "To remove those as well, run:"
echo "  rm -rf ~/.local/share/supernote-unifier"
