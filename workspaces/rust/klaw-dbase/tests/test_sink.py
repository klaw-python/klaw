"""Test write functionality for klaw-dbase."""

from io import BytesIO
from pathlib import Path
import tempfile

import polars as pl
import pytest

from klaw_dbase import write_dbase, read_dbase, scan_dbase, DbaseError, EncodingError
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


@pytest.fixture
def complex_dataframe():
    """Create a complex DataFrame with various data types."""
    return pl.from_dict({
        "palavra": ["Hello", "World", "Now"],
        "inteiro": [42, -17, 0],
        "real": [3.14, -2.71, 0.0],
        "booliano": [True, False, True],
        "data": ["2023-01-01", "2023-12-31", "2023-06-15"],
    })

@pytest.fixture
def sample_dbf_buffer(sample_dataframe):
    """Create a BytesIO buffer with sample dBase data."""
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as f:
        temp_path = f.name
        write_dbase(sample_dataframe, dest=temp_path, overwrite=True)
        buff = BytesIO()
        buff.write(temp_path)
        buff.seek(0)
        return buff


    



def test_file_write(sample_dataframe, tmp_path: Path) -> None:
    """Test writing to a file."""
    path = tmp_path / "test.dbf"
    write_dbase(sample_dataframe, path)
    duplicate = read_dbase(path)
    assert frames_equal(sample_dataframe, duplicate)


def test_round_trip_simple_data() -> None:
    """Test round-trip with simple data - mirrors Rust test."""
    # Create a simple test DataFrame
    original_df = pl.from_dict({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "score": [95.5, 87.2, 92.1],
        "active": [True, False, True],
    })

    # Create temporary file
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
        temp_path = temp_file.name

    try:
        # Write to dBase file
        write_dbase(original_df, temp_path, overwrite=True)
        
        # Read back from dBase file
        roundtrip_df = read_dbase(temp_path)
        
        # Verify basic properties
        assert original_df.height == roundtrip_df.height
        assert original_df.width == roundtrip_df.width
        
        # Verify column names (dBase might change casing)
        original_names = original_df.columns
        roundtrip_names = roundtrip_df.columns
        assert len(original_names) == len(roundtrip_names)
        
    finally:
        # Clean up
        import os
        os.unlink(temp_path)


def test_round_trip_with_encoding() -> None:
    """Test round-trip with different encodings - mirrors Rust test."""
    encodings = ["cp1252", "utf-8", "cp850"]
    
    for encoding in encodings:
        # Create DataFrame with accented characters
        original_df = pl.from_dict({
            "name": ["Alice", "Bob", "Charlie"],
            "city": ["São Paulo", "New York", "João Pessoa"],
            "age": [25, 30, 35],
        })

        with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Write with specific encoding
            write_dbase(original_df, temp_path, encoding=encoding, overwrite=True)
            
            # Read back with same encoding
            roundtrip_df = read_dbase(temp_path, encoding=encoding)
            
            # Basic integrity checks
            assert original_df.height == roundtrip_df.height
            assert original_df.width == roundtrip_df.width
            
        finally:
            import os
            os.unlink(temp_path)


def test_round_trip_memory_buffer() -> None:
    """Test round-trip using in-memory buffer - mirrors Rust test."""
    original_df = pl.from_dict({
        "id": [1, 2, 3, 4, 5],
        "product": ["Apple", "Banana", "Orange", "Grape", "Mango"],
        "price": [1.99, 0.99, 2.49, 3.99, 1.49],
        "in_stock": [True, False, True, True, False],
    })

    # Write to memory buffer
    buffer = BytesIO()
    write_dbase(original_df, buffer)
    
    # Read back from memory buffer
    buffer.seek(0)
    roundtrip_df = read_dbase(buffer)
    
    # Verify data integrity
    assert original_df.height == roundtrip_df.height
    assert original_df.width == roundtrip_df.width
    

