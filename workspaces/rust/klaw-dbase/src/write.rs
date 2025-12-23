//! Write functionality for dBase files
//!
//! This module provides functions to write Polars DataFrames to dBase files,
//! following the pattern from the Avro plugin and using our new serializer.

use std::io::{Seek, Write};
use std::path::Path;

use dbase::{FieldName, FieldType, TableWriterBuilder};
use polars::frame::DataFrame;
use polars::prelude::Schema as PlSchema;

use crate::{
    error::Error,
    ser::{DBaseFieldSpec, Serializer, serialize_dataframe},
};

/// Options for writing dBase files
#[derive(Debug, Clone)]
pub struct WriteOptions {
    /// Character encoding for string fields (e.g., "cp1252", "utf8", "gbk")
    pub encoding: String,
    /// Whether to overwrite existing files (for file-based functions)
    pub overwrite: bool,
    /// Threshold for using memo fields (string length)
    pub memo_threshold: usize,
}

impl Default for WriteOptions {
    fn default() -> Self {
        Self {
            encoding: "cp1252".to_string(), // Default for DataSUS compatibility
            overwrite: true,
            memo_threshold: 254, // Use memo for strings > 254 chars
        }
    }
}

impl WriteOptions {
    /// Create options with specific encoding
    pub fn with_encoding(encoding: impl Into<String>) -> Self {
        Self {
            encoding: encoding.into(),
            ..Self::default()
        }
    }

    /// Set memo threshold
    pub fn with_memo_threshold(mut self, threshold: usize) -> Self {
        self.memo_threshold = threshold;
        self
    }

    /// Set overwrite behavior
    pub fn with_overwrite(mut self, overwrite: bool) -> Self {
        self.overwrite = overwrite;
        self
    }
}

/// Resolve encoding string to a normalized form
/// This mirrors the function in read.rs for consistency
/// Uses encoding_rs exclusively for Send + Sync compatibility
fn resolve_encoding_string(encoding_name: &str) -> Result<String, Error> {
    // Validate and normalize encoding names
    match encoding_name.to_lowercase().as_str() {
        // UTF-8 encodings
        "utf8" | "utf-8" => Ok("utf8".to_string()),
        "utf8-lossy" | "utf-8-lossy" => Ok("utf8-lossy".to_string()),
        "ascii" => Ok("ascii".to_string()),

        // Windows code pages (all supported by encoding_rs)
        "cp1252" | "windows-1252" => Ok("cp1252".to_string()),
        "cp1250" | "windows-1250" => Ok("cp1250".to_string()),
        "cp1251" | "windows-1251" => Ok("cp1251".to_string()),
        "cp1253" | "windows-1253" => Ok("cp1253".to_string()),
        "cp1254" | "windows-1254" => Ok("cp1254".to_string()),
        "cp1255" | "windows-1255" => Ok("cp1255".to_string()),
        "cp1256" | "windows-1256" => Ok("cp1256".to_string()),
        "cp1257" | "windows-1257" => Ok("cp1257".to_string()),
        "cp1258" | "windows-1258" => Ok("cp1258".to_string()),

        // IBM/DOS code pages supported by encoding_rs
        "cp866" | "ibm866" | "dos-866" => Ok("cp866".to_string()),
        "cp874" | "windows-874" | "dos-874" => Ok("cp874".to_string()),

        // ISO-8859 encodings (supported by encoding_rs)
        "iso-8859-1" | "iso8859-1" | "latin1" => Ok("iso-8859-1".to_string()),
        "iso-8859-2" | "iso8859-2" | "latin2" => Ok("iso-8859-2".to_string()),
        "iso-8859-7" | "iso8859-7" | "greek" => Ok("iso-8859-7".to_string()),
        "iso-8859-15" | "iso8859-15" | "latin9" => Ok("iso-8859-15".to_string()),

        // CJK encodings (all supported by encoding_rs)
        "gbk" | "gb2312" | "gb18030" => Ok("gbk".to_string()),
        "big5" => Ok("big5".to_string()),
        "shift_jis" | "sjis" | "shift-jis" => Ok("shift_jis".to_string()),
        "euc-jp" | "eucjp" => Ok("euc-jp".to_string()),
        "euc-kr" | "euckr" => Ok("euc-kr".to_string()),

        _ => Err(Error::EncodingError(format!(
            "Unsupported encoding: '{}'. Supported encodings: utf8, cp1250-1258, cp866, cp874, iso-8859-2, iso-8859-7, gbk, big5, shift_jis, euc-jp, euc-kr",
            encoding_name
        ))),
    }
}

