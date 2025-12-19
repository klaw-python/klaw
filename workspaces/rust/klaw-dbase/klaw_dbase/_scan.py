from __future__ import annotations

from collections.abc import Iterator, Sequence
from glob import iglob
from os import path
from pathlib import Path
from typing import BinaryIO, Literal

import polars as pl
from polars import DataFrame, Expr, LazyFrame, Schema
from polars.io.plugins import register_io_source

from ._dbase_rs import DbaseSource, EmptySources, EncodingError, get_record_count
from ._utils import validate_encoding


def expand_str(source: str | Path, *, glob: bool) -> Iterator[str]:
    expanded = Path(source).expanduser()
    if glob and '*' in expanded:
        yield from sorted(iglob(expanded))
    elif Path(expanded).is_dir():
        yield from sorted(iglob(path.join(expanded, '*')))
    else:
        yield expanded


def scan_dbase(
    sources: Sequence[str | Path] | Sequence[BinaryIO] | str | Path | BinaryIO,
    *,
    batch_size: int = 8192,
    single_col_name: str | None = None,
    encoding: Literal[
        'utf8',
        'utf8-lossy',
        'ascii',
        'cp1252',
        'cp850',
        'cp437',
        'cp852',
        'cp866',
        'cp865',
        'cp861',
        'cp874',
        'cp1255',
        'cp1256',
        'cp1250',
        'cp1251',
        'cp1254',
        'cp1253',
        'gbk',
        'big5',
        'shift_jis',
        'euc-jp',
        'euc-kr',
    ]
    | None = 'cp1252',
    character_trim: Literal['begin', 'end', 'begin_end', 'both', 'none'] | None = 'begin_end',
    skip_deleted: bool | None = True,
    validate_schema: bool | None = True,
    compressed: bool | None = False,
    glob: bool = True,
    progress: bool = False,
) -> LazyFrame:
    """Scan a dBase file or files.

    Parameters:
        sources: The dBase file or files to scan.
        batch_size: The batch size to use for reading the dBase file. Defaults to 32768.
        single_col_name: The name of the single column to read. Defaults to None.
        encoding: The encoding to use for reading the dBase file. Defaults to "cp1252".
        character_trim: The character trim to use for reading the dBase file. Defaults to "begin_end".
        skip_deleted: Whether to skip deleted records. Defaults to True.
        validate_schema: Whether to validate the schema. Defaults to True.
        compressed: Whether to read the dBase file as compressed. Defaults to True.
        glob: Whether to use glob patterns. Defaults to False.
        progress: Whether to show a progress bar during scanning. Defaults to False.

    Returns:
        LazyFrame: The scanned dBase file.

    Example:
        ??? example "Scan a single dBase file"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf")
            ```

        ??? example "Scan multiple dBase files"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase(["data1.dbf", "data2.dbf"])
            ```

        ??? example "Scan with a custom batch size"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", batch_size=1000)
            ```

        ??? example "Scan with a custom encoding"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", encoding="utf-8")
            ```

        ??? example "Scan with a custom character trim"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", character_trim="end")
            ```

        ??? example "Scan with a custom single column name"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", single_col_name="column_name")
            ```

        ??? example "Scan with skip deleted records disabled"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", skip_deleted=False)
            ```

        ??? example "Scan with schema validation disabled"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbf", validate_schema=False)
            ```

        ??? example "Scan a compressed dBase file"

            ```python
            import polars as pl
            from klaw_dbase import scan_dbase

            df: pl.LazyFrame = scan_dbase("data.dbc", compressed=True)
            ```
    """
    # normalize sources
    strs: list[str] = []
    bins: list[BinaryIO] = []
    match sources:
        case [*_]:
            for source in sources:
                if isinstance(source, str | Path):
                    strs.extend(expand_str(source, glob=glob))
                else:
                    bins.append(source)
        case str() | Path():
            strs.extend(expand_str(sources, glob=glob))
        case _:
            bins.append(sources)

    def_batch_size = batch_size

    if len(strs) == 0 and len(bins) == 0:
        raise EmptySources

    if validate_encoding(encoding):
        pass
    else:
        raise EncodingError(f'Unsupported encoding: {encoding}')

    src = DbaseSource(
        paths=strs,
        buffs=bins,
        single_col_name=single_col_name,
        encoding=encoding,
        character_trim=character_trim,
        skip_deleted=skip_deleted,
        validate_schema=validate_schema,
        compressed=compressed,
    )

    def get_schema() -> Schema:
        return Schema(src.schema())

    def source_generator(
        with_columns: list[str] | None,
        predicate: Expr | None,
        n_rows: int | None,
        batch_size: int | None,
    ) -> Iterator[DataFrame]:
        # Use progress-enabled iterator if requested
        if progress:
            dbase_iter = src.batch_iter_with_progress(batch_size or def_batch_size, with_columns, True)
        else:
            dbase_iter = src.batch_iter(batch_size or def_batch_size, with_columns)

        while (batch := dbase_iter.next()) is not None:
            if predicate is not None:
                batch = batch.filter(predicate)
            if n_rows is None:
                yield batch
            else:
                batch = batch[:n_rows]
                n_rows -= len(batch)
                yield batch
                if n_rows == 0:
                    break

    try:
        return register_io_source(source_generator, schema=get_schema)
    except TypeError:
        eager_schema = get_schema()
        return register_io_source(source_generator, schema=eager_schema)


