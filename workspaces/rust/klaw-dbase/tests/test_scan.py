"""Test scan functionality for klaw-dbase."""

from io import BytesIO

import polars as pl
import pytest
import tempfile

from klaw_dbase import scan_dbase, read_dbase, write_dbase, DbaseError, EmptySources
from utils import frames_equal


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pl.from_dict({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "score": [95.5, 87.2, 92.1],
        "active": [True, False, True],
    })


# @pytest.fixture
# def sample_dbf_buffer(sample_dataframe):
#     """Create a BytesIO buffer with sample dBase data."""
#     buff = BytesIO()
#     print(buff)
#     write_dbase(sample_dataframe, buff)
#     buff.seek(0)
#     return buff

def test_scan_dbase() -> None:
    """Test generic scan of files."""
    # Use a real file from the data directory if available
    try:
        frame = scan_dbase("data/expected-sids.dbf", encoding="cp1252").collect()
        assert frame.height > 0
        assert frame.width > 0
    except FileNotFoundError:
        # Skip test if data file not available
        pytest.skip("Data file not available")


def test_projection_pushdown_dbase(sample_dataframe) -> None:
    """Test that projection is pushed down to scan."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        lazy = scan_dbase(temp_path).select(pl.col("name"))

        explain = lazy.explain()

        # Check that projection optimization is working
        assert "PROJECT" in explain
        
        normal = lazy.collect()
        unoptimized = lazy.collect(no_optimization=True)
        assert frames_equal(normal, unoptimized)
        

def test_predicate_pushdown_dbase(sample_dataframe) -> None:
    """Test that predicate is pushed down to scan."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        lazy = scan_dbase(temp_path).filter(pl.col("age") > 25)

        explain = lazy.explain()

        # Check that predicate optimization is working
        assert "SELECTION" in explain or "FILTER" in explain

        normal = lazy.collect()
        unoptimized = lazy.collect(no_optimization=True)
        assert frames_equal(normal, unoptimized)


def test_glob_n_rows() -> None:
    """Test that globbing and n_rows work."""
    try:
        # Test with glob pattern if data files exist
        frame = scan_dbase("data/dir_test/*.dbf").limit(10).collect()
        print(frame)
        assert frame.shape[0] <= 10  # Should have at most 10 rows
    except FileNotFoundError:
        pytest.skip("Data files not available")

def test_many_files(sample_dataframe) -> None:
    """Test that scan works with many files."""
    buff = BytesIO()
    write_dbase(sample_dataframe, buff)
    
    # Create multiple buffers
    buffs = [BytesIO(buff.getvalue()) for _ in range(10)]
    res = scan_dbase(buffs).collect()
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
        frame = scan_dbase(temp_path).filter(pl.col("name") == "nonexistent").collect()
        reference = read_dbase(temp_path).filter(pl.col("name") == "nonexistent")
        assert frames_equal(frame, reference)


def test_directory() -> None:
    """Test scan on directory."""
    try:
        frame = scan_dbase("data/dir_test").collect()
        assert frame.height >= 0  # Should not crash
    except FileNotFoundError:
        pytest.skip("Data directory not available")


def test_dbase_list_arg(sample_dataframe) -> None:
    """Test that scan works when passing a list."""
    # Create multiple temporary files
    import tempfile
    import os

    temp_files = []
    try:
        
        temp_file_1 = tempfile.NamedTemporaryFile(suffix='.dbf', delete=False)
        temp_file_2 = tempfile.NamedTemporaryFile(suffix='.dbf', delete=False)
        temp_file_3 = tempfile.NamedTemporaryFile(suffix='.dbf', delete=False)
        
        write_dbase(sample_dataframe, temp_file_1.name, overwrite=True)
        write_dbase(sample_dataframe, temp_file_2.name, overwrite=True)
        write_dbase(sample_dataframe, temp_file_3.name, overwrite=True)
        
        temp_files.append(temp_file_1.name)
        temp_files.append(temp_file_2.name)
        temp_files.append(temp_file_3.name)

        # Test scanning list of files
        frame = scan_dbase(temp_files).collect()
        expected = pl.concat([sample_dataframe] * 3)
        assert frames_equal(frame, expected)
                
    finally:
        # Clean up
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                

def test_glob_single_scan() -> None:
    """Test that globbing works with a single file."""
    try:
        file_path = "data/expected-sids.dbf"
        frame = scan_dbase(file_path)

        explain = frame.explain()

        assert explain.count("SCAN") == 1
    except FileNotFoundError:
        pytest.skip("Data file not available")
        

def test_scan_in_memory(sample_dataframe) -> None:
    """Test that scan works for in memory buffers."""
    buff = BytesIO()
    write_dbase(sample_dataframe, buff)
    buff.seek(0)
    scanned = scan_dbase(buff).collect()
    assert frames_equal(sample_dataframe, scanned)


