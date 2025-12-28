#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/swift-bridge"

echo "Building AppleNotesBridge..."
swift build -c release

# Copy to predictable location
mkdir -p "$PROJECT_DIR/bin"
cp .build/release/notes-bridge "$PROJECT_DIR/bin/"

echo "Built: bin/notes-bridge"
echo ""
echo "Test it with:"
echo "  ./bin/notes-bridge list-folders"
echo "  ./bin/notes-bridge export-all --html"