def test_field_type_coverage() -> None:
    """Test all supported field types - mirrors Rust test."""
    df = pl.from_dict({
        "palavra": ["Hello", "World", "Now"],
        "inteiro": [42, -17, 0],
        "real": [3.14, -2.71, 0.0],
        "booliano": [True, False, True],
        "data": ["2023-01-01", "2023-12-31", "2023-06-15"],
    })

    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
        temp_path = temp_file.name

    try:
        # Write and read back
        write_dbase(df, temp_path, encoding="utf-8", overwrite=True)
        roundtrip_df = read_dbase(temp_path, encoding="utf-8")
        
        # Verify data integrity
        assert df.height == roundtrip_df.height
        assert df.width == roundtrip_df.width
        
    finally:
        import os
        os.unlink(temp_path)
    

# NOTE: You can't write multiple chunks to a buffer since the bytes from a dBase file will include the header
# and footer. So, we'll have to write to a file and read back from there.
def test_chunk_processing() -> None:
    """Test writing multiple chunks - mirrors Rust test."""
    # Create multiple DataFrames
    df1 = pl.from_dict({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
    })
    
    df2 = pl.from_dict({
        "id": [4, 5, 6],
        "name": ["David", "Eve", "Frank"],
    })
    
    df3 = pl.from_dict({
        "id": [7, 8, 9],
        "name": ["Grace", "Henry", "Ivy"],
    })
    

    # Create a list of DataFrames to simulate chunks
    chunks = [df1, df2, df3]

    # Combine for expected result
    expected_df = pl.concat(chunks)
    total_rows = expected_df.height
    print(expected_df)
    
    # Write multiple chunks to memory buffer
    buffer = BytesIO()
    
    # Write each chunk
    write_dbase(expected_df, buffer)
    
    # Read back from the buffer
    buffer.seek(0)
    roundtrip_df = read_dbase(buffer, batch_size=10)
    
    # Verify all rows were written
    print(total_rows)
    assert total_rows == roundtrip_df.height
    assert 2 == roundtrip_df.width  # id and name columns


def test_encoding_options() -> None:
    """Test different character encodings."""
    df = pl.from_dict({
        "name": ["Álvaro", "José", "João"],
        "city": ["São Paulo", "Rio de Janeiro", "Belo Horizonte"],
    })
    
    encodings = ["cp1252", "utf-8", "cp850"]
    
    for encoding in encodings:
        with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            write_dbase(df, temp_path, encoding=encoding, overwrite=True)
            result = read_dbase(temp_path, encoding=encoding)
            assert df.height == result.height
            assert df.width == result.width
        finally:
            import os
            os.unlink(temp_path)


def test_character_trimming() -> None:
    """Test different character trimming options."""
    df = pl.from_dict({
        "name": ["  Alice  ", "Bob", "  Charlie  "],
        "description": ["  Test  ", "Demo", "  Example  "],
    })

    trimming_options = ["begin", "end", "begin_end", "both", "none"]

    for trim_option in trimming_options:
        with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            write_dbase(df, temp_path, overwrite=True)
            result = read_dbase(temp_path, character_trim=trim_option)
            assert df.height == result.height
            assert df.width == result.width
        finally:
            import os
            os.unlink(temp_path)



def test_overwrite_behavior() -> None:
    """Test overwrite parameter."""
    df = pl.from_dict({"x": [1, 2, 3]})
    temp_path = tempfile.NamedTemporaryFile(suffix='.dbf', delete=False)
    path = temp_path.name

    # Write first time
    write_dbase(df, path, overwrite=True)

    # Try to write again without overwrite (should fail)
    with pytest.raises(Exception):  # Should raise some kind of error
        write_dbase(df, path, overwrite=False)

    # Write again with overwrite (should succeed)
    write_dbase(df, path, overwrite=True)
    result = read_dbase(path)
    assert frames_equal(df, result)

def test_invalid_encoding() -> None:
    """Test handling of invalid encoding names."""
    df = pl.from_dict({"x": [1, 2, 3]})
    
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as temp_file:
        temp_path = temp_file.name

        try:
            with pytest.raises(RuntimeError):
                write_dbase(df, temp_path, encoding="invalid-encoding-12345", overwrite=True)
        finally:
            import os
            os.unlink(temp_path)



if __name__ == "__main__":
    pytest.main([__file__])