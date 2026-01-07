# klaw-dbase

A Polars plugin for reading and writing dBase III files (.DBF), with built-in support for DATASUS compressed files (.DBC).

## Features

- **Polars IO plugin** with lazy scanning, projection pushdown, and predicate pushdown
- **DATASUS .DBC support** for compressed Brazilian health system files
- **Parallel reading** across multiple files
- **Flexible encodings** (`cp1252`, `utf-8`, `iso-8859-1`, etc.)
- **Globbing and directory scanning**

## Installation

```bash
pip install klaw-dbase
```

**Requirements:** Python 3.13+

## Quickstart

### Read a .DBF file

```python
from klaw_dbase import read_dbase

df = read_dbase('data.dbf')
```

### Lazy scan for large files

```python
import polars as pl
from klaw_dbase import scan_dbase

lf = scan_dbase('data.dbf')
result = lf.filter(pl.col('age') > 30).select('name', 'age').collect()
```

### Write a DataFrame

```python
import polars as pl
from klaw_dbase import write_dbase

df = pl.DataFrame({'name': ['Alice', 'Bob'], 'age': [25, 30]})
write_dbase(df, 'output.dbf', overwrite=True)
```

## DATASUS .DBC Files

The primary use case for this library is handling DATASUS files from Brazil's public health system—both compressed (.DBC) and uncompressed (.DBF).

### Read a compressed .DBC file

```python
from klaw_dbase import read_dbase

# Auto-detected by .dbc extension
df = read_dbase('RDPA2402.dbc')

# Or explicitly
df = read_dbase('RDPA2402.dbc', compressed=True)
```

### Read multiple DATASUS files

```python
from klaw_dbase import read_dbase

files = [
    'RDPA2401.dbc',
    'RDPA2402.dbc',
    'RDPA2403.dbc',
]
df = read_dbase(files)
```

### Lazy scan with glob patterns

```python
import polars as pl
from klaw_dbase import scan_dbase

lf = scan_dbase('data/RDPA24*.dbc')
summary = lf.filter(pl.col('IDADE') >= 65).group_by('UF_RESID').agg(pl.len().alias('count')).collect()
```

### Get record count without loading data

```python
from klaw_dbase import get_dbase_record_count

n = get_dbase_record_count('RDPA2402.dbc')
```

## API Reference

### `read_dbase`

```python
read_dbase(
    sources,                    # path, list of paths, directory, or glob pattern
    *,
    columns=None,               # columns to select (names or indices)
    n_rows=None,                # limit number of rows
    row_index_name=None,        # add row index column
    row_index_offset=0,
    rechunk=False,
    batch_size=8192,
    n_workers=None,             # parallel readers (default: all CPUs)
    glob=True,
    encoding="cp1252",
    character_trim="begin_end",
    skip_deleted=True,
    validate_schema=True,
    compressed=False,           # auto-detected for .dbc files
) -> pl.DataFrame
```

### `scan_dbase`

```python
scan_dbase(
    sources,
    *,
    batch_size=8192,
    n_workers=None,
    single_col_name=None,
    encoding="cp1252",
    character_trim="begin_end",
    skip_deleted=True,
    validate_schema=True,
    compressed=False,
    glob=True,
    progress=False,
) -> pl.LazyFrame
```

### `write_dbase`

```python
write_dbase(
    df,                         # polars DataFrame
    dest,                       # path or file-like object
    *,
    batch_size=None,
    encoding="cp1252",
    overwrite=False,
) -> None
```

### `get_dbase_record_count`

```python
get_dbase_record_count(path) -> int
```

## Encodings

Common encodings for dBase files:

| Encoding      | Use case                                      |
| ------------- | --------------------------------------------- |
| `cp1252`      | Windows Latin-1 (default, common for DATASUS) |
| `utf-8`       | Unicode                                       |
| `iso-8859-1`  | Latin-1                                       |
| `iso-8859-15` | Latin-9 (Euro sign)                           |

## Error Handling

| Exception        | When raised                                |
| ---------------- | ------------------------------------------ |
| `DbaseError`     | Corrupted or invalid dBase file            |
| `DbcError`       | Compression-specific problems              |
| `EmptySources`   | No input files or empty DataFrame on write |
| `SchemaMismatch` | Multiple files with incompatible schemas   |
| `EncodingError`  | Invalid or unsupported encoding            |

```python
from klaw_dbase import DbaseError, DbcError, EmptySources

try:
    df = read_dbase('corrupted.dbf')
except DbaseError as e:
    print(f'Failed to read: {e}')
```

## License

MIT