def read_dbase(
    sources: Sequence[str | Path] | Sequence[BinaryIO] | str | Path | BinaryIO,
    *,
    columns: Sequence[int | str] | None = None,
    n_rows: int | None = None,
    row_index_name: str | None = None,
    row_index_offset: int = 0,
    rechunk: bool = False,
    batch_size: int = 8192,
    glob: bool = True,
    single_col_name: str | None = None,
    encoding: Literal[
        'utf8',
        'utf8-lossy',
        'ascii',
        'cp1252',
        'cp850',
        'cp437',
        'cp852',
        'cp866',
        'cp865',
        'cp861',
        'cp874',
        'cp1255',
        'cp1256',
        'cp1250',
        'cp1251',
        'cp1254',
        'cp1253',
        'gbk',
        'big5',
        'shift_jis',
        'euc-jp',
        'euc-kr',
    ]
    | None = 'cp1252',
    character_trim: Literal['begin', 'end', 'begin_end', 'both', 'none'] | None = 'begin_end',
    skip_deleted: bool = True,
    validate_schema: bool = True,
    compressed: bool = False,
) -> DataFrame:
    """Read a dBase file or files into a DataFrame.

    Parameters:
        sources: The dBase file or files to read.
        columns: hich reads all columns.
        n_rows: The number of rows to read. Defaults to None, which reads all rows.
        row_index_name: The name of the row index column. Defaults to None.
        row_index_offset: The offset to add to the row index. Defaults to 0.
        rechunk: Whether to rechunk the DataFrame. Defaults to False.
        batch_size: The batch size to use for reading the dBase file. Defaults to 32768.
        glob: Whether to use glob patterns. Defaults to False.
        single_col_name: The name of the single column to read. Defaults to None.
        encoding: The encoding to use for reading the dBase file. Defaults to "cp1252".
        character_trim: The character trim to use for reading the dBase file. Defaults to "begin_end".
        skip_deleted: Whether to skip deleted records. Defaults to True.
        validate_schema: Whether to validate the schema. Defaults to True.
        compressed: Whether to read the dBase file as compressed. Defaults to True.

    Returns:
        DataFrame: The read dBase file as a DataFrame.

    Example:
        ??? example "Read a single dBase file"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf")
            ```

        ??? example "Read multiple dBase files"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase(["data1.dbf", "data2.dbf"])
            ```

        ??? example "Read with a custom batch size"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", batch_size=1000)
            ```

        ??? example "Read with a custom encoding"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", encoding="utf-8")
            ```

        ??? example "Read with a custom character trim"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", character_trim="end")
            ```

        ??? example "Read with a custom single column name"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", single_col_name="column_name")
            ```

        ??? example "Read with skip deleted records disabled"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", skip_deleted=False)
            ```

        ??? example "Read with schema validation disabled"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbf", validate_schema=False)
            ```

        ??? example "Read a compressed dBase file"

            ```python
            import polars as pl
            from klaw_dbase import read_dbase

            df: pl.DataFrame = read_dbase("data.dbc", compressed=True)
            ```
    """
    lazy = scan_dbase(
        sources=sources,
        batch_size=batch_size,
        single_col_name=single_col_name,
        encoding=encoding,
        character_trim=character_trim,
        skip_deleted=skip_deleted,
        validate_schema=validate_schema,
        compressed=compressed,
        glob=glob,
    )
    if columns is not None:
        lazy = lazy.select([pl.nth(c) if isinstance(c, int) else pl.col(c) for c in columns])
    if row_index_name is not None:
        lazy = lazy.with_row_index(row_index_name, offset=row_index_offset)
    if n_rows is not None:
        lazy = lazy.limit(n_rows)
    res = lazy.collect()
    return res.rechunk() if rechunk else res


def get_dbase_record_count(path: str | Path) -> int:
    """Get the number of records in a dBase file.

    Parameters:
        path: The path to the dBase file.

    Returns:
        int: The number of records in the dBase file.

    Example:
        ??? example "Get the number of records in a dBase file"

            ```python
            from klaw_dbase import get_dbase_record_count

            record_count_dbf: int = get_dbase_record_count("data.dbf")
            record_count_dbc: int = get_dbase_record_count("data.dbc")

            print(f"Record count DBF: {record_count_dbf}")
            print(f"Record count DBC: {record_count_dbc}")
            ```
    """
    if not isinstance(path, (str, Path)):
        raise TypeError('path must be a string or Path')

    match path:
        case str():
            return get_record_count(path)

        case Path():
            return get_record_count(str(path))

        case _:
            raise TypeError('path must be a string or Path')
