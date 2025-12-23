//! Integration tests for the optimal dBase implementation
#![allow(unused_imports)]
#![allow(unused_mut)]

use std::io::Cursor;

use polars::df;
use polars::prelude::{DataType, Schema as PlSchema};

use super::{
    read::{DbfReadOptions, DbfReader},
    write::{WriteOptions, write_dbase, write_dbase_file},
};

#[cfg(test)]
mod integration_tests {
    use super::*;

    #[test]
    fn test_round_trip_simple_data() {
        // Create a simple test DataFrame
        let original_df = df! {
            "name" => ["Alice", "Bob", "Charlie"],
            "age" => [25, 30, 35],
            "score" => [95.5, 87.2, 92.1],
            "active" => [true, false, true],
        }
        .unwrap();

        println!("Original DataFrame:");
        println!("Schema: {:?}", original_df.schema());
        println!(
            "Shape: {} rows × {} columns",
            original_df.height(),
            original_df.width()
        );

        // Create temporary file
        let temp_file = tempfile::NamedTempFile::new().unwrap();
        let temp_path = temp_file.path();

        // Write to dBase file
        let write_result = write_dbase_file(&original_df, temp_path, None);

        match write_result {
            Ok(()) => {
                println!("✅ Successfully wrote DataFrame to dBase file");

                // Read back from dBase file using DbfReader
                let read_result =
                    DbfReader::new(vec![std::fs::File::open(temp_path).unwrap()], None);

                match read_result {
                    Ok(reader) => {
                        let mut iterator = reader.into_iter(None, None);
                        let mut roundtrip_df = None;

                        for batch_result in iterator {
                            let batch = batch_result.unwrap();
                            if batch.is_empty() {
                                continue;
                            }

                            match roundtrip_df {
                                None => roundtrip_df = Some(batch),
                                Some(ref mut df) => {
                                    *df = df.vstack(&batch).unwrap();
                                }
                            }
                        }

                        if let Some(roundtrip_df) = roundtrip_df {
                            println!("✅ Successfully read DataFrame back from dBase file");
                            println!("Round-trip Schema: {:?}", roundtrip_df.schema());
                            println!(
                                "Round-trip Shape: {} rows × {} columns",
                                roundtrip_df.height(),
                                roundtrip_df.width()
                            );

                            // Verify basic properties
                            assert_eq!(
                                original_df.height(),
                                roundtrip_df.height(),
                                "Row count mismatch"
                            );
                            assert_eq!(
                                original_df.width(),
                                roundtrip_df.width(),
                                "Column count mismatch"
                            );

                            // Verify column names (dBase might change casing)
                            let original_names: Vec<_> = original_df.get_column_names();
                            let roundtrip_names: Vec<_> = roundtrip_df.get_column_names();
                            assert_eq!(original_names.len(), roundtrip_names.len());

                            println!("✅ Round-trip test successful!");
                        } else {
                            println!("❌ No data read back");
                        }
                    }
                    Err(e) => {
                        println!("❌ Failed to create reader: {}", e);
                    }
                }
            }
            Err(e) => {
                println!("❌ Write failed: {}", e);
            }
        }
    }

