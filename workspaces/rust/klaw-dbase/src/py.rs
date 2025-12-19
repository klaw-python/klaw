//! pyo3 bindings
use rayon::prelude::*;
use std::fs::File;
use std::io::{self, BufReader, BufWriter, ErrorKind, Read, Seek, SeekFrom, Write};
use std::iter::{Chain, Fuse};
use std::path::Path;
use std::sync::Arc;

use polars::prelude::{PlSmallStr, Schema};
use pyo3::exceptions::{PyException, PyIOError, PyRuntimeError, PyValueError};
use pyo3::types::{PyAnyMethods, PyBytes, PyBytesMethods, PyModule, PyModuleMethods};
use pyo3::{
    Bound, PyErr, PyObject, PyResult, Python, create_exception, pyclass, pyfunction, pymethods,
    pymodule, wrap_pyfunction,
};
use pyo3_polars::{PyDataFrame, PySchema};

use dbase::File as DbaseFile;

use crate::read_compressed::{DbcReader, create_dbf_reader_from_dbc};
use crate::{
    error::Error,
    progress::{DbaseFileInfo, create_multi_file_progress},
    read::{DbfIter, DbfReadOptions, DbfReader},
    write::{WriteOptions, write_dbase, write_dbase_file as write_dbase_file_internal},
};

/// Trait combining Read and Seek for use in ScanSource
trait ReadSeek: std::io::Read + std::io::Seek + Send + Sync {}
impl<T: std::io::Read + std::io::Seek + Send + Sync> ReadSeek for T {}

enum ScanSource {
    File(BufReader<File>),
    Bytes(BufReader<PyReader>),
    Dbc(BufReader<Box<dyn ReadSeek>>),
}

impl Read for ScanSource {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        match self {
            ScanSource::File(reader) => reader.read(buf),
            ScanSource::Bytes(reader) => reader.read(buf),
            ScanSource::Dbc(reader) => reader.read(buf),
        }
    }
}

impl Seek for ScanSource {
    fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
        match self {
            ScanSource::File(reader) => reader.seek(pos),
            ScanSource::Bytes(reader) => reader.seek(pos),
            ScanSource::Dbc(reader) => reader.seek(pos),
        }
    }
}

struct BytesIter {
    buffs: Arc<[Arc<PyObject>]>,
    idx: usize,
}

impl BytesIter {
    fn new(buffs: Arc<[Arc<PyObject>]>) -> Self {
        Self { buffs, idx: 0 }
    }
}

impl Iterator for BytesIter {
    type Item = Result<ScanSource, Error>;

    fn next(&mut self) -> Option<Self::Item> {
        self.buffs.get(self.idx).map(|buff| {
            self.idx += 1;
            Ok(ScanSource::Bytes(BufReader::new(PyReader(buff.clone()))))
        })
    }
}

struct PathIter {
    paths: Arc<[String]>,
    idx: usize,
}

impl PathIter {
    fn new(paths: Arc<[String]>) -> Self {
        Self { paths, idx: 0 }
    }
}

impl Iterator for PathIter {
    type Item = Result<ScanSource, Error>;

    fn next(&mut self) -> Option<Self::Item> {
        self.paths.get(self.idx).map(|path| {
            self.idx += 1;
            match File::open(path) {
                Ok(file) => Ok(ScanSource::File(BufReader::new(file))),
                Err(e) => Err(Error::InternalError {
                    message: e.to_string(),
                }),
            }
        })
    }
}

/// Iterator for DBC (compressed) files
struct DbcIter {
    sources: Vec<ScanSource>,
    idx: usize,
}

impl DbcIter {
    fn new(sources: Vec<ScanSource>) -> Self {
        Self { sources, idx: 0 }
    }
}

impl Iterator for DbcIter {
    type Item = Result<ScanSource, Error>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.idx < self.sources.len() {
            let source = self.sources.swap_remove(self.idx);
            Some(Ok(source))
        } else {
            None
        }
    }
}

