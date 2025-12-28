"""
Command-line interface for the Supernote Apple Note Unifier.
"""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

from .generators.base import GeneratorType
from .supernote.paths import DEFAULT_SUPERNOTE_BASE, verify_supernote_mounted

console = Console()

DEFAULT_STATE_DB = Path.home() / ".local/share/supernote-unifier/state.db"
DEFAULT_SWIFT_BRIDGE = Path(__file__).parent.parent.parent / "bin/notes-bridge"
DEFAULT_BACKUP_DIR = Path.home() / ".local/share/supernote-unifier/backups"


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Supernote Apple Note Unifier - Mirror Apple Notes to Supernote"""
    pass


@main.command()
@click.option(
    '--generator', '-g',
    type=click.Choice(['auto', 'strokes', 'text', 'pdf']),
    default='auto',
    help='Generator type: auto (default), strokes, text (.txt), or pdf'
)
@click.option(
    '--supernote-path', '-s',
    type=click.Path(path_type=Path),
    default=DEFAULT_SUPERNOTE_BASE,
    help='Path to Supernote data directory'
)
@click.option(
    '--direction', '-d',
    type=click.Choice(['forward', 'reverse', 'both']),
    default='forward',
    help='Sync direction: forward (Apple->Supernote), reverse (Supernote->Apple), both'
)
@click.option(
    '--backup/--no-backup',
    default=True,
    help='Create Apple Notes backup before reverse sync (default: yes)'
)
@click.option(
    '--dry-run', '-n',
    is_flag=True,
    help='Show what would be done without making changes'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Verbose output'
)
def sync(generator: str, supernote_path: Path, direction: str, backup: bool,
         dry_run: bool, verbose: bool):
    """Run the sync process

    By default (--generator auto), text-only notes become Markdown .txt files,
    while notes with images/attachments use the PDF generator for visual accuracy.

    Sync directions:
    - forward: Apple Notes -> Supernote (default, one-way)
    - reverse: Supernote -> Apple Notes (sync .txt changes back)
    - both: Full bidirectional sync

    Conflict resolution: Apple wins (if both sides changed, Apple version prevails).
    """
    console.print("[bold]Supernote Apple Note Unifier[/bold]")
    console.print(f"Direction: [cyan]{direction}[/cyan]")
    console.print(f"Supernote path: {supernote_path}")

    if not verify_supernote_mounted(supernote_path):
        console.print(f"[red]Error: Supernote volume not mounted at {supernote_path}[/red]")
        raise click.Abort()

    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]")

    # Ensure state directory exists
    DEFAULT_STATE_DB.parent.mkdir(parents=True, exist_ok=True)

    try:
        if direction in ('reverse', 'both'):
            # Use bidirectional engine
            from .sync.engine import BidirectionalSyncEngine

            engine = BidirectionalSyncEngine(
                supernote_base=supernote_path,
                state_db_path=DEFAULT_STATE_DB,
                swift_bridge_path=DEFAULT_SWIFT_BRIDGE,
                backup_dir=DEFAULT_BACKUP_DIR,
            )

            if direction == 'both':
                stats = engine.run_bidirectional(
                    dry_run=dry_run,
                    verbose=verbose,
                    create_backup=backup,
                )
            else:  # reverse only
                if backup and not dry_run:
                    engine.create_backup()
                stats = engine.run_reverse_sync(dry_run=dry_run, verbose=verbose)

            # Display bidirectional results
            table = Table(title="Sync Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green")

            if direction == 'both':
                table.add_row("[bold]Forward Sync (Apple -> Supernote)[/bold]", "")
                table.add_row("Total notes", str(stats.forward_total))
                table.add_row("Created", str(stats.forward_created))
                table.add_row("Updated", str(stats.forward_updated))
                table.add_row("Skipped", str(stats.forward_skipped))
                table.add_row("Failed", str(stats.forward_failed))
                table.add_row("─" * 35, "─" * 5)

            table.add_row("[bold]Reverse Sync (Supernote -> Apple)[/bold]", "")
            table.add_row("Created (new from Supernote)", str(stats.reverse_created))
            table.add_row("Modified (synced back)", str(stats.reverse_modified))
            table.add_row("Deleted (synced back)", str(stats.reverse_deleted))
            table.add_row("Skipped", str(stats.reverse_skipped))
            table.add_row("Failed", str(stats.reverse_failed))
            table.add_row("Originals backed up", str(stats.originals_backed_up))

            if stats.conflicts_detected:
                table.add_row("─" * 35, "─" * 5)
                table.add_row("[yellow]Conflicts detected[/yellow]", str(stats.conflicts_detected))
                table.add_row("Resolved (Apple wins)", str(stats.conflicts_resolved_apple_wins))

            console.print(table)

            if stats.errors:
                console.print("\n[red]Errors:[/red]")
                for err in stats.errors:
                    console.print(f"  - {err}")

        else:
            # Forward sync only (original behavior)
            gen_type = {
                'auto': GeneratorType.AUTO,
                'strokes': GeneratorType.STROKES,
                'text': GeneratorType.TEXT,
                'pdf': GeneratorType.PDF_LAYER,
            }[generator]

            if generator == 'auto':
                console.print("Generator: [cyan]auto[/cyan] (text .txt for text-only, pdf for rich content)")
            else:
                console.print(f"Generator: [cyan]{generator}[/cyan]")

            from .orchestrator import Orchestrator

            orchestrator = Orchestrator(
                supernote_base=supernote_path,
                state_db_path=DEFAULT_STATE_DB,
                swift_bridge_path=DEFAULT_SWIFT_BRIDGE,
                generator_type=gen_type
            )

            stats = orchestrator.run(dry_run=dry_run, verbose=verbose)

            # Update Supernote hashes after forward sync for future reverse detection
            if not dry_run:
                from .sync.engine import BidirectionalSyncEngine
                engine = BidirectionalSyncEngine(
                    supernote_base=supernote_path,
                    state_db_path=DEFAULT_STATE_DB,
                    swift_bridge_path=DEFAULT_SWIFT_BRIDGE,
                )
                engine.update_supernote_hashes()

            # Display results
            table = Table(title="Sync Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green")

            table.add_row("Total notes", str(stats["total"]))
            table.add_row("Created", str(stats["created"]))
            table.add_row("Updated", str(stats["updated"]))
            table.add_row("Skipped (unchanged)", str(stats["skipped"]))
            table.add_row("Failed", str(stats["failed"]))

            if generator == 'auto':
                table.add_row("─" * 20, "─" * 5)
                table.add_row("Text-only (native)", str(stats.get("text_only", 0)))
                table.add_row("Rich content (pdf)", str(stats.get("rich_content", 0)))

            console.print(table)

            if stats.get("errors"):
                console.print("\n[red]Errors:[/red]")
                for err in stats["errors"]:
                    console.print(f"  - {err['note']}: {err['error']}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


@main.command()
@click.option(
    '--supernote-path', '-s',
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_SUPERNOTE_BASE,
    help='Path to Supernote data directory'
)
def status(supernote_path: Path):
    """Show current sync status"""
    console.print(f"[bold]Supernote Apple Note Unifier - Status[/bold]")
    console.print(f"Supernote path: {supernote_path}")

    if not verify_supernote_mounted(supernote_path):
        console.print(f"[yellow]Warning: Supernote volume not mounted[/yellow]")

    if not DEFAULT_STATE_DB.exists():
        console.print("[yellow]No sync history found. Run 'sync' first.[/yellow]")
        return

    from .state import StateDatabase
    db = StateDatabase(DEFAULT_STATE_DB)
    stats = db.get_statistics()

    table = Table(title="Sync Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Total notes processed", str(stats['total_files']))
    table.add_row("Successful", str(stats['successful']))
    table.add_row("Failed", str(stats['failed']))

    console.print(table)


@main.command()
@click.option(
    '--supernote-path', '-s',
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_SUPERNOTE_BASE,
    help='Path to Supernote data directory'
)
def info(supernote_path: Path):
    """Show Supernote filesystem info"""
    console.print("[bold]Supernote Filesystem Info[/bold]")

    from .supernote.paths import get_user_data_path, get_note_directory

    if not verify_supernote_mounted(supernote_path):
        console.print(f"[red]Error: Supernote volume not mounted at {supernote_path}[/red]")
        raise click.Abort()

    user_path = get_user_data_path(supernote_path)
    note_dir = get_note_directory(supernote_path)

    console.print(f"Base path: {supernote_path}")
    console.print(f"User data path: {user_path or 'Not found'}")
    console.print(f"Note directory: {note_dir or 'Not found'}")

    if note_dir:
        # Count .note files
        note_files = list(note_dir.rglob("*.note"))
        console.print(f"Total .note files: {len(note_files)}")

        # List top-level folders
        folders = [d for d in note_dir.iterdir() if d.is_dir()]
        console.print(f"Folders: {', '.join(d.name for d in folders)}")


@main.command()
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=DEFAULT_BACKUP_DIR,
    help='Directory to store backups'
)
def backup(output_dir: Path):
    """Create a full backup of Apple Notes.

    Creates a timestamped JSON file containing all notes and folders.
    Useful before running bidirectional sync or making major changes.
    """
    console.print("[bold]Apple Notes Backup[/bold]")
    console.print(f"Output directory: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import subprocess
        import json

        result = subprocess.run(
            [str(DEFAULT_SWIFT_BRIDGE), "backup-all", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            console.print(f"[red]Error: {result.stderr}[/red]")
            raise click.Abort()

        data = json.loads(result.stdout)

        if data.get("success"):
            console.print(f"[green]Backup created successfully![/green]")
            console.print(f"Path: {data.get('backupPath')}")
            console.print(f"Notes: {data.get('noteCount')}")
            console.print(f"Folders: {data.get('folderCount')}")
        else:
            console.print(f"[red]Backup failed[/red]")
            raise click.Abort()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort()


@main.command()
@click.argument('note_id')
def restore(note_id: str):
    """List backup history for a note and optionally restore.

    Shows all backed-up versions of a note from the Originals folder.
    """
    console.print(f"[bold]Backup History for Note: {note_id}[/bold]")

    from .state import StateDatabase

    if not DEFAULT_STATE_DB.exists():
        console.print("[yellow]No sync history found.[/yellow]")
        return

    db = StateDatabase(DEFAULT_STATE_DB)
    originals = db.get_originals(note_id)

    if not originals:
        console.print("[yellow]No backups found for this note.[/yellow]")
        return

    table = Table(title="Backup History")
    table.add_column("Date", style="cyan")
    table.add_column("Reason", style="yellow")
    table.add_column("Backup Note ID", style="dim")

    for orig in originals:
        table.add_row(
            orig.get("backed_up_at", "Unknown"),
            orig.get("reason", "Unknown"),
            orig.get("backup_folder_note_id", "N/A"),
        )

    console.print(table)
    console.print("\nTo restore, find the backup note in the 'Originals (Supernote Sync)' folder in Apple Notes.")


if __name__ == "__main__":
    main()