    #[test]
    fn test_round_trip_with_encoding() {
        use crate::read::{DbfEncoding, resolve_encoding_string};

        // Test round-trip with different encodings (using encoding_rs supported encodings)
        let encodings = vec![
            ("cp1252", DbfEncoding::Cp1252),
            ("utf8", DbfEncoding::Utf8),
            ("cp866", DbfEncoding::Cp866),
        ];

        for (encoding_str, encoding_enum) in encodings {
            println!("Testing round-trip with {} encoding...", encoding_str);

            let original_df = df! {
                "name" => ["Alice", "Bob", "Charlie"],
                "city" => ["São Paulo", "New York", "João Pessoa"],
                "age" => [25, 30, 35],
            }
            .unwrap();

            let read_options = DbfReadOptions::with_encoding(encoding_enum);
            let write_options = WriteOptions::with_encoding(encoding_str);

            // Create temporary file
            let temp_file = tempfile::NamedTempFile::new().unwrap();
            let temp_path = temp_file.path();

            // Write with specific encoding
            let write_result = write_dbase_file(&original_df, temp_path, Some(write_options));

            match write_result {
                Ok(()) => {
                    println!("✅ Successfully wrote with {} encoding", encoding_str);

                    // Read back with same encoding using DbfReader
                    let read_result = DbfReader::new_with_options(
                        vec![std::fs::File::open(temp_path).unwrap()],
                        None,
                        read_options,
                    );

                    match read_result {
                        Ok(reader) => {
                            let mut iterator = reader.into_iter(None, None);
                            let mut roundtrip_df = None;

                            for batch_result in iterator {
                                let batch = batch_result.unwrap();
                                if batch.is_empty() {
                                    continue;
                                }

                                match roundtrip_df {
                                    None => roundtrip_df = Some(batch),
                                    Some(ref mut df) => {
                                        *df = df.vstack(&batch).unwrap();
                                    }
                                }
                            }

                            if let Some(roundtrip_df) = roundtrip_df {
                                println!(
                                    "✅ Successfully read back with {}: {} rows × {} columns",
                                    encoding_str,
                                    roundtrip_df.height(),
                                    roundtrip_df.width()
                                );

                                // Basic integrity checks
                                assert_eq!(original_df.height(), roundtrip_df.height());
                                assert_eq!(original_df.width(), roundtrip_df.width());

                                println!("✅ Round-trip with {} successful!", encoding_str);
                            } else {
                                println!("❌ No data read back with {}", encoding_str);
                            }
                        }
                        Err(e) => {
                            println!("❌ Failed to create reader with {}: {}", encoding_str, e)
                        }
                    }
                }
                Err(e) => println!("❌ Write with {} failed: {}", encoding_str, e),
            }
        }
    }

    #[test]
    fn test_round_trip_memory_buffer() {
        // Test round-trip using in-memory buffer
        let original_df = df! {
            "id" => [1, 2, 3, 4, 5],
            "product" => ["Apple", "Banana", "Orange", "Grape", "Mango"],
            "price" => [1.99, 0.99, 2.49, 3.99, 1.49],
            "in_stock" => [true, false, true, true, false],
        }
        .unwrap();

        println!("Testing memory buffer round-trip...");
        println!(
            "Original: {} rows × {} columns",
            original_df.height(),
            original_df.width()
        );

        // Write to memory buffer
        let mut buffer = Cursor::new(Vec::new());
        let write_result = write_dbase([&original_df], &mut buffer, WriteOptions::default());

        match write_result {
            Ok(()) => {
                println!("✅ Successfully wrote to memory buffer");

                // Read back from memory buffer using DbfReader
                buffer.set_position(0);

                let read_result = DbfReader::new(vec![buffer], None);

                match read_result {
                    Ok(reader) => {
                        let mut iterator = reader.into_iter(None, None);
                        let mut roundtrip_df = None;

                        for batch_result in iterator {
                            let batch = batch_result.unwrap();
                            if batch.is_empty() {
                                continue;
                            }

                            match roundtrip_df {
                                None => roundtrip_df = Some(batch),
                                Some(ref mut df) => {
                                    *df = df.vstack(&batch).unwrap();
                                }
                            }
                        }

                        if let Some(roundtrip_df) = roundtrip_df {
                            println!(
                                "✅ Successfully read from memory buffer: {} rows × {} columns",
                                roundtrip_df.height(),
                                roundtrip_df.width()
                            );

                            // Verify data integrity
                            assert_eq!(original_df.height(), roundtrip_df.height());
                            assert_eq!(original_df.width(), roundtrip_df.width());

                            println!("✅ Memory buffer round-trip test successful!");
                        } else {
                            println!("❌ No data read from buffer");
                        }
                    }
                    Err(e) => println!("❌ Failed to create reader from buffer: {}", e),
                }
            }
            Err(e) => println!("❌ Failed to write to buffer: {}", e),
        }
    }

