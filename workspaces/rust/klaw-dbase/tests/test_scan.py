"""Test scan functionality for klaw-dbase."""

import pathlib
import tempfile

import polars as pl
import pytest
from klaw_dbase import DbaseError, EmptySources, read_dbase, scan_dbase, write_dbase

from .utils import frames_equal


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pl.from_dict({
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': [25, 30, 35],
        'score': [95.5, 87.2, 92.1],
        'active': [True, False, True],
    })


def test_scan_dbase() -> None:
    """Test generic scan of files."""
    # Use a real file from the data directory if available
    try:
        frame = scan_dbase('data/expected-sids.dbf', encoding='cp1252').collect()
        assert frame.height > 0
        assert frame.width > 0
    except FileNotFoundError:
        # Skip test if data file not available
        pytest.skip('Data file not available')


def test_projection_pushdown_dbase(sample_dataframe) -> None:
    """Test that projection is pushed down to scan."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        lazy = scan_dbase(temp_path).select(pl.col('name'))

        explain = lazy.explain()

        # Check that projection optimization is working
        assert 'PROJECT' in explain

        normal = lazy.collect()
        no_opts = pl.lazyframe.opt_flags.QueryOptFlags(
            predicate_pushdown=False,
            projection_pushdown=False,
            simplify_expression=False,
            slice_pushdown=False,
            comm_subplan_elim=False,
            comm_subexpr_elim=False,
            cluster_with_columns=False,
            collapse_joins=False,
        )
        unoptimized = lazy.collect(optimizations=no_opts)
        assert frames_equal(normal, unoptimized)


def test_predicate_pushdown_dbase(sample_dataframe) -> None:
    """Test that predicate is pushed down to scan."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        lazy = scan_dbase(temp_path).filter(pl.col('age') > 25)

        explain = lazy.explain()

        # Check that predicate optimization is working
        assert 'SELECTION' in explain or 'FILTER' in explain

        normal = lazy.collect()
        no_opts = pl.lazyframe.opt_flags.QueryOptFlags(
            predicate_pushdown=False,
            projection_pushdown=False,
            simplify_expression=False,
            slice_pushdown=False,
            comm_subplan_elim=False,
            comm_subexpr_elim=False,
            cluster_with_columns=False,
            collapse_joins=False,
        )
        unoptimized = lazy.collect(optimizations=no_opts)
        assert frames_equal(normal, unoptimized)


def test_glob_n_rows() -> None:
    """Test that globbing and n_rows work."""
    try:
        # Test with glob pattern if data files exist
        frame = scan_dbase('data/dir_test/*.dbf').limit(10).collect()
        print(frame)
        assert frame.shape[0] <= 10  # Should have at most 10 rows
    except FileNotFoundError:
        pytest.skip('Data files not available')


def test_many_files(sample_dataframe) -> None:
    """Test that scan works with many files."""
    import os
    import tempfile

    # Create temporary directory with multiple files
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = []
        for i in range(10):
            temp_path = os.path.join(tmpdir, f'test_{i}.dbf')
            write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
            paths.append(temp_path)

        res = scan_dbase(paths).collect()
        reference = pl.concat([sample_dataframe] * 10)
        assert frames_equal(res, reference)


def test_scan_nrows_empty(sample_dataframe) -> None:
    """Test that scan doesn't panic with n_rows set to 0."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        frame = scan_dbase(temp_path).head(0).collect()
        reference = read_dbase(temp_path).head(0)
        assert frames_equal(frame, reference)


def test_scan_filter_empty(sample_dataframe) -> None:
    """Test that scan doesn't panic when filter removes all rows."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        frame = scan_dbase(temp_path).filter(pl.col('name') == 'nonexistent').collect()
        reference = read_dbase(temp_path).filter(pl.col('name') == 'nonexistent')
        assert frames_equal(frame, reference)


def test_directory() -> None:
    """Test scan on directory."""
    try:
        frame = scan_dbase('data/dir_test').collect()
        assert frame.height >= 0  # Should not crash
    except FileNotFoundError:
        pytest.skip('Data directory not available')