type SourceIter = Chain<Chain<DbcIter, PathIter>, BytesIter>;

#[pyclass(unsendable)] // Keep unsendable due to encoding trait objects
pub struct PyDbaseIter(Fuse<DbfIter<ScanSource, SourceIter>>);

#[pymethods]
impl PyDbaseIter {
    fn next(&mut self) -> PyResult<Option<PyDataFrame>> {
        let PyDbaseIter(inner) = self;
        Ok(inner.next().transpose().map(|op| op.map(PyDataFrame))?)
    }
}

struct PyReader(Arc<PyObject>);

impl Read for PyReader {
    fn read(&mut self, mut buf: &mut [u8]) -> io::Result<usize> {
        Python::with_gil(|py| {
            let res = self.0.bind(py).call_method1("read", (buf.len(),))?;
            let bytes = res.downcast_into::<PyBytes>()?;
            let raw = bytes.as_bytes();
            buf.write_all(raw)?;
            Ok(raw.len())
        })
        .map_err(|err: PyErr| io::Error::other(err.to_string()))
    }
}

impl Seek for PyReader {
    fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
        match pos {
            SeekFrom::Start(pos) => Python::with_gil(|py| {
                let reader = self.0.bind(py);
                let res = reader.call_method1("seek", (pos,))?;
                res.extract()
            })
            .map_err(|err: PyErr| io::Error::other(err.to_string())),
            SeekFrom::Current(offset) => Python::with_gil(|py| {
                let reader = self.0.bind(py);
                let res = reader.call_method0("tell")?;
                let current: u64 = res.extract()?;
                let pos = if offset < 0 {
                    current.saturating_sub(offset.unsigned_abs())
                } else {
                    current.saturating_add(offset.unsigned_abs())
                };
                let res = reader.call_method1("seek", (pos,))?;
                res.extract()
            })
            .map_err(|err: PyErr| io::Error::other(err.to_string())),
            SeekFrom::End(_) => Err(io::Error::new(
                ErrorKind::Unsupported,
                "Seeking from end not supported in streaming mode",
            )),
        }
    }
}

struct PyWriter(PyObject);

impl Write for PyWriter {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        Python::with_gil(|py| {
            let res = self.0.bind(py).call_method1("write", (buf,))?;
            res.extract()
        })
        .map_err(|err: PyErr| io::Error::other(err.to_string()))
    }

    fn flush(&mut self) -> io::Result<()> {
        Python::with_gil(|py| {
            self.0.bind(py).call_method0("flush")?;
            Ok(())
        })
        .map_err(|err: PyErr| io::Error::other(err.to_string()))
    }
}

impl Seek for PyWriter {
    fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
        match pos {
            SeekFrom::Start(pos) => Python::with_gil(|py| {
                let writter = self.0.bind(py);
                let res = writter.call_method1("seek", (pos,))?;
                res.extract()
            })
            .map_err(|err: PyErr| io::Error::other(err.to_string())),
            SeekFrom::Current(offset) => Python::with_gil(|py| {
                let writer = self.0.bind(py);
                let res = writer.call_method0("tell")?;
                let current: u64 = res.extract()?;
                let pos = if offset < 0 {
                    current.saturating_sub(offset.unsigned_abs())
                } else {
                    current.saturating_add(offset.unsigned_abs())
                };
                let res = writer.call_method1("seek", (pos,))?;
                res.extract()
            })
            .map_err(|err: PyErr| io::Error::other(err.to_string())),
            SeekFrom::End(_) => Err(io::Error::new(
                ErrorKind::Unsupported,
                "Seeking from end not supported in streaming mode",
            )),
        }
    }
}

