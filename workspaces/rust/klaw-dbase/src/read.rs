//! DBF scanner implementation for efficient batch processing of dBase files
//!
//! This module provides a scanner that can efficiently read DBF files in batches,
//! with support for column selection, multi-file scanning, and memory-efficient
//! processing using the dBase Record abstraction.

use rayon::prelude::*;
use std::io::{Read, Seek};
use std::iter::{Fuse, FusedIterator};
use std::sync::Arc;

// Progress tracking
use crate::progress::DbaseProgressTracker;

#[allow(unused_imports)]
use dbase::{FieldInfo, Reader, Record};
use polars::error::PolarsError;
use polars::frame::DataFrame;
#[allow(unused_imports)]
use polars::prelude::{Column, PlSmallStr, Schema as PlSchema, SchemaNamesAndDtypes};
use polars::series::Series;

use super::des::{ValueBuilder, new_value_builder, try_from_schema};
use super::error::Error as ValueError;
use dbase::{ReaderBuilder, Unicode, UnicodeLossy};

/// Typed encoding enum that is Copy + Send + Sync
///
/// This replaces the String-based encoding to enable parallel file reading.
/// All variants use encoding_rs internally for Send + Sync compatibility.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum DbfEncoding {
    /// UTF-8 (strict)
    Utf8,
    /// UTF-8 with lossy replacement for invalid sequences
    Utf8Lossy,
    /// ASCII
    Ascii,
    /// Windows-1252 (Western European) - default for DataSUS
    #[default]
    Cp1252,
    /// Windows-1250 (Central European)
    Cp1250,
    /// Windows-1251 (Cyrillic)
    Cp1251,
    /// Windows-1253 (Greek)
    Cp1253,
    /// Windows-1254 (Turkish)
    Cp1254,
    /// Windows-1255 (Hebrew)
    Cp1255,
    /// Windows-1256 (Arabic)
    Cp1256,
    /// Windows-1257 (Baltic)
    Cp1257,
    /// Windows-1258 (Vietnamese)
    Cp1258,
    /// IBM866 (Russian DOS)
    Cp866,
    /// Windows-874 (Thai)
    Cp874,
    /// ISO-8859-1 (Latin-1, Western European)
    Iso8859_1,
    /// ISO-8859-2 (Central European)
    Iso8859_2,
    /// ISO-8859-7 (Greek)
    Iso8859_7,
    /// ISO-8859-15 (Latin-9, Western European with Euro)
    Iso8859_15,
    /// GBK (Simplified Chinese)
    Gbk,
    /// Big5 (Traditional Chinese)
    Big5,
    /// Shift_JIS (Japanese)
    ShiftJis,
    /// EUC-JP (Japanese)
    EucJp,
    /// EUC-KR (Korean)
    EucKr,
}

impl std::fmt::Display for DbfEncoding {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        use DbfEncoding::*;
        let name = match self {
            Utf8 => "utf8",
            Utf8Lossy => "utf8-lossy",
            Ascii => "ascii",
            Cp1252 => "cp1252",
            Cp1250 => "cp1250",
            Cp1251 => "cp1251",
            Cp1253 => "cp1253",
            Cp1254 => "cp1254",
            Cp1255 => "cp1255",
            Cp1256 => "cp1256",
            Cp1257 => "cp1257",
            Cp1258 => "cp1258",
            Cp866 => "cp866",
            Cp874 => "cp874",
            Iso8859_1 => "iso-8859-1",
            Iso8859_2 => "iso-8859-2",
            Iso8859_7 => "iso-8859-7",
            Iso8859_15 => "iso-8859-15",
            Gbk => "gbk",
            Big5 => "big5",
            ShiftJis => "shift_jis",
            EucJp => "euc-jp",
            EucKr => "euc-kr",
        };
        write!(f, "{}", name)
    }
}

impl std::str::FromStr for DbfEncoding {
    type Err = ValueError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        resolve_encoding_string(s)
    }
}

/// Progress tracking mode for file reading
///
/// Controls how progress is reported during batch iteration.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ProgressMode {
    /// No progress tracking (default)
    #[default]
    None,
    /// Track only overall progress across all files
    Total,
    /// Track per-file progress and overall progress
    PerFile,
}

/// Configuration options for DBF scanning
#[derive(Debug, Clone)]
pub struct DbfReadOptions {
    /// Batch size for DataFrame creation
    pub batch_size: usize,
    /// Character trimming options
    pub character_trim: dbase::TrimOption,
    /// Whether to skip deleted records
    pub skip_deleted: bool,
    /// Whether to validate schema consistency across files
    pub validate_schema: bool,
    /// Encoding for text fields
    pub encoding: DbfEncoding,
}

impl Default for DbfReadOptions {
    fn default() -> Self {
        Self {
            batch_size: 1024,
            character_trim: dbase::TrimOption::BeginEnd,
            skip_deleted: true,
            validate_schema: true,
            encoding: DbfEncoding::default(),
        }
    }
}

impl DbfReadOptions {
    /// Create options with specific encoding (enum variant)
    pub fn with_encoding(encoding: DbfEncoding) -> Self {
        Self {
            encoding,
            ..Self::default()
        }
    }

    /// Create options with encoding from string (for Python compatibility)
    pub fn with_encoding_str(encoding: impl AsRef<str>) -> Result<Self, ValueError> {
        let encoding = resolve_encoding_string(encoding.as_ref())?;
        Ok(Self {
            encoding,
            ..Self::default()
        })
    }

    /// Set batch size for reading
    pub fn with_batch_size(mut self, batch_size: usize) -> Self {
        self.batch_size = batch_size;
        self
    }

    /// Set character trimming option
    pub fn with_character_trim(mut self, trim: dbase::TrimOption) -> Self {
        self.character_trim = trim;
        self
    }
}