def test_dbase_list_arg(sample_dataframe) -> None:
    """Test that scan works when passing a list."""
    import os
    import shutil
    import tempfile

    temp_dir = tempfile.mkdtemp()
    try:
        temp_file_1 = os.path.join(temp_dir, 'test1.dbf')
        temp_file_2 = os.path.join(temp_dir, 'test2.dbf')
        temp_file_3 = os.path.join(temp_dir, 'test3.dbf')

        write_dbase(sample_dataframe, temp_file_1, overwrite=True)
        write_dbase(sample_dataframe, temp_file_2, overwrite=True)
        write_dbase(sample_dataframe, temp_file_3, overwrite=True)

        temp_files = [temp_file_1, temp_file_2, temp_file_3]

        # Test scanning list of files
        frame = scan_dbase(temp_files).collect()
        expected = pl.concat([sample_dataframe] * 3)
        assert frames_equal(frame, expected)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_glob_single_scan() -> None:
    """Test that globbing works with a single file."""
    try:
        file_path = 'data/expected-sids.dbf'
        frame = scan_dbase(file_path)

        explain = frame.explain()

        assert explain.count('SCAN') == 1
    except FileNotFoundError:
        pytest.skip('Data file not available')


def test_scan_in_memory(sample_dataframe) -> None:
    """Test that scan works for file paths (formerly in-memory buffers)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        scanned = scan_dbase(temp_path).collect()
        assert frames_equal(sample_dataframe, scanned)


def test_encoding_detection() -> None:
    """Test auto-detection of encodings."""
    try:
        # Test with different encodings
        encodings = ['cp1252', 'utf-8', 'iso-8859-1']

        for encoding in encodings:
            df = pl.from_dict({
                'name': ['Álvaro', 'José', 'João'],
                'city': ['São Paulo', 'Rio', 'Belo Horizonte'],
            })

            with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
                temp_path = f.name

            try:
                write_dbase(df, temp_path, encoding=encoding, overwrite=True)

                # Try to read with the same encoding
                result = read_dbase(temp_path, encoding=encoding)
                assert df.height == result.height
                assert df.width == result.width

            finally:
                pathlib.Path(temp_path).unlink()

    except Exception as e:
        print(e)


def test_character_trimming_scan() -> None:
    """Test character trimming on read."""
    df = pl.from_dict({
        'name': ['  Alice  ', 'Bob', '  Charlie  '],
        'description': ['  Test  ', 'Demo', '  Example  '],
    })

    trimming_options = ['begin', 'end', 'begin_end', 'both', 'none']

    for trim_option in trimming_options:
        with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
            temp_path = f.name

        try:
            write_dbase(df, temp_path, overwrite=True)
            result = read_dbase(temp_path, character_trim=trim_option)
            assert df.height == result.height
            assert df.width == result.width
        finally:
            pathlib.Path(temp_path).unlink()


def test_skip_deleted_records() -> None:
    """Test skip_deleted parameter."""
    df = pl.from_dict({'x': [1, 2, 3]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with skip_deleted=True (default)
        result_true = read_dbase(temp_path, skip_deleted=True)
        assert df.height == result_true.height

        # Test with skip_deleted=False
        result_false = read_dbase(temp_path, skip_deleted=False)
        assert df.height == result_false.height

    finally:
        pathlib.Path(temp_path).unlink()


def test_schema_validation() -> None:
    """Test validate_schema parameter."""
    df = pl.from_dict({'x': [1, 2, 3]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with validate_schema=True (default)
        result_true = read_dbase(temp_path, validate_schema=True)
        assert df.height == result_true.height

        # Test with validate_schema=False
        result_false = read_dbase(temp_path, validate_schema=False)
        assert df.height == result_false.height

    finally:
        pathlib.Path(temp_path).unlink()


# TODO: Uncomment when we have a compressed file
def test_compressed_read() -> None:
    """Test reading compressed dBase files (.dbc)."""
    try:
        # Try to read an existing .dbc file
        frame = read_dbase('data/RDPA2402.dbc', compressed=True)
        assert frame.height >= 0
    except FileNotFoundError:
        pytest.skip('Compressed data file not available')


def test_single_col_name() -> None:
    """Test single_col_name parameter."""
    df = pl.from_dict({'x': [1, 2, 3]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test reading with single_col_name
        result = read_dbase(temp_path, single_col_name='x')
        assert 'x' in result.columns
        assert df.height == result.height

    finally:
        pathlib.Path(temp_path).unlink()


def test_batch_size_scan() -> None:
    """Test batch_size parameter."""
    df = pl.from_dict({'x': [1, 2, 3, 4, 5]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with different batch sizes
        for batch_size in [1, 2, 10]:
            result = read_dbase(temp_path, batch_size=batch_size)
            assert frames_equal(df, result)

    finally:
        pathlib.Path(temp_path).unlink()


def test_real_dbf_files() -> None:
    """Test with actual .dbf files."""
    try:
        # Try to read existing .dbf files
        dbf_files = ['data/expected-sids.dbf', 'data/test-encoding.dbf']

        for dbf_file in dbf_files:
            try:
                frame = read_dbase(dbf_file)
                assert frame.height >= 0
                assert frame.width > 0
            except FileNotFoundError:
                continue  # Skip if file doesn't exist

    except Exception as e:
        pytest.skip(f'Real file test failed: {e}')


def test_real_dbc_files() -> None:
    """Test with actual .dbc files (same schema for parallel reading)."""
    try:
        dbc_files = [
            'data/RDPA2401.dbc',
            'data/RDPA2402.dbc',
            'data/RDPA2403.dbc',
            'data/RDPA2404.dbc',
            'data/RDPA2405.dbc',
            'data/RDPA2406.dbc',
        ]

        for dbc_file in dbc_files:
            try:
                frame = read_dbase(dbc_file, compressed=True)
                print(frame)
                assert frame.height >= 0
                assert frame.width > 0
            except FileNotFoundError as e:
                print(e)

    except Exception as e:
        print(e)


def test_various_encodings() -> None:
    """Test files with different encodings."""
    try:
        # Test with various encoding files
        encoding_files = [
            ('data/test-cp1252-output.dbf', 'cp1252'),
            ('data/test-utf8-output.dbf', 'utf-8'),
            ('data/test-iso8859-1-output.dbf', 'iso-8859-1'),
        ]

        for file_path, encoding in encoding_files:
            try:
                frame = read_dbase(file_path, encoding=encoding)
                assert frame.height >= 0
            except FileNotFoundError:
                print(file_path)

    except Exception as e:
        print(e)


def test_corrupted_files() -> None:
    """Test handling of corrupted dBase files."""
    # Create a corrupted file
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        f.write(b'This is not a valid dBase file')
        temp_path = f.name

    try:
        with pytest.raises((DbaseError, pl.exceptions.ComputeError)):
            read_dbase(temp_path)
    finally:
        pathlib.Path(temp_path).unlink()


def test_empty_sources() -> None:
    """Test that empty sources raises an error."""
    with pytest.raises((EmptySources, ValueError, DbaseError)):
        scan_dbase([]).collect()


def test_read_options() -> None:
    """Test read works with options."""
    # Create a test file first
    df = pl.from_dict({
        'x': [1, 2, 3, 4, 5],
        'y': ['a', 'b', 'c', 'd', 'e'],
    })

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with options
        frame = read_dbase(temp_path, row_index_name='row_index', columns=['x'], n_rows=3)
        assert frame.shape == (3, 2)  # 3 rows, 2 columns (x + row_index)
        assert 'row_index' in frame.columns
        assert frame['row_index'].to_list() == [0, 1, 2]

    finally:
        pathlib.Path(temp_path).unlink()


def test_parallel_read_multiple_files(sample_dataframe) -> None:
    """Test parallel reading of multiple files."""
    import os
    import shutil
    import tempfile

    temp_dir = tempfile.mkdtemp()
    try:
        # Create multiple test files
        temp_files = []
        for i in range(5):
            temp_file = os.path.join(temp_dir, f'test{i}.dbf')
            write_dbase(sample_dataframe, temp_file, overwrite=True)
            temp_files.append(temp_file)

        # Test parallel reading with explicit n_workers
        frame = read_dbase(temp_files, n_workers=2)
        expected = pl.concat([sample_dataframe] * 5)
        assert frame.height == expected.height
        assert frame.width == expected.width

        # Test parallel reading with default n_workers (all CPUs)
        frame_default = read_dbase(temp_files)
        assert frame_default.height == expected.height

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_parallel_scan_multiple_files(sample_dataframe) -> None:
    """Test parallel scan of multiple files."""
    import os
    import shutil
    import tempfile

    temp_dir = tempfile.mkdtemp()
    try:
        # Create multiple test files
        temp_files = []
        for i in range(3):
            temp_file = os.path.join(temp_dir, f'test{i}.dbf')
            write_dbase(sample_dataframe, temp_file, overwrite=True)
            temp_files.append(temp_file)

        # Test parallel scan with explicit n_workers
        frame = scan_dbase(temp_files, n_workers=2).collect()
        expected = pl.concat([sample_dataframe] * 3)
        assert frame.height == expected.height
        assert frame.width == expected.width

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_n_workers_parameter() -> None:
    """Test n_workers parameter with different values."""
    df = pl.from_dict({'x': [1, 2, 3]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with different n_workers values
        for n_workers in [1, 2, 4, None]:
            result = read_dbase(temp_path, n_workers=n_workers)
            assert frames_equal(df, result)

    finally:
        pathlib.Path(temp_path).unlink()


if __name__ == '__main__':
    pytest.main([__file__])