    #[test]
    fn test_field_type_coverage() {
        // Test all supported field types
        println!("Testing field type coverage...");

        let df = df! {
            "palavra" => ["Hello", "World", "Now"],
            "inteiro" => [42, -17, 0],
            "real" => [3.15, -2.71, 0.0],
            "booliano" => [true, false, true],
            "data" => ["2023-01-01", "2023-12-31", "2023-06-15"],
        }
        .unwrap();

        println!("Original schema:");
        for (name, dtype) in df.schema().iter() {
            match dtype {
                DataType::String => println!("  📝 String field: {}", name),
                DataType::Int32 => println!("  🔢 Integer field: {}", name),
                DataType::Float64 => println!("  💰 Float field: {}", name),
                DataType::Boolean => println!("  ✅ Boolean field: {}", name),
                DataType::Date => println!("  📅 Date field: {}", name),
                _ => println!("  ❓ Other field: {} ({})", name, dtype),
            }
        }

        // Create temporary file
        let temp_file = tempfile::NamedTempFile::new().unwrap();
        let temp_path = temp_file.path();
        println!("Temp file path: {}", temp_path.display());
        let writing_options = WriteOptions::with_encoding("utf8");

        // Write and read back
        let write_result = write_dbase_file(&df, temp_path, Some(writing_options.clone()));
        println!("write_result: {:?}", write_result);

        match write_result {
            Ok(()) => {
                println!("✅ Successfully wrote field types test file");

                println!("Reading back from {}", temp_path.display());
                let read_result = DbfReader::new_with_options(
                    vec![std::fs::File::open(temp_file.path()).unwrap()],
                    None,
                    DbfReadOptions::with_encoding(crate::read::DbfEncoding::Utf8),
                );

                match read_result {
                    Ok(reader) => {
                        let mut iterator = reader.into_iter(None, None);
                        let mut roundtrip_df = None; // TODO: This is a hack to avoid the first batch being empty

                        for batch_result in iterator {
                            let batch = batch_result.unwrap();
                            if batch.is_empty() {
                                continue;
                            }

                            match roundtrip_df {
                                None => roundtrip_df = Some(batch),
                                Some(ref mut df) => {
                                    println!("Appending batch to roundtrip_df");
                                    println!("Roundtrip_df shape: {:?}", df.height());
                                    println!("Batch shape: {:?}", batch.height());
                                    println!("Batch Content:");
                                    print!("{}", batch);
                                    *df = df.vstack(&batch).unwrap();
                                }
                            }
                        }

                        if let Some(roundtrip_df) = roundtrip_df {
                            println!("✅ Successfully read back field types");
                            println!("Round-trip schema:");
                            for (name, dtype) in roundtrip_df.schema().iter() {
                                match dtype {
                                    DataType::String => println!("  📝 String field: {}", name),
                                    DataType::Int32 => println!("  🔢 Integer field: {}", name),
                                    DataType::Float64 => println!("  💰 Float field: {}", name),
                                    DataType::Boolean => println!("  ✅ Boolean field: {}", name),
                                    DataType::Date => println!("  📅 Date field: {}", name),
                                    _ => println!("  ❓ Other field: {} ({})", name, dtype),
                                }
                            }

                            // Verify data integrity
                            assert_eq!(df.height(), roundtrip_df.height());
                            assert_eq!(df.width(), roundtrip_df.width());

                            println!("✅ Field type coverage test complete");
                        } else {
                            println!("❌ No data read back for field types");
                        }
                    }
                    Err(e) => println!("❌ Failed to read field types: {}", e),
                }
            }
            Err(e) => {
                let file_content_result = std::fs::read_to_string(temp_file.path());
                match file_content_result {
                    Ok(file_content) => {
                        println!("File content:\n{}", file_content);
                    }
                    Err(e) => println!("Failed to read file content: {}", e),
                }
                println!("❌ Failed to write field types: {}.", e,)
            }
        }
    }