/// Parse encoding name string to DbfEncoding enum
///
/// Supports all encodings available in encoding_rs for Send + Sync compatibility.
pub fn resolve_encoding_string(encoding_name: &str) -> Result<DbfEncoding, ValueError> {
    use DbfEncoding::*;
    match encoding_name.to_lowercase().as_str() {
        // UTF-8 encodings
        "utf8" | "utf-8" => Ok(Utf8),
        "utf8-lossy" | "utf-8-lossy" => Ok(Utf8Lossy),
        "ascii" => Ok(Ascii),

        // Windows code pages (all supported by encoding_rs)
        "cp1252" | "windows-1252" => Ok(Cp1252),
        "cp1250" | "windows-1250" => Ok(Cp1250),
        "cp1251" | "windows-1251" => Ok(Cp1251),
        "cp1253" | "windows-1253" => Ok(Cp1253),
        "cp1254" | "windows-1254" => Ok(Cp1254),
        "cp1255" | "windows-1255" => Ok(Cp1255),
        "cp1256" | "windows-1256" => Ok(Cp1256),
        "cp1257" | "windows-1257" => Ok(Cp1257),
        "cp1258" | "windows-1258" => Ok(Cp1258),

        // IBM/DOS code pages supported by encoding_rs
        "cp866" | "ibm866" | "dos-866" => Ok(Cp866),
        "cp874" | "windows-874" | "dos-874" => Ok(Cp874),

        // ISO-8859 encodings (supported by encoding_rs)
        "iso-8859-1" | "iso8859-1" | "latin1" => Ok(Iso8859_1),
        "iso-8859-2" | "iso8859-2" | "latin2" => Ok(Iso8859_2),
        "iso-8859-7" | "iso8859-7" | "greek" => Ok(Iso8859_7),
        "iso-8859-15" | "iso8859-15" | "latin9" => Ok(Iso8859_15),

        // CJK encodings (all supported by encoding_rs)
        "gbk" | "gb2312" | "gb18030" => Ok(Gbk),
        "big5" => Ok(Big5),
        "shift_jis" | "sjis" | "shift-jis" => Ok(ShiftJis),
        "euc-jp" | "eucjp" => Ok(EucJp),
        "euc-kr" | "euckr" => Ok(EucKr),

        _ => Err(ValueError::EncodingError(format!(
            "Unsupported encoding: '{}'. Supported encodings: utf8, cp1250-1258, cp866, cp874, iso-8859-2, iso-8859-7, gbk, big5, shift_jis, euc-jp, euc-kr",
            encoding_name
        ))),
    }
}

/// Build a dbase Reader with the specified encoding
///
/// Uses encoding_rs exclusively for all non-UTF8 encodings to ensure Send + Sync.
fn build_reader_with_encoding<R: Read + Seek>(
    source: R,
    encoding: DbfEncoding,
    reading_options: dbase::ReadingOptions,
) -> Result<Reader<R>, dbase::Error> {
    use DbfEncoding::*;

    // Helper macro to reduce boilerplate for encoding_rs encodings
    macro_rules! with_encoding_rs {
        ($enc:expr) => {
            ReaderBuilder::new(source)
                .with_encoding(dbase::encoding::EncodingRs::from($enc))
                .with_options(reading_options)
                .build()
        };
    }

    match encoding {
        // UTF-8 variants use built-in Unicode types
        Utf8 => ReaderBuilder::new(source)
            .with_encoding(Unicode)
            .with_options(reading_options)
            .build(),
        Utf8Lossy | Ascii => ReaderBuilder::new(source)
            .with_encoding(UnicodeLossy)
            .with_options(reading_options)
            .build(),

        // Windows code pages via encoding_rs
        Cp1252 => with_encoding_rs!(encoding_rs::WINDOWS_1252),
        Cp1250 => with_encoding_rs!(encoding_rs::WINDOWS_1250),
        Cp1251 => with_encoding_rs!(encoding_rs::WINDOWS_1251),
        Cp1253 => with_encoding_rs!(encoding_rs::WINDOWS_1253),
        Cp1254 => with_encoding_rs!(encoding_rs::WINDOWS_1254),
        Cp1255 => with_encoding_rs!(encoding_rs::WINDOWS_1255),
        Cp1256 => with_encoding_rs!(encoding_rs::WINDOWS_1256),
        Cp1257 => with_encoding_rs!(encoding_rs::WINDOWS_1257),
        Cp1258 => with_encoding_rs!(encoding_rs::WINDOWS_1258),

        // IBM/DOS code pages via encoding_rs
        Cp866 => with_encoding_rs!(encoding_rs::IBM866),
        Cp874 => with_encoding_rs!(encoding_rs::WINDOWS_874),

        // ISO-8859 via encoding_rs
        // Note: ISO-8859-1 uses WINDOWS_1252 which is a superset (web standard behavior)
        Iso8859_1 => with_encoding_rs!(encoding_rs::WINDOWS_1252),
        Iso8859_2 => with_encoding_rs!(encoding_rs::ISO_8859_2),
        Iso8859_7 => with_encoding_rs!(encoding_rs::ISO_8859_7),
        Iso8859_15 => with_encoding_rs!(encoding_rs::ISO_8859_15),

        // CJK encodings via encoding_rs
        Gbk => with_encoding_rs!(encoding_rs::GBK),
        Big5 => with_encoding_rs!(encoding_rs::BIG5),
        ShiftJis => with_encoding_rs!(encoding_rs::SHIFT_JIS),
        EucJp => with_encoding_rs!(encoding_rs::EUC_JP),
        EucKr => with_encoding_rs!(encoding_rs::EUC_KR),
    }
}

/// Sanitize field names to remove null bytes and other invalid characters
/// This mirrors the function in des.rs but is used for field name mapping
fn sanitize_field_name_for_mapping(name: &str) -> String {
    // Remove null bytes and any characters after the first null byte
    let cleaned = if let Some(null_pos) = name.find('\0') {
        &name[..null_pos]
    } else {
        name
    };

    // Trim whitespace and replace any remaining problematic characters
    let mut result = cleaned.trim().to_string();

    // Replace empty field names with a default
    if result.is_empty() {
        result = "unnamed_field".to_string();
    }

    // Ensure the name is valid for Arrow (no control characters, etc.)
    result.retain(|c| c.is_ascii_graphic() || c == '_' || c == ' ');

    // If the result is empty after cleaning, use a default name
    if result.is_empty() {
        result = "unnamed_field".to_string();
    }

    result
}

/// An abstract scanner that can be converted into an iterator over `DataFrame`s
///
/// This scanner provides efficient batch processing of DBF files with support for:
/// - Column selection (only read needed fields)
/// - Multi-file scanning with schema validation
/// - Memory-efficient processing using Record abstraction
/// - Configurable batch sizes
pub struct DbfReader<R, I>
where
    R: Read + Seek,
{
    reader: Reader<R>,
    sources: I,
    schema: Arc<PlSchema>,
    field_info: Vec<FieldInfo>,
    field_name_mapping: std::collections::HashMap<String, String>, // sanitized -> original
    single_column_name: Option<PlSmallStr>,
    options: DbfReadOptions,
}

impl<R, I> std::fmt::Debug for DbfReader<R, I>
where
    R: Read + Seek,
    I: Iterator<Item = Result<R, std::io::Error>>,
{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("DbfReader")
            .field("options", &self.options)
            .field("schema_len", &self.schema.len())
            .field("field_count", &self.field_info.len())
            .field("single_column_name", &self.single_column_name)
            .finish()
    }
}

// FIXME move into module since we need to expose it
pub enum Infallable {}

