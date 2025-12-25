#!/usr/bin/env python3
"""
Data Migration Script

Migrates existing earnings data from old directory structure
to new configurable data directory.

Old structure (in project root):
  ./transcripts/
  ./secfilings/
  ./.sec_cache/

New structure (configurable location):
  {data_dir}/transcripts/
  {data_dir}/secfilings/
  {data_dir}/cache/
  {data_dir}/metadata.db

Usage:
  python migrate_data.py
  python migrate_data.py --data-dir /path/to/new/location
  python migrate_data.py --copy  # Copy instead of move
"""

import argparse
import shutil
import sys
from pathlib import Path

from config import Config, get_config


def migrate_data(target_data_dir: str = None, copy: bool = False, dry_run: bool = False):
    """
    Migrate data from old structure to new configurable location.

    Args:
        target_data_dir: Target data directory (uses config if None)
        copy: Copy files instead of moving (safer but uses more disk space)
        dry_run: Show what would be done without actually doing it
    """
    # Get target configuration
    if target_data_dir:
        config = Config(target_data_dir)
    else:
        config = get_config()

    print("=" * 70)
    print("EARNINGS DATA MIGRATION")
    print("=" * 70)
    print(f"\nTarget data directory: {config.data_dir}")
    print(f"Operation: {'COPY' if copy else 'MOVE'}")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE'}")
    print()

    # Source directories (old structure in project root)
    project_root = Path(__file__).parent
    old_dirs = {
        'transcripts': project_root / 'transcripts',
        'secfilings': project_root / 'secfilings',
        'cache': project_root / '.sec_cache'
    }

    # Target directories (new structure)
    new_dirs = {
        'transcripts': config.transcripts_dir,
        'secfilings': config.secfilings_dir,
        'cache': config.cache_dir
    }

    # Check what needs to be migrated
    migrations = []
    total_size = 0

    for name, old_path in old_dirs.items():
        new_path = new_dirs[name]

        if not old_path.exists():
            print(f"⊘ {name:12s} - No data found at {old_path}")
            continue

        if old_path == new_path:
            print(f"✓ {name:12s} - Already at target location")
            continue

        # Count files and size
        file_count = sum(1 for _ in old_path.rglob('*') if _.is_file())
        dir_size = sum(f.stat().st_size for f in old_path.rglob('*') if f.is_file())
        total_size += dir_size

        migrations.append({
            'name': name,
            'old_path': old_path,
            'new_path': new_path,
            'file_count': file_count,
            'size': dir_size
        })

        print(f"→ {name:12s} - {file_count:6d} files ({dir_size / (1024**3):.2f} GB)")
        print(f"  From: {old_path}")
        print(f"  To:   {new_path}")
        print()

    if not migrations:
        print("\n✓ No migration needed - all data is already in the target location!")
        return

    # Summary
    print("=" * 70)
    print(f"Total: {len(migrations)} directories, {total_size / (1024**3):.2f} GB")
    print("=" * 70)

    if dry_run:
        print("\n✓ DRY RUN COMPLETE - No changes were made")
        print("\nTo perform the actual migration, run without --dry-run:")
        if target_data_dir:
            print(f"  python migrate_data.py --data-dir {target_data_dir}")
        else:
            print("  python migrate_data.py")
        return

    # Confirm
    print("\nThis will", "COPY" if copy else "MOVE", "your data to the new location.")
    if not copy:
        print("⚠️  WARNING: MOVE will delete data from old location after copying!")
    print(f"\nProceed? (yes/no): ", end='')

    response = input().strip().lower()
    if response not in ['yes', 'y']:
        print("\n✗ Migration cancelled")
        return

    # Perform migration
    print("\n" + "=" * 70)
    print("STARTING MIGRATION")
    print("=" * 70)

    for migration in migrations:
        name = migration['name']
        old_path = migration['old_path']
        new_path = migration['new_path']

        print(f"\nMigrating {name}...")

        try:
            # Ensure parent directory exists
            new_path.parent.mkdir(parents=True, exist_ok=True)

            if new_path.exists():
                print(f"  ⚠️  Target already exists: {new_path}")
                print(f"  Skipping to avoid overwriting existing data")
                continue

            if copy:
                # Copy directory tree
                print(f"  Copying {old_path} -> {new_path}")
                shutil.copytree(old_path, new_path)
                print(f"  ✓ Copied successfully")
            else:
                # Move directory
                print(f"  Moving {old_path} -> {new_path}")
                shutil.move(str(old_path), str(new_path))
                print(f"  ✓ Moved successfully")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            print(f"\nMigration failed for {name}. Please fix the error and try again.")
            return

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE!")
    print("=" * 70)

    # Create index
    print("\nNext steps:")
    print("1. Verify data in new location:")
    print(f"   ls -lh {config.transcripts_dir}")
    print(f"   ls -lh {config.secfilings_dir}")
    print()
    print("2. Create metadata index:")
    print("   earnings-index")
    print()
    print("3. Test queries:")
    print("   earnings-query --stats")
    print("   python examples/basic_usage.py")

    if not copy:
        print()
        print("4. Optional: Remove old empty directories")
        print("   (Only if you're sure migration was successful)")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate earnings data to new directory structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (see what would happen)
  python migrate_data.py --dry-run

  # Migrate to default location (~/.earnings_data)
  python migrate_data.py

  # Migrate to custom location
  python migrate_data.py --data-dir /data/earnings

  # Copy instead of move (safer but uses more disk)
  python migrate_data.py --copy

  # Migrate to location from .env file
  # (make sure EARNINGS_DATA_DIR is set in .env)
  python migrate_data.py
        """
    )

    parser.add_argument(
        '--data-dir',
        help='Target data directory (default: from config/env)'
    )
    parser.add_argument(
        '--copy',
        action='store_true',
        help='Copy files instead of moving (safer but uses more disk space)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )

    args = parser.parse_args()

    try:
        migrate_data(
            target_data_dir=args.data_dir,
            copy=args.copy,
            dry_run=args.dry_run
        )
    except KeyboardInterrupt:
        print("\n\n✗ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