/// Write DataFrame chunks into a dBase file
///
/// This function follows the polars-avro pattern and writes multiple DataFrame
/// chunks to a single dBase file. All chunks must have the same schema.
///
/// # Errors
///
/// If the schema can't be written as a dBase file, if chunks have different
/// schemas, if encoding is unsupported, or if there are I/O errors during writing.
pub fn write_dbase<'a>(
    chunks: impl IntoIterator<Item = &'a DataFrame>,
    dest: impl Write + Seek,
    options: WriteOptions,
) -> Result<(), Error> {
    let mut chunks_iter = chunks.into_iter().peekable();

    if let Some(first) = chunks_iter.peek() {
        // Get Polars schema from first chunk
        let schema = first.schema();

        // Validate encoding
        let validated_encoding = resolve_encoding_string(&options.encoding)?;

        // Create serializer with encoding-aware configuration
        let serializer = Serializer::new();

        // Convert schema to dBase field specifications
        let field_specs = serializer.try_as_schema(schema)?;

        // Adjust field specs for memo fields based on threshold
        let adjusted_specs = adjust_specs_for_memo_fields(field_specs, &options);

        // Create dBase writer with encoding support
        let mut writer = create_writer_from_specs(&adjusted_specs, dest, &validated_encoding)?;

        // Write all DataFrame chunks
        for chunk in chunks_iter {
            if chunk.schema() == schema {
                write_dataframe_to_dbase(chunk, &mut writer, &adjusted_specs)?;
            } else {
                return Err(Error::NonMatchingSchemas);
            }
        }
    }

    Ok(())
}

/// Write a single DataFrame to a dBase file
///
/// Convenience function that writes a single DataFrame to a file path.
pub fn write_dbase_file<P: AsRef<Path>>(
    df: &DataFrame,
    path: P,
    options: Option<WriteOptions>,
) -> Result<(), Error> {
    let opts = options.unwrap_or_default();

    // Check if file exists and handle overwrite logic
    if path.as_ref().exists() && !opts.overwrite {
        return Err(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            "File already exists and overwrite is false",
        )
        .into());
    }

    let file = std::fs::File::create(path)?;
    write_dbase([df], file, opts)
}

/// Write DataFrame chunks with custom field specifications
///
/// Advanced function that allows users to provide custom field specifications
/// instead of relying on automatic schema inference.
pub fn write_dbase_with_specs<'a>(
    chunks: impl IntoIterator<Item = &'a DataFrame>,
    dest: impl Write + Seek,
    field_specs: Vec<DBaseFieldSpec>,
    options: WriteOptions,
) -> Result<(), Error> {
    let mut chunks_iter = chunks.into_iter().peekable();

    if let Some(first) = chunks_iter.peek() {
        let schema = first.schema();

        // Validate encoding
        let validated_encoding = resolve_encoding_string(&options.encoding)?;

        // Validate that field specs match the schema
        validate_field_specs_with_schema(&field_specs, schema)?;

        // Adjust field specs for memo fields based on threshold
        let adjusted_specs = adjust_specs_for_memo_fields(field_specs, &options);

        // Create dBase writer with encoding support
        let mut writer = create_writer_from_specs(&adjusted_specs, dest, &validated_encoding)?;

        // Write all DataFrame chunks
        for chunk in chunks_iter {
            if chunk.schema() == schema {
                write_dataframe_to_dbase(chunk, &mut writer, &adjusted_specs)?;
            } else {
                return Err(Error::NonMatchingSchemas);
            }
        }
    }

    Ok(())
}

/// Adjust field specifications (placeholder for future enhancements)
fn adjust_specs_for_memo_fields(
    specs: Vec<DBaseFieldSpec>,
    _options: &WriteOptions,
) -> Vec<DBaseFieldSpec> {
    // For now, return specs as-is
    // Memo fields are not supported in dBase3, our main target
    specs
}