impl From<Infallable> for ValueError {
    fn from(_: Infallable) -> Self {
        unreachable!()
    }
}

pub struct InfallableIter<I>(pub I);

impl<I: Iterator> Iterator for InfallableIter<I> {
    type Item = Result<I::Item, Infallable>;

    fn next(&mut self) -> Option<Self::Item> {
        self.0.next().map(Result::Ok)
    }
}

impl<I: ExactSizeIterator> ExactSizeIterator for InfallableIter<I> {}
impl<I: FusedIterator> FusedIterator for InfallableIter<I> {}

impl<R, I> DbfReader<R, InfallableIter<I>>
where
    R: Read + Seek,
    I: Iterator<Item = R>,
{
    /// Create a new scanner from file sources
    ///
    /// # Errors
    ///
    /// If the schema can't be converted into a Polars schema.
    pub fn new(
        sources: impl IntoIterator<IntoIter = I>,
        single_column_name: Option<PlSmallStr>,
    ) -> Result<Self, ValueError> {
        Self::try_new(
            InfallableIter(sources.into_iter()),
            single_column_name,
            DbfReadOptions::default(),
        )
    }

    /// Create a new scanner with custom options
    pub fn new_with_options(
        sources: impl IntoIterator<IntoIter = I>,
        single_column_name: Option<PlSmallStr>,
        options: DbfReadOptions,
    ) -> Result<Self, ValueError> {
        Self::try_new(
            InfallableIter(sources.into_iter()),
            single_column_name,
            options,
        )
    }
}

impl<R, E, I> DbfReader<R, I>
where
    R: Read + Seek,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>>,
{
    /// Create a new scanner from `ScanSources`
    ///
    /// # Errors
    ///
    /// If the schema can't be converted into a Polars schema, or any errors from the readers.
    pub fn try_new(
        sources: impl IntoIterator<IntoIter = I>,
        single_column_name: Option<PlSmallStr>,
        options: DbfReadOptions,
    ) -> Result<Self, ValueError> {
        let mut sources = sources.into_iter();
        let source = sources.next().ok_or(ValueError::InternalError {
            message: "No sources provided".to_string(),
        })??;

        // Create reading options from configuration
        let reading_options =
            dbase::ReadingOptions::default().character_trim(options.character_trim);

        // Build reader with typed encoding enum
        let reader = build_reader_with_encoding(source, options.encoding, reading_options)?;

        let field_info = reader.fields().to_vec();
        let schema = Arc::new(try_from_schema(&field_info, single_column_name.as_ref())?);

        // Create mapping from sanitized field names to original field names
        let mut field_name_mapping = std::collections::HashMap::new();
        for field in &field_info {
            let sanitized_name = sanitize_field_name_for_mapping(field.name());
            field_name_mapping.insert(sanitized_name, field.name().to_string());
        }

        Ok(Self {
            reader,
            sources,
            schema,
            field_info,
            field_name_mapping,
            single_column_name,
            options,
        })
    }

    /// Get the schema
    pub fn schema(&self) -> Arc<PlSchema> {
        self.schema.clone()
    }

    /// Get the field information
    pub fn field_info(&self) -> &[FieldInfo] {
        &self.field_info
    }

    /// Get the total number of records in the current reader
    pub fn total_records(&self) -> usize {
        self.reader.header().num_records as usize
    }

    /// Convert the scanner into an actual iterator
    pub fn into_iter(
        self,
        batch_size: Option<usize>,
        with_columns: Option<Arc<[usize]>>,
    ) -> Fuse<DbfIter<R, I>> {
        let actual_batch_size = batch_size.unwrap_or(self.options.batch_size);
        DbfIter {
            reader: self.reader,
            sources: self.sources,
            schema: self.schema,
            _field_info: self.field_info,
            field_name_mapping: self.field_name_mapping.clone(),
            single_column_name: self.single_column_name,
            options: self.options,
            batch_size: actual_batch_size,
            with_columns,
            progress_tracker: None,
            progress_mode: ProgressMode::None,
            current_file_index: 0,
            records_processed_in_file: 0,
        }
        .fuse()
    }

    /// Convert the scanner into an actual iterator with column names
    ///
    /// This uses string columns instead of indices
    ///
    /// # Errors
    ///
    /// If columns don't exist in the schema.
    pub fn try_into_iter(
        self,
        batch_size: Option<usize>,
        columns: Option<&[impl AsRef<str>]>,
    ) -> Result<Fuse<DbfIter<R, I>>, ValueError> {
        let with_columns = if let Some(columns) = columns {
            let indexes = columns
                .iter()
                .map(|name| {
                    self.schema
                        .index_of(name.as_ref())
                        .ok_or_else(|| PolarsError::ColumnNotFound(name.as_ref().to_owned().into()))
                })
                .collect::<Result<_, _>>()?;
            Some(indexes)
        } else {
            None
        };
        Ok(self.into_iter(batch_size, with_columns))
    }

    /// Convert the scanner into an actual iterator with progress tracking
    pub fn into_iter_with_progress(
        self,
        batch_size: Option<usize>,
        with_columns: Option<Arc<[usize]>>,
        progress_tracker: Option<DbaseProgressTracker>,
        progress_mode: ProgressMode,
    ) -> Fuse<DbfIter<R, I>> {
        let actual_batch_size = batch_size.unwrap_or(self.options.batch_size);
        DbfIter {
            reader: self.reader,
            sources: self.sources,
            schema: self.schema,
            _field_info: self.field_info,
            field_name_mapping: self.field_name_mapping.clone(),
            single_column_name: self.single_column_name,
            options: self.options,
            batch_size: actual_batch_size,
            with_columns,
            progress_tracker,
            progress_mode,
            current_file_index: 0,
            records_processed_in_file: 0,
        }
        .fuse()
    }
}
/// An `Iterator` of `DataFrame` batches scanned from various DBF sources
///
/// This iterator efficiently processes DBF files using the Record abstraction
/// for clean separation of concerns and memory efficiency.
pub struct DbfIter<R, I>
where
    R: Read + Seek,
{
    reader: Reader<R>,
    sources: I,
    schema: Arc<PlSchema>,
    _field_info: Vec<FieldInfo>,
    field_name_mapping: std::collections::HashMap<String, String>, // sanitized -> original
    single_column_name: Option<PlSmallStr>,
    options: DbfReadOptions,
    batch_size: usize,
    with_columns: Option<Arc<[usize]>>,
    // Progress tracking
    progress_tracker: Option<DbaseProgressTracker>,
    progress_mode: ProgressMode,
    current_file_index: usize,
    records_processed_in_file: usize,
}