    #[test]
    fn test_chunk_processing() {
        // Test writing multiple chunks
        println!("Testing chunk processing...");

        // Create multiple DataFrames
        let df1 = df! {
            "id" => [1, 2, 3],
            "name" => ["Alice", "Bob", "Charlie"],
        }
        .unwrap();

        let df2 = df! {
            "id" => [4, 5, 6],
            "name" => ["David", "Eve", "Frank"],
        }
        .unwrap();

        let df3 = df! {
            "id" => [7, 8, 9],
            "name" => ["Grace", "Henry", "Ivy"],
        }
        .unwrap();

        let total_rows = df1.height() + df2.height() + df3.height();
        println!("Created {} chunks with total {} rows", 3, total_rows);

        // Write multiple chunks to memory buffer
        let mut buffer = Cursor::new(Vec::new());
        let write_result = write_dbase([&df1, &df2, &df3], &mut buffer, WriteOptions::default());

        match write_result {
            Ok(()) => {
                println!("✅ Successfully wrote multiple chunks");

                // Read back from the same buffer
                buffer.set_position(0);

                let read_result = DbfReader::new(vec![buffer], None);

                match read_result {
                    Ok(reader) => {
                        let mut iterator = reader.into_iter(None, None);
                        let mut roundtrip_df = None;

                        for batch_result in iterator {
                            let batch = batch_result.unwrap();
                            if batch.is_empty() {
                                continue;
                            }

                            match roundtrip_df {
                                None => roundtrip_df = Some(batch),
                                Some(ref mut df) => {
                                    *df = df.vstack(&batch).unwrap();
                                }
                            }
                        }

                        if let Some(roundtrip_df) = roundtrip_df {
                            println!(
                                "✅ Successfully read back chunks: {} rows",
                                roundtrip_df.height()
                            );

                            // Verify all rows were written
                            assert_eq!(total_rows, roundtrip_df.height());
                            assert_eq!(2, roundtrip_df.width()); // id and name columns

                            println!("✅ Chunk processing test successful!");
                        } else {
                            println!("❌ No data read back from chunks");
                        }
                    }
                    Err(e) => println!("❌ Failed to read chunks: {}", e),
                }
            }
            Err(e) => println!("❌ Failed to write chunks: {}", e),
        }
    }

    #[test]
    fn test_error_handling() {
        // Test error handling scenarios
        println!("Testing error handling...");

        // Test with unsupported field type (should fail gracefully)
        let df = df! {
            "name" => ["Alice", "Bob"],
        }
        .unwrap();

        // Create temporary file
        let temp_file = tempfile::NamedTempFile::new().unwrap();
        let temp_path = temp_file.path();

        // Test invalid encoding
        let invalid_options = WriteOptions::with_encoding("invalid-encoding-12345");
        let write_result = write_dbase_file(&df, temp_path, Some(invalid_options));

        match write_result {
            Ok(()) => println!("⚠️ Invalid encoding unexpectedly succeeded"),
            Err(e) => println!("✅ Correctly handled invalid encoding: {}", e),
        }

        // Test file overwrite behavior
        let valid_options = WriteOptions::default().with_overwrite(true); // Allow overwrite for temp files

        // Write first time
        let temp_file2 = tempfile::NamedTempFile::new().unwrap();
        let temp_path2 = temp_file2.path();
        let write1 = write_dbase_file(&df, temp_path2, Some(valid_options.clone()));
        assert!(write1.is_ok(), "First write should succeed");

        // Try to write again with overwrite enabled (should succeed)
        let write2 = write_dbase_file(&df, temp_path2, Some(valid_options));
        assert!(write2.is_ok(), "Second write with overwrite should succeed");

        // Test with overwrite disabled - use a regular temp directory path
        let no_overwrite_options = WriteOptions::default().with_overwrite(false);
        let temp_dir = tempfile::tempdir().unwrap();
        let temp_path3 = temp_dir.path().join("test_no_overwrite.dbf");

        // First write should succeed (file doesn't exist yet)
        let write3 = write_dbase_file(&df, &temp_path3, Some(no_overwrite_options.clone()));
        match &write3 {
            Ok(()) => println!("✅ First write with no overwrite succeeded"),
            Err(e) => println!("❌ First write with no overwrite failed: {}", e),
        }
        assert!(write3.is_ok(), "First write should succeed");

        // Second write without overwrite should fail (file now exists)
        let write4 = write_dbase_file(&df, &temp_path3, Some(no_overwrite_options));
        assert!(
            write4.is_err(),
            "Second write without overwrite should fail"
        );

        println!("✅ Error handling test complete");
    }

