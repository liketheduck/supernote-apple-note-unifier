# Supernote Apple Note Unifier

Bidirectional sync between Apple Notes and Supernote devices.

## Overview

This tool syncs notes between Apple Notes on macOS and Supernote devices. Notes are stored in a dedicated `Apple` folder on your Supernote, mirroring your Apple Notes folder structure.

**Sync Directions:**
- **Forward** (default): Apple Notes → Supernote
- **Reverse**: Supernote → Apple Notes (sync `.txt` changes back)
- **Bidirectional**: Both directions with conflict resolution

**Content Types:**
- Text-only notes → `.txt` files (Markdown format, editable on Supernote)
- Rich notes (images, PDFs) → `.note` files (PDF background layer)

## Requirements

- macOS 13.0 (Ventura) or later
- Python 3.11 or later
- Xcode Command Line Tools (for Swift compilation)
- Supernote Personal Cloud storage mounted (default: `/Volumes/Storage/Supernote`)

## Installation

```bash
# Clone and setup
git clone https://github.com/yourusername/supernote-apple-note-unifier.git
cd supernote-apple-note-unifier

# Install dependencies
./scripts/install_deps.sh
./scripts/build_swift.sh

# Activate environment
source .venv/bin/activate
```

## Usage

### Basic Commands

```bash
# Forward sync (Apple → Supernote)
unifier sync

# Bidirectional sync (both directions)
unifier sync --direction both

# Reverse sync only (Supernote → Apple)
unifier sync --direction reverse

# Dry run (preview changes)
unifier sync --direction both --dry-run
```

### All Commands

| Command | Description |
|---------|-------------|
| `unifier sync` | Run sync process |
| `unifier backup` | Create Apple Notes backup |
| `unifier status` | Show sync statistics |
| `unifier info` | Display Supernote filesystem info |
| `unifier restore <note-id>` | View backup history for a note |

### Sync Options

```bash
unifier sync [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-d, --direction` | `forward`, `reverse`, or `both` (default: forward) |
| `-g, --generator` | `auto`, `markdown`, or `pdf` (default: auto) |
| `--backup/--no-backup` | Create backup before reverse sync (default: yes) |
| `-s, --supernote-path` | Path to Supernote storage |
| `-n, --dry-run` | Preview without making changes |
| `-v, --verbose` | Detailed output |

## Folder Structure

Notes mirror your Apple Notes folder hierarchy, including folders with emojis:

```
Supernote/Note/Apple/
├── 🏡 Home/
│   └── Renovation Ideas.txt
├── 👨🏻‍🍳 Recipes/
│   ├── Soup.txt
│   └── Turkey.note
...
```

Full structure example:

```
Supernote/Note/Apple/
├── Personal/
│   ├── Projects/
│   │   └── Meeting Notes.txt
│   └── Ideas.txt
├── Recipes/
│   ├── Soup.txt
│   └── Turkey.note          # Has images, uses PDF
└── Work/
    └── Project Plan.txt
```

## Sync Behavior

| Scenario | What Happens |
|----------|--------------|
| New Apple Note | Creates `.txt` or `.note` in matching Supernote folder |
| New `.txt` on Supernote | Creates Apple Note in matching folder |
| Modified Apple Note | Updates file on Supernote |
| Modified `.txt` on Supernote | Updates Apple Note (original backed up) |
| Deleted `.txt` on Supernote | Deletes Apple Note (original backed up) |
| Both sides changed | **Apple wins** (Supernote change discarded) |
| Locked Apple Note | Creates `.txt` with "**Locked in Apple Notes**" (no reverse sync) |

### Safety Features

1. **Originals Folder**: Before any Supernote change overwrites Apple Notes, the original is copied to "Originals (Supernote Sync)" folder
2. **Full Backup**: Optional timestamped JSON backup of all Apple Notes before sync
3. **Conflict Resolution**: Apple version always wins if both sides changed

## Scheduled Sync (launchd)

Run sync automatically every X minutes:

```bash
# Install (default: every 15 minutes)
./scripts/install_launchd.sh

# Custom interval (e.g., 30 minutes)
./scripts/install_launchd.sh 30

# Uninstall
./scripts/uninstall_launchd.sh

# View logs
tail -f ~/.local/share/supernote-unifier/logs/sync.log
```

## Generator Options

### Auto (default)
Automatically selects based on content:
- Text-only notes → Markdown `.txt`
- Notes with images/PDFs → PDF layer `.note`

### Markdown (`--generator markdown`)
Creates `.txt` files with Markdown formatting. Editable on Supernote.

### PDF Layer (`--generator pdf`)
Renders all content as PDF background. Preserves formatting but not editable.

### Strokes (`--generator strokes`)
Renders text as bitmap strokes on the main layer. Appears as handwritten ink but is not true vector strokes.

## Limitations

**What works:**
- ✅ Text-only notes sync bidirectionally (Apple ↔ Supernote via `.txt`)
- ✅ Folder structure with emojis preserved
- ✅ Rich notes (images/PDFs) sync forward as `.note` files
- ✅ Modifications to `.txt` on Supernote sync back to Apple Notes
- ✅ New `.txt` files created on Supernote create new Apple Notes
- ✅ Locked notes are detected and marked (reverse sync disabled)

**What doesn't work:**
- ❌ `.note` files cannot sync back (PDF layer is read-only)
- ❌ Images/attachments in notes are one-way only (Apple → Supernote)
- ❌ Handwritten annotations on Supernote don't sync back
- ❌ Apple Notes formatting (fonts, colors) is simplified in `.txt` output
- ❌ Locked Apple Notes content cannot be read (shows placeholder message)

**Personal Cloud Sync:**
Files are written directly to the mounted Supernote filesystem. If you see database connection errors during sync, the files are still created - you may need to manually refresh/sync on your Supernote device to see them. Full Personal Cloud database integration requires a separate MariaDB setup.

## Architecture

```
Apple Notes (macOS)
        │
        ▼
┌───────────────┐
│ Swift Bridge  │ ◄── AppleScript/ScriptingBridge
└───────────────┘
        │
        ▼
┌───────────────┐     ┌──────────────┐
│  Orchestrator │────►│ State DB     │ (SQLite)
└───────────────┘     └──────────────┘
        │
        ├─────────────────────────────┐
        ▼                             ▼
┌───────────────┐             ┌───────────────┐
│ Markdown Gen  │             │   PDF Gen     │
│   (.txt)      │             │   (.note)     │
└───────────────┘             └───────────────┘
        │                             │
        └──────────────┬──────────────┘
                       ▼
              Supernote/Note/Apple/
                       │
                       ▼ (reverse sync)
              ┌───────────────┐
              │ Reverse Sync  │
              │    Engine     │
              └───────────────┘
                       │
                       ▼
                 Apple Notes
```

## Troubleshooting

### "Supernote volume not mounted"
```bash
ls /Volumes/Storage/Supernote
```
Mount your Supernote Personal Cloud storage first.

### "Swift bridge not found"
```bash
./scripts/build_swift.sh
```

### "Could not connect to Notes app"
1. Open Notes.app at least once
2. Grant Terminal access when prompted
3. Check System Settings > Privacy & Security > Automation

### Existing flat files after upgrade
If you have old files in flat `Note/Apple/*.txt`, delete them and re-sync to get proper folder structure:
```bash
# Remove old flat files (backup first!)
rm /Volumes/Storage/Supernote/.../Note/Apple/*.txt

# Re-sync with folder structure
unifier sync
```

### Reset state database
```bash
rm ~/.local/share/supernote-unifier/state.db
```

## File Locations

| Path | Purpose |
|------|---------|
| `~/.local/share/supernote-unifier/state.db` | Sync state database |
| `~/.local/share/supernote-unifier/backups/` | Apple Notes backups |
| `~/.local/share/supernote-unifier/logs/` | Scheduled sync logs |

## Disclaimer

Apple Notes is a trademark of Apple Inc. Supernote is a trademark of Ratta Software.
This project is not affiliated with, endorsed by, or sponsored by Apple Inc. or Ratta Software.

## License

MIT License
