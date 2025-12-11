"""Scan and sink dBase files.

This module provides three functions: `scan_dbase`, `read_dbase`, and `write_dbase`.

`scan_dbase` scans a dBase file or files and returns a `LazyFrame`.

`read_dbase` reads a dBase file or files into a `DataFrame`.

`write_dbase` writes a `DataFrame` to a dBase file.
"""

from ._dbase_rs import DbaseError, EmptySources, SchemaMismatch, EncodingError, DbcError
from ._scan import read_dbase, scan_dbase, get_dbase_record_count
from ._sink import write_dbase

__all__ = [
    "DbaseError",
    "EmptySources",
    "SchemaMismatch",
    "EncodingError",
    "DbcError",
    "scan_dbase",
    "read_dbase",
    "write_dbase",
    "get_dbase_record_count",
]