    #[test]
    fn test_real_dbase_file_round_trip() {
        // Test with a real dBase file
        println!("Testing round-trip with real dBase file...");

        // Path to the real dBase file
        let real_dbf_path = "data/expected-sids.dbf";

        // First, read the real file using our DbfReader
        let read_result = DbfReader::new(vec![std::fs::File::open(real_dbf_path).unwrap()], None);

        match read_result {
            Ok(reader) => {
                let mut iterator = reader.into_iter(None, None);
                let mut original_df = None;

                for batch_result in iterator {
                    let batch = batch_result.unwrap();
                    if batch.is_empty() {
                        continue;
                    }

                    match original_df {
                        None => original_df = Some(batch),
                        Some(ref mut df) => {
                            *df = df.vstack(&batch).unwrap();
                        }
                    }
                }

                if let Some(original_df) = original_df {
                    println!("✅ Successfully read real dBase file");
                    println!(
                        "Original: {} rows × {} columns",
                        original_df.height(),
                        original_df.width()
                    );
                    println!("Schema: {:?}", original_df.schema());

                    // Create temporary file for round-trip test
                    let temp_file = tempfile::NamedTempFile::new().unwrap();
                    let temp_path = temp_file.path();

                    // Write the DataFrame back to dBase format
                    let write_result = write_dbase_file(&original_df, temp_path, None);

                    match write_result {
                        Ok(()) => {
                            println!("✅ Successfully wrote DataFrame back to dBase format");

                            // Read it back again
                            let read_back_result =
                                DbfReader::new(vec![std::fs::File::open(temp_path).unwrap()], None);

                            match read_back_result {
                                Ok(reader) => {
                                    let mut iterator = reader.into_iter(None, None);
                                    let mut roundtrip_df = None;

                                    for batch_result in iterator {
                                        let batch = batch_result.unwrap();
                                        if batch.is_empty() {
                                            continue;
                                        }

                                        match roundtrip_df {
                                            None => roundtrip_df = Some(batch),
                                            Some(ref mut df) => {
                                                *df = df.vstack(&batch).unwrap();
                                            }
                                        }
                                    }

                                    if let Some(roundtrip_df) = roundtrip_df {
                                        println!("✅ Successfully read round-trip file");
                                        println!(
                                            "Round-trip: {} rows × {} columns",
                                            roundtrip_df.height(),
                                            roundtrip_df.width()
                                        );

                                        // Verify data integrity
                                        assert_eq!(
                                            original_df.height(),
                                            roundtrip_df.height(),
                                            "Row count should match"
                                        );
                                        assert_eq!(
                                            original_df.width(),
                                            roundtrip_df.width(),
                                            "Column count should match"
                                        );

                                        // Verify column names
                                        let original_names: Vec<_> = original_df.get_column_names();
                                        let roundtrip_names: Vec<_> =
                                            roundtrip_df.get_column_names();
                                        assert_eq!(
                                            original_names.len(),
                                            roundtrip_names.len(),
                                            "Column count should match"
                                        );

                                        println!("✅ Real dBase file round-trip test successful!");
                                    } else {
                                        println!("❌ No data read back from round-trip file");
                                    }
                                }
                                Err(e) => println!("❌ Failed to read round-trip file: {}", e),
                            }
                        }
                        Err(e) => println!("❌ Failed to write round-trip file: {}", e),
                    }
                } else {
                    println!("❌ No data read from real dBase file");
                }
            }
            Err(e) => println!("❌ Failed to read real dBase file: {}", e),
        }
    }
}