#[pyclass(unsendable)] // Keep unsendable due to encoding trait objects
pub struct DbaseSource {
    paths: Arc<[String]>,
    buffs: Arc<[Arc<PyObject>]>,
    single_col_name: Option<PlSmallStr>,
    schema: Option<Arc<Schema>>,
    last_scanner: Option<DbfReader<ScanSource, SourceIter>>,
    // DBF-specific options
    encoding: Option<String>,
    character_trim: Option<String>,
    skip_deleted: Option<bool>,
    validate_schema: Option<bool>,
    // DBC (compressed) support
    compressed: Option<bool>,
}

impl DbaseSource {
    /// If we created a scanner to get the schema, then take it, otherwise create a new one.
    fn take_scanner(&mut self, py: Python<'_>) -> Result<DbfReader<ScanSource, SourceIter>, Error> {
        if let Some(scanner) = self.last_scanner.take() {
            Ok(scanner)
        } else {
            // For DBC files, we need to handle them properly by creating a single iterator chain
            if self.compressed.unwrap_or(false) && !self.paths.is_empty() {
                let options = self.build_dbf_options();

                // Step 1: Extract schema from the first DBC file only
                let first_path = &self.paths[0];
                match create_dbf_reader_from_dbc(
                    first_path,
                    self.single_col_name.clone(),
                    Some(options.clone()),
                ) {
                    Ok(first_dbc_reader) => {
                        // Store the schema from the first file
                        self.schema = Some(first_dbc_reader.schema());
                    }
                    Err(e) => {
                        return Err(Error::InternalError {
                            message: format!(
                                "Failed to extract schema from first DBC file {}: {}",
                                first_path, e
                            ),
                        });
                    }
                }

                // Step 2: Create all DBC ScanSources
                let dbc_sources = self.create_scan_sources_from_dbc_paths(py)?;

                // Step 3: Build single iterator chain for all DBC files
                let dbc_iter = DbcIter::new(dbc_sources);
                let path_iter = PathIter::new(Vec::new().into()); // Empty for DBC-only mode
                let bytes_iter = BytesIter::new(Vec::new().into()); // Empty for DBC-only mode
                let combined_iter = dbc_iter.chain(path_iter).chain(bytes_iter);

                // Step 4: Create single DbfReader with the combined iterator
                let scanner =
                    DbfReader::try_new(combined_iter, self.single_col_name.clone(), options)
                        .map_err(|e| Error::InternalError {
                            message: format!("Failed to create scanner for DBC files: {}", e),
                        })?;

                Ok(scanner)
            } else {
                // Regular DBF file handling
                let dbc_iter = DbcIter::new(Vec::new());
                let path_iter = PathIter::new(self.paths.clone());
                let bytes_iter = BytesIter::new(self.buffs.clone());

                // Create a triple chain: DBC -> Path -> Bytes
                let combined_iter = dbc_iter.chain(path_iter).chain(bytes_iter);

                // create a new scanner from the combined sources
                let options = self.build_dbf_options();
                let scanner =
                    DbfReader::try_new(combined_iter, self.single_col_name.clone(), options)
                        .map_err(|e| Error::InternalError {
                            message: format!("Failed to create scanner: {}", e),
                        })?;

                // ensure we store the schema
                if self.schema.is_none() {
                    self.schema = Some(scanner.schema());
                }

                Ok(scanner)
            }
        }
    }

    fn build_dbf_options(&self) -> DbfReadOptions {
        let mut options = DbfReadOptions::default();

        if let Some(encoding) = &self.encoding {
            options.encoding = encoding.clone();
        }

        if let Some(trim) = &self.character_trim {
            options.character_trim = match trim.as_str() {
                "begin" => dbase::TrimOption::Begin,
                "end" => dbase::TrimOption::End,
                "begin_end" | "both" => dbase::TrimOption::BeginEnd,
                "none" => dbase::TrimOption::BeginEnd, // None is not available, use BeginEnd as default
                _ => dbase::TrimOption::BeginEnd,
            };
        }

        if let Some(skip_deleted) = self.skip_deleted {
            options.skip_deleted = skip_deleted;
        }

        if let Some(validate_schema) = self.validate_schema {
            options.validate_schema = validate_schema;
        }

        options
    }