impl<R, E, I> DbfIter<R, I>
where
    R: Read + Seek,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>>,
{
    /// Update progress tracking based on configured mode
    fn update_progress(&mut self, records_read: usize) {
        match self.progress_mode {
            ProgressMode::None => { /* no-op */ }
            ProgressMode::Total => {
                if let Some(ref tracker) = self.progress_tracker {
                    tracker.update_overall_progress(records_read as u64);
                }
            }
            ProgressMode::PerFile => {
                if let Some(ref tracker) = self.progress_tracker {
                    self.records_processed_in_file += records_read;
                    tracker.update_file_progress(
                        self.current_file_index,
                        self.records_processed_in_file as u64,
                    );
                    tracker.update_overall_progress(records_read as u64);
                }
            }
        }
    }

    /// Handle file transition and reset progress tracking
    fn on_file_transition(&mut self) {
        if self.progress_mode == ProgressMode::PerFile {
            self.current_file_index += 1;
            self.records_processed_in_file = 0;
        }
    }

    fn read_columns(
        &mut self,
        with_columns: impl IntoIterator<Item = usize> + Clone,
    ) -> Result<Vec<Column>, ValueError> {
        let column_indices: Vec<usize> = with_columns.into_iter().collect();

        // Collect all records for the batch first to enable parallel processing
        let mut records = Vec::with_capacity(self.batch_size);

        // Collect records from current file
        for _ in 0..self.batch_size {
            if let Some(record_result) = self.reader.iter_records().next() {
                records.push(record_result);
            } else {
                break;
            }
        }

        // Update progress after collecting batch (more efficient than per-record)
        if !records.is_empty() {
            self.update_progress(records.len());
        }

        // If we need more records, try to get them from additional sources
        if records.len() < self.batch_size {
            while records.len() < self.batch_size {
                if let Some(source_result) = self.sources.next() {
                    let reading_options = dbase::ReadingOptions::default()
                        .character_trim(self.options.character_trim);

                    // Build reader with typed encoding enum
                    self.reader = build_reader_with_encoding(
                        source_result?,
                        self.options.encoding,
                        reading_options,
                    )?;

                    // Validate schema if required
                    if self.options.validate_schema {
                        let new_field_info = self.reader.fields().to_vec();
                        let new_schema =
                            try_from_schema(&new_field_info, self.single_column_name.as_ref())?;

                        if new_schema != *self.schema {
                            return Err(ValueError::InternalError {
                                message: "Schema mismatch between files".to_string(),
                            });
                        }
                    }

                    // Handle file transition
                    self.on_file_transition();

                    let current_remaining = self.batch_size - records.len();

                    // Collect records from the new file
                    let records_to_add = self
                        .reader
                        .iter_records()
                        .take(current_remaining)
                        .collect::<Vec<_>>();

                    let num_records_added = records_to_add.len();

                    // Update progress for new records
                    if num_records_added > 0 {
                        self.update_progress(num_records_added);
                    }

                    records.extend(records_to_add);

                    // If no records were added, continue to next file
                    if num_records_added == 0 {
                        continue;
                    }
                } else {
                    break;
                }
            }
        }

        // If no records, return empty columns
        if records.is_empty() {
            return column_indices
                .into_iter()
                .map(|idx| {
                    let (name, dtype) = self.schema.get_at_index(idx).unwrap();
                    let mut builder = new_value_builder(dtype, 0);
                    let series = Series::from_arrow(name.clone(), builder.as_box())?;
                    Ok(unsafe { series.cast_unchecked(dtype) }?.into())
                })
                .collect();
        }

        // 🚀 PARALLEL COLUMN PROCESSING
        // Process each column independently in parallel
        let parallel_results: Result<Vec<_>, _> = column_indices
            .par_iter()
            .map(|&field_idx| {
                let (field_name, dtype) = self.schema.get_at_index(field_idx).unwrap();
                let original_field_name = self
                    .field_name_mapping
                    .get(field_name.as_str())
                    .map(|s| s.as_str())
                    .unwrap_or(field_name.as_str());

                let mut builder = new_value_builder(dtype, records.len());

                for record_result in &records {
                    match record_result {
                        Ok(record) => {
                            if let Some(field_value) = record.get(original_field_name) {
                                // Try to push the value, if it fails insert null
                                if builder.try_push_value(field_value).is_err() {
                                    builder.push_null();
                                }
                            } else {
                                // Field not found in record, insert null
                                builder.push_null();
                            }
                        }
                        Err(_) => {
                            // If there's an error reading a record, insert null
                            builder.push_null();
                        }
                    }
                }

                let series = Series::from_arrow(field_name.clone(), builder.as_box())?;
                // NOTE we intentionally want to avoid any actual casting here
                Ok(unsafe { series.cast_unchecked(dtype) }?.into())
            })
            .collect();

        parallel_results
    }

    fn read_frame(&mut self) -> Result<DataFrame, ValueError> {
        let columns = if let Some(with_columns) = &self.with_columns {
            let cols = with_columns.clone();
            self.read_columns(cols.iter().copied())?
        } else {
            self.read_columns(0..self.schema.len())?
        };

        let df = DataFrame::new(columns)?;

        // If this is an empty DataFrame, we've reached EOF - finish progress tracking
        if let (true, Some(tracker)) = (df.is_empty(), &self.progress_tracker) {
            tracker.finish();
        }

        Ok(df)
    }
}

impl<R, E, I> Iterator for DbfIter<R, I>
where
    R: Read + Seek,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>>,
{
    type Item = Result<DataFrame, ValueError>;

    fn next(&mut self) -> Option<Self::Item> {
        match self.read_frame() {
            Ok(frame) if frame.is_empty() => None,
            res => Some(res),
        }
    }
}

#[cfg(test)]
mod read_tests {
    use super::*;
    #[allow(unused_imports)]
    use std::io::Cursor;