/// Create a dBase TableWriter from field specifications with encoding support
///
/// Uses encoding_rs exclusively for Send + Sync compatibility.
fn create_writer_from_specs(
    specs: &[DBaseFieldSpec],
    dest: impl Write + Seek,
    encoding: &str,
) -> Result<dbase::TableWriter<impl Write + Seek>, Error> {
    // Helper macro to reduce boilerplate for encoding_rs encodings
    macro_rules! with_encoding_rs {
        ($enc:expr) => {
            TableWriterBuilder::with_encoding(dbase::encoding::EncodingRs::from($enc))
        };
    }

    // Create builder with encoding
    let mut builder = match encoding {
        // UTF-8 variants use built-in Unicode types
        "utf8" => TableWriterBuilder::with_encoding(dbase::Unicode),
        "utf8-lossy" | "ascii" => TableWriterBuilder::with_encoding(dbase::UnicodeLossy),

        // Windows code pages via encoding_rs
        "cp1252" => with_encoding_rs!(encoding_rs::WINDOWS_1252),
        "cp1250" => with_encoding_rs!(encoding_rs::WINDOWS_1250),
        "cp1251" => with_encoding_rs!(encoding_rs::WINDOWS_1251),
        "cp1253" => with_encoding_rs!(encoding_rs::WINDOWS_1253),
        "cp1254" => with_encoding_rs!(encoding_rs::WINDOWS_1254),
        "cp1255" => with_encoding_rs!(encoding_rs::WINDOWS_1255),
        "cp1256" => with_encoding_rs!(encoding_rs::WINDOWS_1256),
        "cp1257" => with_encoding_rs!(encoding_rs::WINDOWS_1257),
        "cp1258" => with_encoding_rs!(encoding_rs::WINDOWS_1258),

        // IBM/DOS code pages via encoding_rs
        "cp866" => with_encoding_rs!(encoding_rs::IBM866),
        "cp874" => with_encoding_rs!(encoding_rs::WINDOWS_874),

        // ISO-8859 via encoding_rs
        // Note: ISO-8859-1 uses WINDOWS_1252 which is a superset (web standard behavior)
        "iso-8859-1" => with_encoding_rs!(encoding_rs::WINDOWS_1252),
        "iso-8859-2" => with_encoding_rs!(encoding_rs::ISO_8859_2),
        "iso-8859-7" => with_encoding_rs!(encoding_rs::ISO_8859_7),
        "iso-8859-15" => with_encoding_rs!(encoding_rs::ISO_8859_15),

        // CJK encodings via encoding_rs
        "gbk" => with_encoding_rs!(encoding_rs::GBK),
        "big5" => with_encoding_rs!(encoding_rs::BIG5),
        "shift_jis" => with_encoding_rs!(encoding_rs::SHIFT_JIS),
        "euc-jp" => with_encoding_rs!(encoding_rs::EUC_JP),
        "euc-kr" => with_encoding_rs!(encoding_rs::EUC_KR),

        _ => {
            // Default to UnicodeLossy for unknown encodings
            TableWriterBuilder::with_encoding(dbase::UnicodeLossy)
        }
    };

    for spec in specs {
        let field_name = FieldName::try_from(spec.name.as_str()).map_err(|_| {
            Error::EncodingError(format!("Invalid field name: {}", spec.name.as_str()))
        })?;

        builder = match spec.field_type {
            FieldType::Character => builder.add_character_field(field_name, spec.length),
            FieldType::Numeric => {
                builder.add_numeric_field(field_name, spec.length, spec.decimal_places)
            }
            FieldType::Date => builder.add_date_field(field_name),
            FieldType::Logical => builder.add_logical_field(field_name),
            FieldType::Float => {
                builder.add_float_field(field_name, spec.length, spec.decimal_places)
            }
            FieldType::Integer => builder.add_integer_field(field_name),
            FieldType::Currency => builder.add_currency_field(field_name),
            FieldType::DateTime => builder.add_datetime_field(field_name),
            FieldType::Double => builder.add_double_field(field_name),
            FieldType::Memo => return Err(Error::UnsupportedFieldType(FieldType::Memo)),
        };
    }

    Ok(builder.build_with_dest(dest))
}