    /// Helper function to create a ScanSource from a DBC file
    ///
    /// This function converts a DBC file into a ScanSource that can be used
    /// by the regular DbfReader, enabling support for multiple DBC files.
    fn create_scan_source_from_dbc(&self, dbc_path: &str) -> Result<ScanSource, Error> {
        // Open the DBC file
        let file = std::fs::File::open(dbc_path)
            .map_err(|e| Error::DbcError(format!("Failed to open DBC file: {}", e)))?;

        let dbc_reader = DbcReader::new(file)
            .map_err(|e| Error::DbcError(format!("Failed to create DBC reader: {}", e)))?;

        // Wrap the DbcReader in a Box and then in BufReader
        let boxed_reader: Box<dyn ReadSeek> = Box::new(dbc_reader);
        Ok(ScanSource::Dbc(std::io::BufReader::new(boxed_reader)))
    }

    /// Helper function to create multiple ScanSources from DBC files
    ///
    /// This function converts multiple DBC files into ScanSources that can be used
    /// by the regular DbfReader, enabling support for multiple DBC files.
    /// 🚀 Uses Rayon for parallel processing of multiple DBC files.
    /// 🐍 GIL-aware: releases GIL for CPU-bound operations.
    fn create_scan_sources_from_dbc_paths(
        &self,
        _py: Python<'_>,
    ) -> Result<Vec<ScanSource>, Error> {
        // Sequential processing of DBC files due to trait object limitations
        // TODO: Re-enable parallel processing when encoding trait objects are Send + Sync
        let mut sources = Vec::new();

        for path in &*self.paths {
            // Use the existing create_scan_source_from_dbc method
            let source = self.create_scan_source_from_dbc(path)?;
            sources.push(source);
        }

        Ok(sources)
    }
}