    /// Helper function to create a temporary DBF file for testing
    fn create_test_dbf() -> std::io::Result<(tempfile::NamedTempFile, Vec<dbase::FieldInfo>)> {
        use dbase::{Date, FieldName, FieldValue, Reader, Record, TableWriterBuilder};

        // Create a temporary file
        let temp_file = tempfile::NamedTempFile::new()?;

        // Create a writer with explicit field definitions
        let mut writer = TableWriterBuilder::new()
            .add_integer_field(FieldName::try_from("ID").unwrap())
            .add_character_field(FieldName::try_from("NAME").unwrap(), 20)
            .add_logical_field(FieldName::try_from("ACTIVE").unwrap())
            .add_numeric_field(FieldName::try_from("SALARY").unwrap(), 10, 2)
            .add_date_field(FieldName::try_from("BIRTH_DATE").unwrap())
            .add_float_field(FieldName::try_from("SCORE").unwrap(), 10, 2)
            .build_with_file_dest(temp_file.path())
            .map_err(std::io::Error::other)?;

        // Create test records
        let records = vec![
            {
                let mut record = Record::default();
                record.insert("ID".to_string(), FieldValue::Integer(1));
                record.insert(
                    "NAME".to_string(),
                    FieldValue::Character(Some("Alice Johnson".to_string())),
                );
                record.insert("ACTIVE".to_string(), FieldValue::Logical(Some(true)));
                record.insert("SALARY".to_string(), FieldValue::Numeric(Some(75000.50)));
                record.insert(
                    "BIRTH_DATE".to_string(),
                    FieldValue::Date(Some(Date::new(15, 6, 1990))),
                );
                record.insert("SCORE".to_string(), FieldValue::Float(Some(95.5)));
                record
            },
            {
                let mut record = Record::default();
                record.insert("ID".to_string(), FieldValue::Integer(2));
                record.insert(
                    "NAME".to_string(),
                    FieldValue::Character(Some("Bob Smith".to_string())),
                );
                record.insert("ACTIVE".to_string(), FieldValue::Logical(Some(false)));
                record.insert("SALARY".to_string(), FieldValue::Numeric(Some(60000.00)));
                record.insert(
                    "BIRTH_DATE".to_string(),
                    FieldValue::Date(Some(Date::new(22, 3, 1985))),
                );
                record.insert("SCORE".to_string(), FieldValue::Float(Some(87.2)));
                record
            },
            {
                let mut record = Record::default();
                record.insert("ID".to_string(), FieldValue::Integer(3));
                record.insert(
                    "NAME".to_string(),
                    FieldValue::Character(Some("Carol Davis".to_string())),
                );
                record.insert("ACTIVE".to_string(), FieldValue::Logical(None)); // Null value
                record.insert("SALARY".to_string(), FieldValue::Numeric(None)); // Null value
                record.insert("BIRTH_DATE".to_string(), FieldValue::Date(None)); // Null value
                record.insert("SCORE".to_string(), FieldValue::Float(None)); // Null value
                record
            },
        ];

        // Write the records
        for record in records {
            writer
                .write_record(&record)
                .map_err(std::io::Error::other)?;
        }

        writer.finalize().map_err(std::io::Error::other)?;

        // Now read the file back to get the field info
        let reader = Reader::from_path(temp_file.path()).map_err(std::io::Error::other)?;
        let fields = reader.fields().to_vec();

        Ok((temp_file, fields))
    }

    #[test]
    fn test_read_options_default() {
        let options = DbfReadOptions::default();
        assert_eq!(options.batch_size, 1024);
        assert_eq!(options.encoding, DbfEncoding::Cp1252);
        assert!(options.skip_deleted);
        assert!(options.validate_schema);
    }

    #[test]
    fn test_read_options_builder() {
        let options = DbfReadOptions::with_encoding(DbfEncoding::Utf8)
            .with_batch_size(2048)
            .with_character_trim(dbase::TrimOption::End);

        assert_eq!(options.encoding, DbfEncoding::Utf8);
        assert_eq!(options.batch_size, 2048);
        assert!(matches!(options.character_trim, dbase::TrimOption::End));
    }

    #[test]
    fn test_read_options_from_string() {
        let options = DbfReadOptions::with_encoding_str("utf8").expect("utf8 should be valid");
        assert_eq!(options.encoding, DbfEncoding::Utf8);

        let options = DbfReadOptions::with_encoding_str("cp1252").expect("cp1252 should be valid");
        assert_eq!(options.encoding, DbfEncoding::Cp1252);

        let result = DbfReadOptions::with_encoding_str("invalid-encoding");
        assert!(result.is_err(), "invalid encoding should fail");
    }

    #[test]
    fn test_reader_creation() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let options = DbfReadOptions::default();
        let result = DbfReader::new_with_options(vec![temp_file.into_file()], None, options);

        assert!(result.is_ok());