/// Write a single DataFrame to a dBase writer
fn write_dataframe_to_dbase(
    df: &DataFrame,
    writer: &mut dbase::TableWriter<impl Write + Seek>,
    field_specs: &[DBaseFieldSpec],
) -> Result<(), Error> {
    // Use our serializer to convert DataFrame to dBase records
    let records = serialize_dataframe(df, Some(field_specs.to_vec()))?;

    // Write each record
    for record in records {
        writer.write_record(&record)?;
    }

    Ok(())
}

/// Validate that field specifications match the Polars schema
fn validate_field_specs_with_schema(
    field_specs: &[DBaseFieldSpec],
    schema: &PlSchema,
) -> Result<(), Error> {
    if field_specs.len() != schema.len() {
        return Err(Error::SchemaMismatch(format!(
            "Field specs have {} fields but schema has {}",
            field_specs.len(),
            schema.len()
        )));
    }

    for (spec, (name, _dtype)) in field_specs.iter().zip(schema.iter()) {
        if spec.name != name.as_str() {
            return Err(Error::SchemaMismatch(format!(
                "Field name mismatch: spec has '{}' but schema has '{}'",
                spec.name, name
            )));
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::df;
    use polars::prelude::DataType;
    use std::io::Cursor;

    #[test]
    fn test_write_options_default() {
        let options = WriteOptions::default();
        assert_eq!(options.encoding, "cp1252");
        assert!(options.overwrite);
        assert_eq!(options.memo_threshold, 254);
    }

    #[test]
    fn test_write_options_builder() {
        let options = WriteOptions::with_encoding("utf8")
            .with_memo_threshold(100)
            .with_overwrite(false);

        assert_eq!(options.encoding, "utf8");
        assert_eq!(options.memo_threshold, 100);
        assert!(!options.overwrite);
    }

    #[test]
    fn test_resolve_encoding_string() {
        // Valid encodings
        assert!(resolve_encoding_string("cp1252").is_ok());
        assert!(resolve_encoding_string("utf8").is_ok());
        assert!(resolve_encoding_string("UTF-8").is_ok());
        assert!(resolve_encoding_string("utf8-lossy").is_ok());
        assert!(resolve_encoding_string("gbk").is_ok());
        assert!(resolve_encoding_string("shift_jis").is_ok());

        // Invalid encoding
        assert!(resolve_encoding_string("invalid").is_err());
    }

    #[test]
    fn test_adjust_specs_for_memo_fields() {
        let specs = vec![
            DBaseFieldSpec {
                name: "short_string".to_string(),
                field_type: FieldType::Character,
                length: 50,
                decimal_places: 0,
            },
            DBaseFieldSpec {
                name: "long_string".to_string(),
                field_type: FieldType::Character,
                length: 255, // Maximum for u8
                decimal_places: 0,
            },
        ];

        let options = WriteOptions::default();
        let adjusted = adjust_specs_for_memo_fields(specs, &options);

        // Since memo fields are not supported, specs should remain unchanged
        assert_eq!(adjusted[0].field_type, FieldType::Character);
        assert_eq!(adjusted[0].length, 50);
        assert_eq!(adjusted[1].field_type, FieldType::Character);
        assert_eq!(adjusted[1].length, 255);
    }

    #[test]
    fn test_validate_field_specs_with_schema() {
        let schema = PlSchema::from_iter(vec![
            ("name".into(), DataType::String),
            ("age".into(), DataType::Int32),
        ]);

        // Matching specs
        let specs = vec![
            DBaseFieldSpec {
                name: "name".to_string(),
                field_type: FieldType::Character,
                length: 50,
                decimal_places: 0,
            },
            DBaseFieldSpec {
                name: "age".to_string(),
                field_type: FieldType::Integer,
                length: 4,
                decimal_places: 0,
            },
        ];
        assert!(validate_field_specs_with_schema(&specs, &schema).is_ok());

        // Wrong number of specs
        let wrong_count_specs = vec![DBaseFieldSpec {
            name: "name".to_string(),
            field_type: FieldType::Character,
            length: 50,
            decimal_places: 0,
        }];
        assert!(validate_field_specs_with_schema(&wrong_count_specs, &schema).is_err());

        // Wrong field name
        let wrong_name_specs = vec![
            DBaseFieldSpec {
                name: "wrong_name".to_string(),
                field_type: FieldType::Character,
                length: 50,
                decimal_places: 0,
            },
            DBaseFieldSpec {
                name: "age".to_string(),
                field_type: FieldType::Integer,
                length: 4,
                decimal_places: 0,
            },
        ];
        assert!(validate_field_specs_with_schema(&wrong_name_specs, &schema).is_err());
    }

    #[test]
    fn test_write_dbase_empty_chunks() {
        let dest = Cursor::new(Vec::new());
        let result = write_dbase([], dest, WriteOptions::default());
        assert!(result.is_ok());
    }

    #[test]
    fn test_write_dbase_simple_dataframe() {
        let df = df! {
            "name" => ["Alice", "Bob", "Charlie"],
            "age" => [25, 30, 35],
            "score" => [95.5, 87.2, 92.1],
            "active" => [true, false, true],
        }
        .unwrap();

        let dest = Cursor::new(Vec::new());
        let result = write_dbase([&df], dest, WriteOptions::default());
        assert!(result.is_ok());
    }

    #[test]
    fn test_write_dbase_with_different_encodings() {
        let df = df! {
            "name" => ["Alice", "Bob", "Charlie"],
            "age" => [25, 30, 35],
        }
        .unwrap();

        // Test different encodings
        let encodings = ["cp1252", "utf8", "utf8-lossy", "gbk"];

        for encoding in encodings {
            let dest = Cursor::new(Vec::new());
            let options = WriteOptions::with_encoding(encoding);
            let result = write_dbase([&df], dest, options);
            assert!(result.is_ok(), "Should work with encoding: {}", encoding);
        }
    }

    #[test]
    fn test_write_dbase_invalid_encoding() {
        let df = df! {
            "name" => ["Alice", "Bob"],
        }
        .unwrap();

        let dest = Cursor::new(Vec::new());
        let options = WriteOptions::with_encoding("invalid-encoding");
        let result = write_dbase([&df], dest, options);
        assert!(result.is_err());
    }

    #[test]
    fn test_write_dbase_non_matching_schemas() {
        let df1 = df! { "a" => [1, 2, 3] }.unwrap();
        let df2 = df! { "b" => ["x", "y", "z"] }.unwrap();

        let dest = Cursor::new(Vec::new());
        let result = write_dbase([&df1, &df2], dest, WriteOptions::default());
        assert!(result.is_err());
        assert!(matches!(result.unwrap_err(), Error::NonMatchingSchemas));
    }

    #[test]
    fn test_write_dbase_with_specs() {
        let df = df! {
            "name" => ["Alice", "Bob"],
            "age" => [25, 30],
        }
        .unwrap();

        let specs = vec![
            DBaseFieldSpec {
                name: "name".to_string(),
                field_type: FieldType::Character,
                length: 50,
                decimal_places: 0,
            },
            DBaseFieldSpec {
                name: "age".to_string(),
                field_type: FieldType::Integer,
                length: 4,
                decimal_places: 0,
            },
        ];

        let dest = Cursor::new(Vec::new());
        let result = write_dbase_with_specs([&df], dest, specs, WriteOptions::default());
        assert!(result.is_ok());
    }

    #[test]
    fn test_write_dbase_file_overwrite() {
        let df = df! {
            "name" => ["Alice", "Bob"],
        }
        .unwrap();

        // Test with overwrite=true (default)
        let temp_file = tempfile::NamedTempFile::new().unwrap();
        let result = write_dbase_file(&df, temp_file.path(), None);
        assert!(result.is_ok());

        // Test with overwrite=false
        let result2 = write_dbase_file(
            &df,
            temp_file.path(),
            Some(WriteOptions::default().with_overwrite(false)),
        );
        assert!(result2.is_err());
        assert!(result2.unwrap_err().to_string().contains("already exists"));
    }
}