#[pymethods]
impl DbaseSource {
    #[new]
    #[pyo3(signature = (paths, buffs, single_col_name, encoding, character_trim, skip_deleted, validate_schema, compressed))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        paths: Vec<String>,
        buffs: Vec<PyObject>,
        single_col_name: Option<String>,
        encoding: Option<String>,
        character_trim: Option<String>,
        skip_deleted: Option<bool>,
        validate_schema: Option<bool>,
        compressed: Option<bool>,
    ) -> Self {
        Self {
            paths: paths.into(),
            buffs: buffs.into_iter().map(Arc::new).collect(),
            single_col_name: single_col_name.map(PlSmallStr::from),
            schema: None,
            last_scanner: None,
            encoding,
            character_trim,
            skip_deleted,
            validate_schema,
            compressed, // Keep as Option<bool>
        }
    }

    fn schema(&mut self) -> PyResult<PySchema> {
        // Extract needed data before mutable borrow
        let buffs = self.buffs.clone();
        let paths = self.paths.clone();
        let single_col_name = self.single_col_name.clone();
        let compressed = self.compressed;
        let options = self.build_dbf_options();

        Ok(PySchema(match &mut self.schema {
            Some(schema) => schema.clone(),
            loc @ None => {
                let new_schema = if let Some(scanner) = &self.last_scanner {
                    scanner.schema()
                } else {
                    // Check if we should use compressed (DBC) reading for schema
                    if compressed.unwrap_or(false) && !paths.is_empty() {
                        let first_path = &paths[0];

                        // Use DBC reader for schema extraction
                        match create_dbf_reader_from_dbc(
                            first_path,
                            single_col_name.clone(),
                            Some(options.clone()),
                        ) {
                            Ok(dbc_reader) => {
                                // Note: We don't store the DBC reader as last_scanner
                                // because it has a different type than our regular scanner
                                dbc_reader.schema()
                            }
                            Err(_e) => {
                                // Fall back to regular scanner if DBC fails
                                let dbc_iter = DbcIter::new(Vec::new()); // No DBC sources for fallback
                                let path_iter = PathIter::new(paths.clone());
                                let bytes_iter = BytesIter::new(buffs.clone());
                                let combined_iter = dbc_iter.chain(path_iter).chain(bytes_iter);

                                let new_scanner =
                                    DbfReader::try_new(combined_iter, single_col_name, options)
                                        .map_err(|e| Error::InternalError {
                                            message: format!(
                                                "Failed to create scanner for schema: {}",
                                                e
                                            ),
                                        })?;
                                let schema = new_scanner.schema();
                                self.last_scanner = Some(new_scanner);
                                schema
                            }
                        }
                    } else {
                        // Regular DBF schema extraction
                        let dbc_iter = DbcIter::new(Vec::new()); // No DBC sources for regular mode
                        let path_iter = PathIter::new(paths.clone());
                        let bytes_iter = BytesIter::new(buffs.clone());
                        let combined_iter = dbc_iter.chain(path_iter).chain(bytes_iter);

                        let new_scanner =
                            DbfReader::try_new(combined_iter, single_col_name, options).map_err(
                                |e| Error::InternalError {
                                    message: format!("Failed to create scanner for schema: {}", e),
                                },
                            )?;
                        let schema = new_scanner.schema();
                        self.last_scanner = Some(new_scanner);
                        schema
                    }
                };
                loc.insert(new_schema).clone()
            }
        }))
    }

    #[pyo3(signature = (batch_size, with_columns))]
    #[allow(clippy::needless_pass_by_value)]
    fn batch_iter(
        &mut self,
        py: Python<'_>,
        batch_size: usize,
        with_columns: Option<Vec<String>>,
    ) -> PyResult<PyDbaseIter> {
        // Create scanner with GIL held (can't move &self into allow_threads)
        let scanner = self
            .take_scanner(py)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to take scanner: {}", e)))?;

        // Create iterator with GIL held (contains non-Send trait objects)
        let iter = scanner
            .try_into_iter(Some(batch_size), with_columns.as_deref())
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create iterator: {}", e)))?;

        Ok(PyDbaseIter(iter))
    }

    #[pyo3(signature = (batch_size, with_columns, progress))]
    #[allow(clippy::needless_pass_by_value)]
    fn batch_iter_with_progress(
        &mut self,
        py: Python<'_>,
        batch_size: usize,
        with_columns: Option<Vec<String>>,
        progress: bool,
    ) -> PyResult<PyDbaseIter> {
        // Create scanner with GIL held (can't move &self into allow_threads)
        let scanner = self
            .take_scanner(py)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to take scanner: {}", e)))?;

        // Create progress tracker if requested
        let progress_tracker =
            if progress && self.compressed.unwrap_or(false) && !self.paths.is_empty() {
                // Get record counts for all files
                let mut file_infos = Vec::new();
                for path in &*self.paths {
                    match create_dbf_reader_from_dbc(
                        path,
                        self.single_col_name.clone(),
                        Some(self.build_dbf_options()),
                    ) {
                        Ok(dbc_reader) => {
                            let file_as_path = Path::new(path);
                            let file_extension =
                                file_as_path.extension().unwrap().to_str().unwrap();
                            let file_name = file_as_path.file_name().unwrap().to_str().unwrap();
                            file_infos.push(DbaseFileInfo::new(
                                file_name.to_string(),
                                dbc_reader.total_records() as u64,
                                file_extension.to_string(),
                            ));
                        }
                        Err(_) => {
                            // If we can't get the record count, skip progress for this file
                            file_infos.push(DbaseFileInfo::default());
                        }
                    }
                }

                if file_infos.iter().any(|info| info.get_file_size() > 0) {
                    Some(create_multi_file_progress(file_infos))
                } else {
                    None
                }
            } else {
                None
            };

        // Convert column names to indices
        let with_columns_indices = if let Some(columns) = with_columns {
            let indexes = columns
                .iter()
                .map(|name| {
                    scanner.schema().index_of(name).ok_or_else(|| {
                        PyRuntimeError::new_err(format!("Column '{}' not found", name))
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            Some(indexes.into())
        } else {
            None
        };

        // Create iterator with progress tracking
        let iter = scanner.into_iter_with_progress(
            Some(batch_size),
            with_columns_indices,
            progress_tracker,
        );

        Ok(PyDbaseIter(iter))
    }
}

// ============================================================================
// Write Functions (following polars-avro pattern)
// ============================================================================

#[pyfunction]
#[pyo3(signature = (frames, dest, encoding, overwrite, memo_threshold))]
#[allow(clippy::too_many_arguments)]
fn write_dbase_file(
    py: Python<'_>,
    frames: Vec<PyDataFrame>,
    dest: String,
    encoding: Option<String>,
    overwrite: Option<bool>,
    memo_threshold: Option<usize>,
) -> PyResult<()> {
    // Build WriteOptions from parameters
    let mut options = WriteOptions::default();

    if let Some(enc) = encoding {
        options.encoding = enc;
    }

    if let Some(overwrite) = overwrite {
        options.overwrite = overwrite;
    }

    if let Some(threshold) = memo_threshold {
        options.memo_threshold = threshold;
    }

    // 🚀 Release GIL for CPU-bound DataFrame conversion
    let dataframes: Vec<_> = py.allow_threads(|| {
        // Convert PyDataFrames to DataFrames in parallel without GIL
        frames
            .into_par_iter()
            .map(|PyDataFrame(frame)| frame)
            .collect()
    });

    // 🚀 Release GIL for CPU-bound file writing operations
    py.allow_threads(|| {
        // Use existing write_dbase_file function - handle single DataFrame case
        if dataframes.len() == 1 {
            write_dbase_file_internal(&dataframes[0], dest, Some(options))
                .map_err(|e| PyRuntimeError::new_err(format!("Failed to write dBase file: {}", e)))
        } else {
            // For multiple DataFrames, use the chunk-based write_dbase function
            let file = std::fs::File::create(dest)
                .map_err(|e| PyRuntimeError::new_err(format!("Failed to create file: {}", e)))?;
            write_dbase(&dataframes, file, options)
                .map_err(|e| PyIOError::new_err(format!("Failed to write dBase file: {}", e)))
        }
    })
}

#[pyfunction]
#[pyo3(signature = (frames, buff, encoding, memo_threshold))]
#[allow(clippy::too_many_arguments)]
fn write_dbase_buff(
    py: Python<'_>,
    frames: Vec<PyDataFrame>,
    buff: PyObject,
    encoding: Option<String>,
    memo_threshold: Option<usize>,
) -> PyResult<()> {
    // Build WriteOptions from parameters
    let mut options = WriteOptions::default();

    if let Some(enc) = encoding {
        options.encoding = enc;
    }

    if let Some(threshold) = memo_threshold {
        options.memo_threshold = threshold;
    }

    // 🚀 Release GIL for CPU-bound DataFrame conversion
    let dataframes: Vec<_> = py.allow_threads(|| {
        // Convert PyDataFrames to DataFrames in parallel without GIL
        frames
            .into_par_iter()
            .map(|PyDataFrame(frame)| frame)
            .collect()
    });

    // 🚀 Release GIL for CPU-bound buffer writing operations
    py.allow_threads(|| {
        // Create BufWriter around PyWriter
        let buff = BufWriter::new(PyWriter(buff));

        // Use existing write_dbase function
        write_dbase(&dataframes, buff, options)
            .map_err(|e| PyIOError::new_err(format!("Failed to write dBase to buffer: {}", e)))
    })
}

// ============================================================================
// Utility functions
// ============================================================================
#[pyfunction]
#[pyo3(signature = (path))]
fn get_record_count(path: String) -> PyResult<usize> {
    if path.is_empty() {
        return Err(PyValueError::new_err("Empty path"));
    }
    let file_as_path = Path::new(&path);
    let file_extension = file_as_path.extension().unwrap().to_str().unwrap();

    match Some(file_extension.eq_ignore_ascii_case("dbc")) {
        Some(true) => {
            let dbc_reader =
                create_dbf_reader_from_dbc(path, None, Some(DbfReadOptions::default())).map_err(
                    |e| PyRuntimeError::new_err(format!("Failed to open DBC file: {}", e)),
                )?;
            Ok(dbc_reader.total_records() as usize)
        }
        Some(false) => {
            let dbase_file = DbaseFile::open_read_only(path).map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to open dBase file: {}", e))
            })?;
            Ok(dbase_file.num_records())
        }
        None => {
            let dbase_file = DbaseFile::open_read_only(file_as_path).map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to open dBase file: {}", e))
            })?;
            Ok(dbase_file.num_records())
        }
    }
}

