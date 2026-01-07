#!/usr/bin/env python3
"""Demo script showing progress tracking modes for parallel DBC reading."""

import time
from pathlib import Path

from klaw_dbase import scan_dbase

DBC_FILES = [
    'data/RDPA2401.dbc',
    'data/RDPA2402.dbc',
    'data/RDPA2403.dbc',
    'data/RDPA2404.dbc',
    'data/RDPA2405.dbc',
    'data/RDPA2406.dbc',
]


def check_files():
    """Check if demo files exist."""
    existing = [f for f in DBC_FILES if Path(f).exists()]
    if not existing:
        print('No DBC files found. Expected files:')
        for f in DBC_FILES:
            print(f'  - {f}')
        return []
    return existing


def demo_no_progress(files: list[str]):
    """Read files without progress tracking."""
    print('\n' + '=' * 60)
    print('MODE 1: No Progress (progress=False)')
    print('=' * 60)

    start = time.perf_counter()
    df = scan_dbase(files, progress=False).collect()
    elapsed = time.perf_counter() - start

    print(f'Read {len(df):,} rows x {len(df.columns)} columns in {elapsed:.2f}s')
    print(f'Throughput: {len(df) / elapsed:,.0f} rows/sec')


def demo_with_progress(files: list[str]):
    """Read files with progress tracking (per-file + overall)."""
    print('\n' + '=' * 60)
    print('MODE 2: With Progress (progress=True)')
    print('=' * 60)

    start = time.perf_counter()
    df = scan_dbase(files, progress=True).collect()
    elapsed = time.perf_counter() - start

    print(f'Read {len(df):,} rows x {len(df.columns)} columns in {elapsed:.2f}s')
    print(f'Throughput: {len(df) / elapsed:,.0f} rows/sec')


def main():
    """Run the progress tracking demo."""
    print('=' * 60)
    print('klaw-dbase Progress Tracking Demo')
    print('=' * 60)

    files = check_files()
    if not files:
        return

    print(f'\nFiles to read: {len(files)}')
    for f in files:
        print(f'  - {f}')

    # Demo each mode
    demo_no_progress(files)
    demo_with_progress(files)

    print('\n' + '=' * 60)
    print('Demo complete!')
    print('=' * 60)


if __name__ == '__main__':
    main()
