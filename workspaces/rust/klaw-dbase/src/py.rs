//! pyo3 bindings
use rayon::prelude::*;
use std::fs::File;
use std::io::{self, BufReader, BufWriter, ErrorKind, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::Arc;

use polars::prelude::{PlSmallStr, Schema};
use pyo3::exceptions::{PyException, PyIOError, PyRuntimeError, PyValueError};
use pyo3::types::{PyAnyMethods, PyModule, PyModuleMethods};
use pyo3::{
    Bound, PyErr, PyObject, PyResult, Python, create_exception, pyclass, pyfunction, pymethods,
    pymodule, wrap_pyfunction,
};
use pyo3_polars::{PyDataFrame, PySchema};

use dbase::File as DbaseFile;

use crate::read_compressed::create_dbf_reader_from_dbc;
use crate::{
    error::Error,
    parallel_read::{ParallelDbfReader, ParallelReadConfig},
    read::{DbfReadOptions, resolve_encoding_string},
    write::{WriteOptions, write_dbase, write_dbase_file as write_dbase_file_internal},
};

/// Python iterator for parallel reading of multiple dBase files.
///
/// Uses a thread pool with crossbeam channels for efficient parallel I/O.
/// Each worker reads files independently and sends batches through a channel.
#[pyclass]
pub struct PyParallelDbaseIter {
    reader: ParallelDbfReader,
}

#[pymethods]
impl PyParallelDbaseIter {
    fn next(&mut self) -> PyResult<Option<PyDataFrame>> {
        match self.reader.next() {
            Some(Ok(df)) => Ok(Some(PyDataFrame(df))),
            Some(Err(e)) => Err(e.into()),
            None => Ok(None),
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

/// Python dBase source for reading DBF/DBC files.
///
/// Used primarily for schema extraction. Iteration is handled by ParallelDbfReader.
#[pyclass]
pub struct DbaseSource {
    paths: Arc<[String]>,
    single_col_name: Option<PlSmallStr>,
    schema: Option<Arc<Schema>>,
    // DBF-specific options
    encoding: Option<String>,
    character_trim: Option<String>,
    skip_deleted: Option<bool>,
    validate_schema: Option<bool>,
    // DBC (compressed) support
    compressed: Option<bool>,
}

impl DbaseSource {
    fn build_dbf_options(&self) -> DbfReadOptions {
        let mut options = DbfReadOptions::default();

        if let Some(encoding_str) = &self.encoding {
            options.encoding = resolve_encoding_string(encoding_str).unwrap_or_default();
        }

        if let Some(trim) = &self.character_trim {
            options.character_trim = match trim.as_str() {
                "begin" => dbase::TrimOption::Begin,
                "end" => dbase::TrimOption::End,
                "begin_end" | "both" => dbase::TrimOption::BeginEnd,
                "none" => dbase::TrimOption::BeginEnd,
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
}

#[pymethods]
impl DbaseSource {
    #[new]
    #[pyo3(signature = (paths, single_col_name, encoding, character_trim, skip_deleted, validate_schema, compressed))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        paths: Vec<String>,
        single_col_name: Option<String>,
        encoding: Option<String>,
        character_trim: Option<String>,
        skip_deleted: Option<bool>,
        validate_schema: Option<bool>,
        compressed: Option<bool>,
    ) -> Self {
        Self {
            paths: paths.into(),
            single_col_name: single_col_name.map(PlSmallStr::from),
            schema: None,
            encoding,
            character_trim,
            skip_deleted,
            validate_schema,
            compressed,
        }
    }

    fn schema(&mut self) -> PyResult<PySchema> {
        let paths = self.paths.clone();
        let single_col_name = self.single_col_name.clone();
        let compressed = self.compressed;
        let options = self.build_dbf_options();

        Ok(PySchema(match &mut self.schema {
            Some(schema) => schema.clone(),
            loc @ None => {
                if paths.is_empty() {
                    return Err(PyValueError::new_err("No file paths provided"));
                }

                let first_path = &paths[0];
                let is_dbc =
                    compressed.unwrap_or(false) || first_path.to_lowercase().ends_with(".dbc");

                let new_schema = if is_dbc {
                    match create_dbf_reader_from_dbc(
                        first_path,
                        single_col_name.clone(),
                        Some(options.clone()),
                    ) {
                        Ok(dbc_reader) => dbc_reader.schema(),
                        Err(e) => {
                            return Err(PyRuntimeError::new_err(format!(
                                "Failed to read DBC schema: {}",
                                e
                            )));
                        }
                    }
                } else {
                    let file = File::open(first_path).map_err(|e| {
                        PyRuntimeError::new_err(format!("Failed to open file: {}", e))
                    })?;
                    let reader = crate::read::DbfReader::new_with_options(
                        vec![BufReader::new(file)],
                        single_col_name,
                        options,
                    )
                    .map_err(|e| {
                        PyRuntimeError::new_err(format!("Failed to read schema: {}", e))
                    })?;
                    reader.schema()
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
    ) -> PyResult<PyParallelDbaseIter> {
        if self.paths.is_empty() {
            return Err(PyValueError::new_err("No file paths provided"));
        }

        let config = ParallelReadConfig {
            batch_size,
            options: self.build_dbf_options(),
            single_col_name: self.single_col_name.clone(),
            with_columns: with_columns.map(|cols| cols.into_iter().map(PlSmallStr::from).collect()),
            progress: false,
            ..Default::default()
        };

        let paths: Vec<String> = self.paths.iter().cloned().collect();
        let reader = py
            .allow_threads(|| ParallelDbfReader::new(paths, config))
            .map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to create parallel reader: {}", e))
            })?;

        Ok(PyParallelDbaseIter { reader })
    }

    #[pyo3(signature = (batch_size, with_columns, progress))]
    #[allow(clippy::needless_pass_by_value)]
    fn batch_iter_with_progress(
        &mut self,
        py: Python<'_>,
        batch_size: usize,
        with_columns: Option<Vec<String>>,
        progress: bool,
    ) -> PyResult<PyParallelDbaseIter> {
        if self.paths.is_empty() {
            return Err(PyValueError::new_err("No file paths provided"));
        }

        let config = ParallelReadConfig {
            batch_size,
            options: self.build_dbf_options(),
            single_col_name: self.single_col_name.clone(),
            with_columns: with_columns.map(|cols| cols.into_iter().map(PlSmallStr::from).collect()),
            progress,
            ..Default::default()
        };

        let paths: Vec<String> = self.paths.iter().cloned().collect();
        let reader = py
            .allow_threads(|| ParallelDbfReader::new(paths, config))
            .map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to create parallel reader: {}", e))
            })?;

        Ok(PyParallelDbaseIter { reader })
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

    let dataframes: Vec<_> = py.allow_threads(|| {
        frames
            .into_par_iter()
            .map(|PyDataFrame(frame)| frame)
            .collect()
    });

    py.allow_threads(|| {
        if dataframes.len() == 1 {
            write_dbase_file_internal(&dataframes[0], dest, Some(options))
                .map_err(|e| PyRuntimeError::new_err(format!("Failed to write dBase file: {}", e)))
        } else {
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
    let mut options = WriteOptions::default();

    if let Some(enc) = encoding {
        options.encoding = enc;
    }

    if let Some(threshold) = memo_threshold {
        options.memo_threshold = threshold;
    }

    let dataframes: Vec<_> = py.allow_threads(|| {
        frames
            .into_par_iter()
            .map(|PyDataFrame(frame)| frame)
            .collect()
    });

    py.allow_threads(|| {
        let buff = BufWriter::new(PyWriter(buff));
        write_dbase(&dataframes, buff, options)
            .map_err(|e| PyIOError::new_err(format!("Failed to write dBase to buffer: {}", e)))
    })
}

// ============================================================================
// Parallel Read Functions
// ============================================================================

/// Create a parallel iterator for reading multiple dBase files
///
/// This function creates a parallel reader that distributes files across worker threads.
/// Each worker reads files independently and sends batches through a channel.
#[pyfunction]
#[pyo3(signature = (paths, batch_size=None, n_workers=None, encoding=None, character_trim=None, skip_deleted=None, with_columns=None, progress=None))]
#[allow(clippy::too_many_arguments)]
fn create_parallel_reader(
    py: Python<'_>,
    paths: Vec<String>,
    batch_size: Option<usize>,
    n_workers: Option<usize>,
    encoding: Option<String>,
    character_trim: Option<String>,
    skip_deleted: Option<bool>,
    with_columns: Option<Vec<String>>,
    progress: Option<bool>,
) -> PyResult<PyParallelDbaseIter> {
    if paths.is_empty() {
        return Err(PyValueError::new_err("No file paths provided"));
    }

    let mut config = ParallelReadConfig::default();

    if let Some(size) = batch_size {
        config.batch_size = size;
    }

    if let Some(workers) = n_workers {
        config.n_workers = Some(workers);
    }

    if let Some(enc) = encoding {
        config.options.encoding = resolve_encoding_string(&enc)
            .map_err(|e| PyValueError::new_err(format!("Invalid encoding: {}", e)))?;
    }

    if let Some(trim) = character_trim {
        config.options.character_trim = match trim.as_str() {
            "begin" => dbase::TrimOption::Begin,
            "end" => dbase::TrimOption::End,
            "begin_end" | "both" => dbase::TrimOption::BeginEnd,
            "none" => dbase::TrimOption::BeginEnd,
            _ => dbase::TrimOption::BeginEnd,
        };
    }

    if let Some(skip) = skip_deleted {
        config.options.skip_deleted = skip;
    }

    if let Some(columns) = with_columns {
        config.with_columns = Some(columns.into_iter().map(PlSmallStr::from).collect());
    }

    if let Some(prog) = progress {
        config.progress = prog;
    }

    let reader = py
        .allow_threads(|| ParallelDbfReader::new(paths, config))
        .map_err(|e| PyRuntimeError::new_err(format!("Failed to create parallel reader: {}", e)))?;

    Ok(PyParallelDbaseIter { reader })
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
    m.add_class::<PyParallelDbaseIter>()?;

    // Register exceptions
    m.add("DbaseError", py.get_type::<DbaseError>())?;
    m.add("EmptySources", py.get_type::<EmptySources>())?;
    m.add("SchemaMismatch", py.get_type::<SchemaMismatch>())?;
    m.add("EncodingError", py.get_type::<EncodingError>())?;
    m.add("DbcError", py.get_type::<DbcError>())?;

    // Register read functions
    m.add_function(wrap_pyfunction!(create_parallel_reader, m)?)?;

    // Register write functions
    m.add_function(wrap_pyfunction!(write_dbase_file, m)?)?;
    m.add_function(wrap_pyfunction!(write_dbase_buff, m)?)?;
    m.add_function(wrap_pyfunction!(get_record_count, m)?)?;

    Ok(())
}