// ============================================================================
// Error Mapping (following polars-avro pattern)
// ============================================================================

impl From<Error> for PyErr {
    fn from(value: Error) -> Self {
        match value {
            Error::InternalError { message } => {
                PyRuntimeError::new_err(format!("Internal error: {}", message))
            }
            Error::DbcError(message) => PyRuntimeError::new_err(format!("DBC error: {}", message)),
            Error::EncodingError(message) => {
                PyValueError::new_err(format!("Encoding error: {}", message))
            }
            Error::SchemaMismatch(message) => {
                PyValueError::new_err(format!("Schema mismatch: {}", message))
            }
            Error::NonMatchingSchemas => PyValueError::new_err("Non-matching schemas"),
            Error::UnsupportedFieldType(field_type) => {
                PyValueError::new_err(format!("Unsupported field type: {:?}", field_type))
            }
            Error::InvalidConversion(message) => {
                PyValueError::new_err(format!("Invalid conversion: {}", message))
            }
            Error::CompressionError(message) => {
                PyRuntimeError::new_err(format!("Compression error: {}", message))
            }
            Error::HuffmanBridgeError(message) => {
                PyRuntimeError::new_err(format!("Huffman bridge error: {}", message))
            }
            Error::LzssError(message) => {
                PyRuntimeError::new_err(format!("LZSS error: {}", message))
            }
            Error::ConstrictionError(message) => {
                PyRuntimeError::new_err(format!("Constriction error: {}", message))
            }
        }
    }
}

