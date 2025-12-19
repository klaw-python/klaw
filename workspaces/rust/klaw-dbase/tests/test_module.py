"""Integration tests for klaw-dbase module."""

import tempfile

import polars as pl
import pytest
from klaw_dbase import (
    DbaseError,
    DbcError,
    EmptySources,
    EncodingError,
    SchemaMismatch,
    read_dbase,
    scan_dbase,
    write_dbase,
)


def test_api_imports() -> None:
    """Test that all API components can be imported."""
    # Test main functions
    assert callable(scan_dbase)
    assert callable(read_dbase)
    assert callable(write_dbase)

    # Test error types
    assert DbaseError is not None
    assert EmptySources is not None
    assert SchemaMismatch is not None
    assert EncodingError is not None
    assert DbcError is not None

    # Test module imports
    import klaw_dbase

    assert hasattr(klaw_dbase, 'scan_dbase')
    assert hasattr(klaw_dbase, 'read_dbase')
    assert hasattr(klaw_dbase, 'write_dbase')


def test_error_types() -> None:
    """Test that appropriate error types are raised."""
    df = pl.from_dict({'x': [1, 2, 3]})

    # Test file not found
    with pytest.raises(pl.exceptions.ComputeError):
        read_dbase('nonexistent_file.dbf')

    # Test empty sources
    with pytest.raises((EmptySources, ValueError, DbaseError)):
        scan_dbase([]).collect()

    # Test invalid encoding
    import os

    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, 'test.dbf')

    try:
        write_dbase(df, temp_path, overwrite=True)

        with pytest.raises((EncodingError, DbaseError)):
            read_dbase(temp_path, encoding='invalid-encoding')

    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__])