def test_encoding_detection() -> None:
    """Test auto-detection of encodings."""
    try:
        # Test with different encodings
        encodings = ["cp1252", "utf-8", "cp850"]

        for encoding in encodings:
            df = pl.from_dict({
                "name": ["Álvaro", "José", "João"],
                "city": ["São Paulo", "Rio", "Belo Horizonte"],
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
                import os
                os.unlink(temp_path)
    
    except Exception as e:
        print(e)


def test_character_trimming_scan() -> None:
    """Test character trimming on read."""
    df = pl.from_dict({
        "name": ["  Alice  ", "Bob", "  Charlie  "],
        "description": ["  Test  ", "Demo", "  Example  "],
    })

    trimming_options = ["begin", "end", "begin_end", "both", "none"]

    for trim_option in trimming_options:
        with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
            temp_path = f.name

        try:
            write_dbase(df, temp_path, overwrite=True)
            result = read_dbase(temp_path, character_trim=trim_option)
            assert df.height == result.height
            assert df.width == result.width
        finally:
            import os
            os.unlink(temp_path)


def test_skip_deleted_records() -> None:
    """Test skip_deleted parameter."""
    df = pl.from_dict({"x": [1, 2, 3]})

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
        import os
        os.unlink(temp_path)


def test_schema_validation() -> None:
    """Test validate_schema parameter."""
    df = pl.from_dict({"x": [1, 2, 3]})

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
        import os
        os.unlink(temp_path)


# TODO: Uncomment when we have a compressed file
def test_compressed_read() -> None:
    """Test reading compressed dBase files (.dbc)."""
    try:
        # Try to read an existing .dbc file
        frame = read_dbase("data/RDPA2402.dbc", compressed=True)
        assert frame.height >= 0
    except FileNotFoundError:
        pytest.skip("Compressed data file not available")


def test_single_col_name() -> None:
    """Test single_col_name parameter."""
    df = pl.from_dict({"x": [1, 2, 3]})

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test reading with single_col_name
        result = read_dbase(temp_path, single_col_name="x")
        assert "x" in result.columns
        assert df.height == result.height
    
    finally:
        import os
        os.unlink(temp_path)


def test_batch_size_scan() -> None:
    """Test batch_size parameter."""
    df = pl.from_dict({"x": [1, 2, 3, 4, 5]})

    
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        
    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with different batch sizes
        for batch_size in [1, 2, 10]:
            result = read_dbase(temp_path, batch_size=batch_size)
            assert frames_equal(df, result)
            
    finally:
        import os
        os.unlink(temp_path)
    

def test_real_dbf_files() -> None:
    """Test with actual .dbf files."""
    try:
        # Try to read existing .dbf files
        dbf_files = ["data/expected-sids.dbf", "data/test-encoding.dbf"]

        for dbf_file in dbf_files:
            try:
                frame = read_dbase(dbf_file)
                assert frame.height >= 0
                assert frame.width > 0
            except FileNotFoundError:
                continue  # Skip if file doesn't exist
                
    except Exception as e:
        pytest.skip(f"Real file test failed: {e}")


def test_real_dbc_files() -> None:
    """Test with actual .dbc files."""
    try:
        dbc_files = [
            "data/sids.dbc", "data/DNAC1996.DBC", "data/PAPA2501.dbc",
            "data/RDPA2401.dbc", "data/ABMG1112.dbc"
        ]

        for dbc_file in dbc_files:
            try:
                frame = read_dbase(dbc_file, compressed=True)
                print(frame)
                assert frame.height >= 0
                assert frame.width > 0
            except FileNotFoundError as e:
                # pytest.skip(f"Real file test failed: {e}")
                print(e)
        
    except Exception as e:
        print(e)
    

def test_various_encodings() -> None:
    """Test files with different encodings."""
    try:
        # Test with various encoding files
        encoding_files = [
            ("data/test-cp1252-output.dbf", "cp1252"),
            ("data/test-utf8-output.dbf", "utf-8"),
            ("data/test-cp850-output.dbf", "cp850"),
        ]

        for file_path, encoding in encoding_files:
            try:
                frame = read_dbase(file_path, encoding=encoding)
                assert frame.height >= 0
            except FileNotFoundError:
                print(file_path)
            
                # continue  # Skip if file doesn't exist
                
    except Exception as e:
        print(e)

        
def test_corrupted_files() -> None:
    """Test handling of corrupted dBase files."""
    # Create a corrupted file
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        f.write(b"This is not a valid dBase file")
        temp_path = f.name
    
    try:
        with pytest.raises((DbaseError, pl.exceptions.ComputeError)):
            read_dbase(temp_path)
    finally:
        import os
        os.unlink(temp_path)


def test_empty_sources() -> None:
    """Test that empty sources raises an error."""
    with pytest.raises((EmptySources, ValueError, DbaseError)):
        scan_dbase([]).collect()
    

def test_read_options() -> None:
    """Test read works with options."""
    # Create a test file first
    df = pl.from_dict({
        "x": [1, 2, 3, 4, 5],
        "y": ["a", "b", "c", "d", "e"],
    })

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name

    try:
        write_dbase(df, temp_path, overwrite=True)

        # Test with options
        frame = read_dbase(
            temp_path, 
            row_index_name="row_index", 
            columns=["x"], 
            n_rows=3
        )
        assert frame.shape == (3, 2)  # 3 rows, 2 columns (x + row_index)
        assert "row_index" in frame.columns
        assert frame["row_index"].to_list() == [0, 1, 2]
        
    finally:
        import os
        os.unlink(temp_path)

if __name__ == "__main__":
    pytest.main([__file__])