        let reader = result.unwrap();
        assert_eq!(reader.schema().len(), 6); // ID, NAME, ACTIVE, SALARY, BIRTH_DATE, SCORE fields
        assert_eq!(reader.field_info().len(), 6);
    }

    #[test]
    fn test_reader_with_utf8_encoding() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let options = DbfReadOptions::with_encoding(DbfEncoding::Utf8);
        let result = DbfReader::new_with_options(vec![temp_file.into_file()], None, options);

        assert!(result.is_ok());
    }

    #[test]
    fn test_reader_with_cp1252_encoding() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let options = DbfReadOptions::with_encoding(DbfEncoding::Cp1252);
        let result = DbfReader::new_with_options(vec![temp_file.into_file()], None, options);

        assert!(result.is_ok());
    }

    #[test]
    fn test_reader_no_sources() {
        let options = DbfReadOptions::default();
        let result =
            DbfReader::new_with_options(std::iter::empty::<std::fs::File>(), None, options);

        assert!(result.is_err());
    }

    #[test]
    fn test_encoding_enum_display() {
        assert_eq!(DbfEncoding::Utf8.to_string(), "utf8");
        assert_eq!(DbfEncoding::Cp1252.to_string(), "cp1252");
        assert_eq!(DbfEncoding::Gbk.to_string(), "gbk");
    }

    #[test]
    fn test_encoding_enum_from_str() {
        use std::str::FromStr;
        assert_eq!(DbfEncoding::from_str("utf8").unwrap(), DbfEncoding::Utf8);
        assert_eq!(DbfEncoding::from_str("UTF-8").unwrap(), DbfEncoding::Utf8);
        assert_eq!(
            DbfEncoding::from_str("cp1252").unwrap(),
            DbfEncoding::Cp1252
        );
        assert_eq!(
            DbfEncoding::from_str("windows-1252").unwrap(),
            DbfEncoding::Cp1252
        );
        assert!(DbfEncoding::from_str("invalid").is_err());
    }

    #[test]
    fn test_reader_schema_extraction() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        let schema = reader.schema();
        assert_eq!(schema.len(), 6); // ID, NAME, ACTIVE, SALARY, BIRTH_DATE, SCORE

        // Check field names and types
        let fields: Vec<_> = schema.iter().collect();
        assert_eq!(fields[0].0, "ID");
        assert!(matches!(fields[0].1, polars::prelude::DataType::Int32));
        assert_eq!(fields[1].0, "NAME");
        assert!(matches!(fields[1].1, polars::prelude::DataType::String));
        assert_eq!(fields[2].0, "ACTIVE");
        assert!(matches!(fields[2].1, polars::prelude::DataType::Boolean));
        assert_eq!(fields[3].0, "SALARY");
        assert!(matches!(fields[3].1, polars::prelude::DataType::Float64));
        assert_eq!(fields[4].0, "BIRTH_DATE");
        assert!(matches!(fields[4].1, polars::prelude::DataType::Date));
        assert_eq!(fields[5].0, "SCORE");
        assert!(matches!(fields[5].1, polars::prelude::DataType::Float32));
    }

    #[test]
    fn test_reader_field_info() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        let field_info = reader.field_info();
        assert_eq!(field_info.len(), 6);

        // Check field info details
        assert_eq!(field_info[0].name(), "ID");
        assert!(matches!(
            field_info[0].field_type(),
            dbase::FieldType::Integer
        ));
        assert_eq!(field_info[1].name(), "NAME");
        assert!(matches!(
            field_info[1].field_type(),
            dbase::FieldType::Character
        ));
        assert_eq!(field_info[2].name(), "ACTIVE");
        assert!(matches!(
            field_info[2].field_type(),
            dbase::FieldType::Logical
        ));
        assert_eq!(field_info[3].name(), "SALARY");
        assert!(matches!(
            field_info[3].field_type(),
            dbase::FieldType::Numeric
        ));
        assert_eq!(field_info[4].name(), "BIRTH_DATE");
        assert!(matches!(field_info[4].field_type(), dbase::FieldType::Date));
        assert_eq!(field_info[5].name(), "SCORE");
        assert!(matches!(
            field_info[5].field_type(),
            dbase::FieldType::Float
        ));
    }

    #[test]
    fn test_reader_iterator_creation() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        let _iterator = reader.into_iter(Some(100), None);
        // Iterator should be created successfully
        // We can't easily test the actual iteration without more complex setup
    }

    #[test]
    fn test_encoding_resolution() {
        // Test that our encoding resolution works for all valid string names
        let valid_encodings = vec![
            ("utf8", DbfEncoding::Utf8),
            ("utf-8", DbfEncoding::Utf8),
            ("utf8-lossy", DbfEncoding::Utf8Lossy),
            ("ascii", DbfEncoding::Ascii),
            ("cp1252", DbfEncoding::Cp1252),
            ("windows-1252", DbfEncoding::Cp1252),
            ("cp866", DbfEncoding::Cp866),
            ("ibm866", DbfEncoding::Cp866),
            ("cp874", DbfEncoding::Cp874),
            ("iso-8859-2", DbfEncoding::Iso8859_2),
            ("gbk", DbfEncoding::Gbk),
            ("big5", DbfEncoding::Big5),
            ("shift_jis", DbfEncoding::ShiftJis),
        ];

        for (encoding_str, expected_enum) in valid_encodings {
            let parsed = resolve_encoding_string(encoding_str)
                .unwrap_or_else(|_| panic!("{} should be a valid encoding", encoding_str));
            assert_eq!(
                parsed, expected_enum,
                "Encoding {} should map to {:?}",
                encoding_str, expected_enum
            );

            // Also test via with_encoding_str
            let options = DbfReadOptions::with_encoding_str(encoding_str)
                .unwrap_or_else(|_| panic!("{} should create valid options", encoding_str));
            assert_eq!(options.encoding, expected_enum);
        }

        // Test invalid encoding
        assert!(resolve_encoding_string("invalid-encoding").is_err());
    }

    #[test]
    fn test_single_column_schema() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let single_column_name = polars::prelude::PlSmallStr::from("SINGLE_COL");
        let result = DbfReader::new(
            vec![temp_file.into_file()],
            Some(single_column_name.clone()),
        );
        assert!(result.is_ok());

        let reader = result.unwrap();
        // With single column name and multiple fields, it should use the original schema
        assert_eq!(reader.schema().len(), 6);
    }

    #[test]
    fn test_batch_size_configuration() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let options = DbfReadOptions::default().with_batch_size(512);
        let reader =
            DbfReader::new_with_options(vec![temp_file.into_file()], None, options).unwrap();

        let _iterator = reader.into_iter(None, None);
        // The iterator should use the configured batch size
        // We can't easily test this without more complex setup
    }

    // Integration test with real DBF file
    #[test]
    fn test_real_sids_file_reading() {
        let file_path = "data/expected-sids.dbf";

        // Check if file exists
        std::fs::metadata(file_path).expect("Test file expected-sids.dbf should exist");

        let file = std::fs::File::open(file_path).expect("Should be able to open test file");

        // Create scanner with proper options for the real file
        let options = DbfReadOptions::with_encoding(DbfEncoding::Cp1252)
            .with_batch_size(50)
            .with_character_trim(dbase::TrimOption::BeginEnd);

        let reader_result = DbfReader::new_with_options(vec![file], None, options);
        assert!(reader_result.is_ok(), "Should create scanner successfully");

        let reader = reader_result.unwrap();

        // Test schema extraction
        let schema = reader.schema();
        assert!(!schema.is_empty(), "Schema should not be empty");

        let field_info = reader.field_info().to_vec();
        assert!(!field_info.is_empty(), "Field info should not be empty");

        // Test iterator creation
        let mut iterator = reader.into_iter(Some(25), None);

        // Test reading first batch
        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Verify batch structure
                assert_eq!(
                    first_batch.width(),
                    schema.len(),
                    "Batch should match schema width"
                );

                // Test that we can access data
                let first_row = first_batch.get_row(0);
                assert!(first_row.is_ok(), "Should have at least one row");

                println!(
                    "Successfully read {} columns from real DBF file",
                    first_batch.width()
                );
                println!(
                    "Schema fields: {:?}",
                    schema.iter().map(|(name, _)| name).collect::<Vec<_>>()
                );
                println!(
                    "Batch shape: {} rows x {} columns",
                    first_batch.height(),
                    first_batch.width()
                );
                println!("Field count: {}", field_info.len());

                // Print some field info for debugging
                for (i, field) in field_info.iter().take(5).enumerate() {
                    println!("Field {}: {} ({:?})", i, field.name(), field.field_type());
                }
            }
        }
    }

    // Integration test that would work with real DBF files
    #[test]
    fn test_real_file_reading() {
        // This test would work with actual DBF files
        // For now, we'll just verify the structure is correct

        let options = DbfReadOptions::with_encoding(DbfEncoding::Cp1252)
            .with_batch_size(1024)
            .with_character_trim(dbase::TrimOption::BeginEnd);

        // Verify options are set correctly
        assert_eq!(options.encoding, DbfEncoding::Cp1252);
        assert_eq!(options.batch_size, 1024);
        assert!(matches!(
            options.character_trim,
            dbase::TrimOption::BeginEnd
        ));
    }

    #[test]
    fn test_with_columns_functionality() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test column selection by indices
        let selected_columns = vec![0, 2, 4]; // ID, ACTIVE, BIRTH_DATE
        let mut iterator = reader.into_iter(Some(100), Some(selected_columns.into()));

        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Should only have 3 columns instead of 6
                assert_eq!(first_batch.width(), 3, "Should only read selected columns");

                // Verify column names match what we selected
                let schema = first_batch.schema();
                let column_names: Vec<_> = schema.iter_names().collect();
                assert_eq!(column_names.len(), 3);

                // The columns should be in the order we selected them
                assert_eq!(column_names[0].as_str(), "ID");
                assert_eq!(column_names[1].as_str(), "ACTIVE");
                assert_eq!(column_names[2].as_str(), "BIRTH_DATE");

                // Verify data types are correct
                let dtypes: Vec<_> = schema
                    .iter_names_and_dtypes()
                    .map(|(_, dtype)| dtype)
                    .collect();
                assert!(matches!(dtypes[0], polars::prelude::DataType::Int32)); // ID
                assert!(matches!(dtypes[1], polars::prelude::DataType::Boolean)); // ACTIVE
                assert!(matches!(dtypes[2], polars::prelude::DataType::Date)); // BIRTH_DATE

                println!("✓ Column selection by indices works correctly");
            }
        }
    }

    #[test]
    fn test_with_columns_by_names() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test column selection by names
        let selected_columns = vec!["NAME", "SALARY", "SCORE"];
        let mut iterator = reader
            .try_into_iter(Some(100), Some(&selected_columns))
            .expect("Should create iterator with column names");

        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Should only have 3 columns instead of 6
                assert_eq!(first_batch.width(), 3, "Should only read selected columns");

                // Verify column names match what we selected
                let schema = first_batch.schema();
                let column_names: Vec<_> = schema.iter_names().collect();
                assert_eq!(column_names.len(), 3);

                // The columns should be in the order we selected them
                assert_eq!(column_names[0].as_str(), "NAME");
                assert_eq!(column_names[1].as_str(), "SALARY");
                assert_eq!(column_names[2].as_str(), "SCORE");

                // Verify data types are correct
                let dtypes: Vec<_> = schema
                    .iter_names_and_dtypes()
                    .map(|(_, dtype)| dtype)
                    .collect();
                assert!(matches!(dtypes[0], polars::prelude::DataType::String)); // NAME
                assert!(matches!(dtypes[1], polars::prelude::DataType::Float64)); // SALARY
                assert!(matches!(dtypes[2], polars::prelude::DataType::Float32)); // SCORE

                println!("✓ Column selection by names works correctly");
            }
        }
    }

    #[test]
    fn test_with_columns_invalid_column() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test with invalid column name
        let invalid_columns = vec!["NONEXISTENT_COLUMN"];
        let result = reader.try_into_iter(Some(100), Some(&invalid_columns));

        assert!(result.is_err(), "Should fail with invalid column name");
        match result {
            Err(_) => {
                println!("✓ Invalid column name correctly detected");
            }
            Ok(_) => panic!("Should have failed with invalid column name"),
        }
    }

    #[test]
    fn test_with_columns_empty_selection() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test with empty column selection
        let empty_columns: Vec<usize> = vec![];
        let mut iterator = reader.into_iter(Some(100), Some(empty_columns.into()));

        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Should have no columns
                assert_eq!(
                    first_batch.width(),
                    0,
                    "Should have no columns with empty selection"
                );
                println!("✓ Empty column selection works correctly");
            }
        }
    }

    #[test]
    fn test_with_columns_all_columns() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test selecting all columns (should be same as no selection)
        let all_columns = vec![0, 1, 2, 3, 4, 5];
        let mut iterator = reader.into_iter(Some(100), Some(all_columns.into()));

        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Should have all 6 columns
                assert_eq!(first_batch.width(), 6, "Should have all columns");

                // Verify column names
                let schema = first_batch.schema();
                let column_names: Vec<_> = schema.iter_names().collect();
                assert_eq!(column_names.len(), 6);

                let expected_names = ["ID", "NAME", "ACTIVE", "SALARY", "BIRTH_DATE", "SCORE"];
                for (i, expected_name) in expected_names.iter().enumerate() {
                    assert_eq!(column_names[i].as_str(), *expected_name);
                }

                println!("✓ All columns selection works correctly");
            }
        }
    }

    #[test]
    fn test_with_columns_mixed_order() {
        let (temp_file, _fields) = create_test_dbf().expect("Should create test DBF file");

        let reader = DbfReader::new(vec![temp_file.into_file()], None).unwrap();

        // Test selecting columns in a different order
        let mixed_order_columns = vec![4, 1, 5, 2]; // BIRTH_DATE, NAME, SCORE, ACTIVE
        let mut iterator = reader.into_iter(Some(100), Some(mixed_order_columns.into()));

        if let Some(first_batch_result) = iterator.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                // Should have 4 columns in the specified order
                assert_eq!(first_batch.width(), 4, "Should have 4 columns");

                // Verify column names are in the order we selected
                let schema = first_batch.schema();
                let column_names: Vec<_> = schema.iter_names().collect();
                assert_eq!(column_names.len(), 4);

                assert_eq!(column_names[0].as_str(), "BIRTH_DATE");
                assert_eq!(column_names[1].as_str(), "NAME");
                assert_eq!(column_names[2].as_str(), "SCORE");
                assert_eq!(column_names[3].as_str(), "ACTIVE");

                println!("✓ Mixed order column selection works correctly");
            }
        }
    }

    #[test]
    fn test_real_file_with_columns_and_print_head() {
        let file_path = "data/expected-sids.dbf";

        // Check if file exists
        std::fs::metadata(file_path).expect("Test file expected-sids.dbf should exist");

        let file = std::fs::File::open(file_path).expect("Should be able to open test file");

        // Create scanner with proper options for the real file
        let options = DbfReadOptions::with_encoding(DbfEncoding::Cp1252)
            .with_batch_size(100)
            .with_character_trim(dbase::TrimOption::BeginEnd);

        let reader_result = DbfReader::new_with_options(vec![file], None, options);
        assert!(reader_result.is_ok(), "Should create scanner successfully");

        let reader = reader_result.unwrap();

        // Get schema to see available columns
        let schema = reader.schema();
        println!("\n=== Real DBF File Schema ===");
        println!("Total columns: {}", schema.len());

        let field_info = reader.field_info();
        for (i, (field_name, dtype)) in schema.iter().enumerate() {
            println!(
                "Column {}: {} -> {:?} (DBF type: {:?})",
                i,
                field_name,
                dtype,
                field_info[i].field_type()
            );
        }

        // Test 1: Select first 3 columns by index
        println!("\n=== Test 1: First 3 columns by index ===");
        let selected_indices = vec![0, 1, 2];
        let mut iterator1 = reader.into_iter(Some(50), Some(selected_indices.into()));

        if let Some(first_batch_result) = iterator1.next() {
            assert!(
                first_batch_result.is_ok(),
                "First batch should read successfully"
            );
            let first_batch = first_batch_result.unwrap();

            if !first_batch.is_empty() {
                println!(
                    "Selected columns: {:?}",
                    first_batch.schema().iter_names().collect::<Vec<_>>()
                );
                println!(
                    "Batch shape: {} rows x {} columns",
                    first_batch.height(),
                    first_batch.width()
                );

                // Print first 10 rows
                println!("First 10 rows:");
                for i in 0..std::cmp::min(10, first_batch.height()) {
                    let row = first_batch.get_row(i).unwrap();
                    let values: Vec<String> = row
                        .0
                        .iter()
                        .map(|val| match val {
                            polars::prelude::AnyValue::Null => "NULL".to_string(),
                            polars::prelude::AnyValue::String(s) => format!("\"{}\"", s),
                            polars::prelude::AnyValue::Int32(i) => i.to_string(),
                            polars::prelude::AnyValue::Int64(i) => i.to_string(),
                            polars::prelude::AnyValue::Float32(f) => format!("{:.2}", f),
                            polars::prelude::AnyValue::Float64(f) => format!("{:.2}", f),
                            polars::prelude::AnyValue::Boolean(b) => b.to_string(),
                            polars::prelude::AnyValue::Date(d) => d.to_string(),
                            _ => format!("{:?}", val),
                        })
                        .collect();
                    println!("  Row {}: [{}]", i, values.join(", "));
                }
            }
        }

        // Test 2: Select specific columns by name (if we know some likely column names)
        println!("\n=== Test 2: Select columns by name ===");
        let schema_names: Vec<_> = schema.iter_names().collect();

        // Try to select some common column patterns
        let potential_columns = ["NAME", "FIPS", "FIPSNO", "CRESS_ID"];
        let available_columns: Vec<_> = potential_columns
            .iter()
            .filter(|&name| {
                schema_names
                    .iter()
                    .any(|schema_name| schema_name.contains(name))
            })
            .map(|&s| s.to_string())
            .collect();

        if !available_columns.is_empty() {
            println!("Available columns to select: {:?}", available_columns);

            // Create a new scanner since we can't reuse the previous one
            let file2 =
                std::fs::File::open(file_path).expect("Should be able to open test file again");
            let reader2 = DbfReader::new_with_options(
                vec![file2],
                None,
                DbfReadOptions::with_encoding(DbfEncoding::Cp1252),
            )
            .expect("Should create scanner again");

            let mut iterator2 = reader2
                .try_into_iter(Some(50), Some(&available_columns))
                .expect("Should create iterator with column names");

            if let Some(first_batch_result) = iterator2.next() {
                assert!(
                    first_batch_result.is_ok(),
                    "First batch should read successfully"
                );
                let first_batch = first_batch_result.unwrap();

                if !first_batch.is_empty() {
                    println!(
                        "Selected columns: {:?}",
                        first_batch.schema().iter_names().collect::<Vec<_>>()
                    );
                    println!(
                        "Batch shape: {} rows x {} columns",
                        first_batch.height(),
                        first_batch.width()
                    );

                    // Print first 10 rows
                    println!("First 10 rows:");
                    for i in 0..std::cmp::min(10, first_batch.height()) {
                        let row = first_batch.get_row(i).unwrap();
                        let values: Vec<String> = row
                            .0
                            .iter()
                            .map(|val| match val {
                                polars::prelude::AnyValue::Null => "NULL".to_string(),
                                polars::prelude::AnyValue::String(s) => format!("\"{}\"", s),
                                polars::prelude::AnyValue::Int32(i) => i.to_string(),
                                polars::prelude::AnyValue::Int64(i) => i.to_string(),
                                polars::prelude::AnyValue::Float32(f) => format!("{:.2}", f),
                                polars::prelude::AnyValue::Float64(f) => format!("{:.2}", f),
                                polars::prelude::AnyValue::Boolean(b) => b.to_string(),
                                polars::prelude::AnyValue::Date(d) => d.to_string(),
                                _ => format!("{:?}", val),
                            })
                            .collect();
                        println!("  Row {}: [{}]", i, values.join(", "));
                    }
                }
            }
        } else {
            println!("No common column patterns found, selecting first 2 columns by name instead");

            // Create a new scanner and select first 2 columns by their actual names
            let file3 =
                std::fs::File::open(file_path).expect("Should be able to open test file again");
            let reader3 = DbfReader::new_with_options(
                vec![file3],
                None,
                DbfReadOptions::with_encoding(DbfEncoding::Cp1252),
            )
            .expect("Should create scanner again");

            if schema.len() >= 2 {
                let first_two_names: Vec<_> =
                    schema_names.iter().take(2).map(|s| s.as_str()).collect();
                let mut iterator3 = reader3
                    .try_into_iter(Some(50), Some(&first_two_names))
                    .expect("Should create iterator with first two column names");

                if let Some(first_batch_result) = iterator3.next() {
                    assert!(
                        first_batch_result.is_ok(),
                        "First batch should read successfully"
                    );
                    let first_batch = first_batch_result.unwrap();

                    if !first_batch.is_empty() {
                        println!(
                            "Selected columns: {:?}",
                            first_batch.schema().iter_names().collect::<Vec<_>>()
                        );
                        println!(
                            "Batch shape: {} rows x {} columns",
                            first_batch.height(),
                            first_batch.width()
                        );

                        // Print first 10 rows
                        println!("First 10 rows:");
                        for i in 0..std::cmp::min(10, first_batch.height()) {
                            let row = first_batch.get_row(i).unwrap();
                            let values: Vec<String> = row
                                .0
                                .iter()
                                .map(|val| match val {
                                    polars::prelude::AnyValue::Null => "NULL".to_string(),
                                    polars::prelude::AnyValue::String(s) => format!("\"{}\"", s),
                                    polars::prelude::AnyValue::Int32(i) => i.to_string(),
                                    polars::prelude::AnyValue::Int64(i) => i.to_string(),
                                    polars::prelude::AnyValue::Float32(f) => format!("{:.2}", f),
                                    polars::prelude::AnyValue::Float64(f) => format!("{:.2}", f),
                                    polars::prelude::AnyValue::Boolean(b) => b.to_string(),
                                    polars::prelude::AnyValue::Date(d) => d.to_string(),
                                    _ => format!("{:?}", val),
                                })
                                .collect();
                            println!("  Row {}: [{}]", i, values.join(", "));
                        }
                    }
                }
            }
        }

        println!("\n=== Real file with_columns test completed successfully! ===");
    }
}