// ============================================================================
// Exception definitions (following polars-avro pattern)
// ============================================================================

create_exception!(exceptions, DbaseError, PyException);
create_exception!(exceptions, EmptySources, PyValueError);
create_exception!(exceptions, SchemaMismatch, PyValueError);
create_exception!(exceptions, EncodingError, PyValueError);
create_exception!(exceptions, DbcError, PyValueError);

// ============================================================================
// Module Registration (following polars-avro pattern)
// ============================================================================

#[pymodule]
#[pyo3(name = "_dbase_rs")]
fn polars_dbase(py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    // Register classes
    m.add_class::<DbaseSource>()?;

    // Register exceptions
    m.add("DbaseError", py.get_type::<DbaseError>())?;
    m.add("EmptySources", py.get_type::<EmptySources>())?;
    m.add("SchemaMismatch", py.get_type::<SchemaMismatch>())?;
    m.add("EncodingError", py.get_type::<EncodingError>())?;
    m.add("DbcError", py.get_type::<DbcError>())?;

    // Register write functions
    m.add_function(wrap_pyfunction!(write_dbase_file, m)?)?;
    m.add_function(wrap_pyfunction!(write_dbase_buff, m)?)?;
    m.add_function(wrap_pyfunction!(get_record_count, m)?)?;

    Ok(())
}
