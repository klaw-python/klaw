from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from polars import DataFrame

from ._dbase_rs import EmptySources, write_dbase_buff, write_dbase_file


def write_dbase(
    df: DataFrame,
    dest: str | Path | BinaryIO,
    *,
    batch_size: int | None = None,
    encoding: str | None = 'cp1252',
    overwrite: bool | None = False,
    memo_threshold: int | None = None,
) -> None:
    """Write a DataFrame to a dBase file.

    Parameters:
        df: The DataFrame to write.
        dest: The destination to write the DataFrame to.
        batch_size: The batch size to use for writing the dBase file. Defaults to None.
        encoding: The encoding to use for writing the dBase file. Defaults to "cp1252".
        overwrite: Whether to overwrite the destination if it exists. Defaults to False.
        memo_threshold: The memo threshold to use for writing the dBase file. Defaults to None.

    Example:
        ??? example "Write a DataFrame to a dBase file"

            ```python
            import polars as pl
            from klaw_dbase import write_dbase

            df: pl.DataFrame = pl.DataFrame({"column_1": [1, 2, 3], "column_2": [4, 5, 6]})
            write_dbase(df, "data.dbf")
            ```

        ??? example "Write with a custom encoding"

            ```python
            import polars as pl
            from klaw_dbase import write_dbase

            df: pl.DataFrame = pl.DataFrame({"column_1": [1, 2, 3], "column_2": [4, 5, 6]})
            write_dbase(df, "data.dbf", encoding="utf-8")
            ```

        ??? example "Write with overwrite enabled"

            ```python
            import polars as pl
            from klaw_dbase import write_dbase

            df: pl.DataFrame = pl.DataFrame({"column_1": [1, 2, 3], "column_2": [4, 5, 6]})
            write_dbase(df, "data.dbf", overwrite=True)
            ```

        ??? example "Write with a custom memo threshold"

            ```python
            import polars as pl
            from klaw_dbase import write_dbase

            df: pl.DataFrame = pl.DataFrame({"column_1": [1, 2, 3], "column_2": [4, 5, 6]})
            write_dbase(df, "data.dbf", memo_threshold=1000)
            ```
    """
    if df.is_empty():
        print(df)
        raise EmptySources

    frames = [df] if batch_size is None else [df[i : i + batch_size].rechunk() for i in range(0, len(df), batch_size)]

    if memo_threshold is not None:
        memo_threshold = None

    match dest:
        case str() | Path():
            expanded = str(Path(dest).expanduser())

            write_dbase_file(
                frames=frames,
                dest=expanded,
                encoding=encoding,
                overwrite=overwrite,
                memo_threshold=memo_threshold,
            )

        case _:
            write_dbase_buff(
                frames=frames,
                buff=dest,
                encoding=encoding,
                memo_threshold=memo_threshold,
            )
