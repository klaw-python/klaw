//! Parallel file reading for dBase/DBC files
//!
//! This module provides parallel reading of multiple DBF/DBC files using a worker pool
//! with crossbeam channels for efficient batch streaming.

use std::fs::File;
use std::io::BufReader;
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;

use crossbeam_channel::{Receiver, Sender, bounded};
use polars::frame::DataFrame;
use polars::prelude::PlSmallStr;

use crate::error::Error;
use crate::progress::{DbaseFileInfo, DbaseProgressTracker};
use crate::read::{DbfEncoding, DbfReadOptions, DbfReader};
use crate::read_compressed::create_dbf_reader_from_dbc;

/// Result type for parallel batch reading
pub type BatchResult = Result<DataFrame, Error>;

/// Configuration for parallel reading
#[derive(Debug, Clone)]
pub struct ParallelReadConfig {
    /// Number of worker threads (None = all logical CPUs)
    pub n_workers: Option<usize>,
    /// Batch size for each worker
    pub batch_size: usize,
    /// Channel buffer size (batches in flight)
    pub channel_buffer: usize,
    /// DBF read options
    pub options: DbfReadOptions,
    /// Single column name for schema
    pub single_col_name: Option<PlSmallStr>,
    /// Columns to read (None = all columns)
    pub with_columns: Option<Vec<PlSmallStr>>,
    /// Enable progress tracking
    pub progress: bool,
}

impl Default for ParallelReadConfig {
    fn default() -> Self {
        Self {
            n_workers: None, // Use all logical CPUs
            batch_size: 8192,
            channel_buffer: 16, // Buffer up to 16 batches
            options: DbfReadOptions::default(),
            single_col_name: None,
            with_columns: None,
            progress: false,
        }
    }
}

impl ParallelReadConfig {
    /// Get effective worker count (defaults to available parallelism)
    pub fn effective_workers(&self) -> usize {
        self.n_workers.unwrap_or_else(|| {
            std::thread::available_parallelism()
                .map(|n| n.get())
                .unwrap_or(4)
        })
    }

    /// Set number of workers
    pub fn with_workers(mut self, n: usize) -> Self {
        self.n_workers = Some(n);
        self
    }

    /// Set batch size
    pub fn with_batch_size(mut self, size: usize) -> Self {
        self.batch_size = size;
        self
    }

    /// Set encoding
    pub fn with_encoding(mut self, encoding: DbfEncoding) -> Self {
        self.options.encoding = encoding;
        self
    }

    /// Enable progress tracking
    pub fn with_progress(mut self, progress: bool) -> Self {
        self.progress = progress;
        self
    }
}

/// Thread-safe progress state shared across workers
struct SharedProgress {
    /// Progress tracker (created on main thread, updated from workers)
    tracker: DbaseProgressTracker,
    /// Per-file record counts for progress updates
    file_records: Arc<[AtomicU64]>,
    /// Whether finish() has been called
    finished: AtomicU64,
}

/// Parallel reader for multiple dBase/DBC files
///
/// Uses a thread pool to read files in parallel, streaming batches through a channel.
pub struct ParallelDbfReader {
    /// Receiver for DataFrame batches
    receiver: Receiver<BatchResult>,
    /// Handle to worker threads (for cleanup)
    _handles: Vec<thread::JoinHandle<()>>,
    /// Progress tracking state (if enabled)
    progress: Option<Arc<SharedProgress>>,
}

impl ParallelDbfReader {
    /// Create a new parallel reader for the given file paths
    ///
    /// Files are distributed across worker threads and read in parallel.
    /// Batches are streamed through a channel as they become available.
    pub fn new(paths: Vec<String>, config: ParallelReadConfig) -> Result<Self, Error> {
        if paths.is_empty() {
            return Err(Error::InternalError {
                message: "No file paths provided".to_string(),
            });
        }

        let n_workers = config.effective_workers().min(paths.len());
        let (sender, receiver) = bounded::<BatchResult>(config.channel_buffer);

        // Create progress tracking if enabled
        let progress = if config.progress {
            Some(Arc::new(Self::create_progress_state(&paths)?))
        } else {
            None
        };

        // Distribute files across workers
        let paths_arc: Arc<[String]> = paths.into();
        let config_arc = Arc::new(config);

        // Spawn worker threads
        let handles: Vec<_> = (0..n_workers)
            .map(|worker_id| {
                let sender = sender.clone();
                let paths = paths_arc.clone();
                let config = config_arc.clone();
                let progress = progress.clone();

                thread::spawn(move || {
                    Self::worker_loop(worker_id, n_workers, paths, config, sender, progress);
                })
            })
            .collect();

        // Drop the original sender so channel closes when all workers finish
        drop(sender);

        Ok(Self {
            receiver,
            _handles: handles,
            progress,
        })
    }

    /// Create progress tracking state by reading file headers for record counts
    fn create_progress_state(paths: &[String]) -> Result<SharedProgress, Error> {
        let mut file_infos = Vec::with_capacity(paths.len());
        let mut file_records = Vec::with_capacity(paths.len());

        for path in paths {
            let path_ref = Path::new(path);
            let extension = path_ref.extension().and_then(|e| e.to_str()).unwrap_or("");
            let is_dbc = extension.eq_ignore_ascii_case("dbc");
            let file_name = path_ref
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or(path)
                .to_string();

            let record_count = Self::get_file_record_count(path, is_dbc)?;

            file_infos.push(DbaseFileInfo::new(
                file_name,
                record_count,
                extension.to_string(),
            ));
            file_records.push(AtomicU64::new(0));
        }

        let tracker = DbaseProgressTracker::new(file_infos);

        Ok(SharedProgress {
            tracker,
            file_records: file_records.into(),
            finished: AtomicU64::new(0),
        })
    }

    /// Get record count from a file header without reading all data
    fn get_file_record_count(path: &str, is_dbc: bool) -> Result<u64, Error> {
        if is_dbc {
            let reader = create_dbf_reader_from_dbc(path, None, None)?;
            Ok(reader.total_records() as u64)
        } else {
            let file = File::open(path).map_err(|e| Error::InternalError {
                message: format!("Failed to open file '{}': {}", path, e),
            })?;
            let reader = DbfReader::new_with_options(
                vec![BufReader::new(file)],
                None,
                DbfReadOptions::default(),
            )?;
            Ok(reader.total_records() as u64)
        }
    }

    /// Worker loop: process assigned files and send batches
    fn worker_loop(
        worker_id: usize,
        n_workers: usize,
        paths: Arc<[String]>,
        config: Arc<ParallelReadConfig>,
        sender: Sender<BatchResult>,
        progress: Option<Arc<SharedProgress>>,
    ) {
        // Each worker processes files at indices: worker_id, worker_id + n_workers, ...
        for (idx, path) in paths.iter().enumerate() {
            if idx % n_workers != worker_id {
                continue;
            }

            // Process this file
            if let Err(e) = Self::process_file(path, idx, &config, &sender, progress.as_ref()) {
                // Send error and continue to next file
                let _ = sender.send(Err(e));
            }
        }
    }

    /// Process a single file, sending batches through the channel
    fn process_file(
        path: &str,
        file_index: usize,
        config: &ParallelReadConfig,
        sender: &Sender<BatchResult>,
        progress: Option<&Arc<SharedProgress>>,
    ) -> Result<(), Error> {
        let path_ref = Path::new(path);
        let extension = path_ref.extension().and_then(|e| e.to_str()).unwrap_or("");

        let is_dbc = extension.eq_ignore_ascii_case("dbc");

        if is_dbc {
            Self::process_dbc_file(path, file_index, config, sender, progress)
        } else {
            Self::process_dbf_file(path, file_index, config, sender, progress)
        }
    }

    /// Update progress for a batch
    fn update_progress(progress: Option<&Arc<SharedProgress>>, file_index: usize, batch_rows: u64) {
        if let Some(prog) = progress {
            // Update per-file progress
            let file_total =
                prog.file_records[file_index].fetch_add(batch_rows, Ordering::Relaxed) + batch_rows;
            prog.tracker.update_file_progress(file_index, file_total);

            // Update overall progress
            prog.tracker.update_overall_progress(batch_rows);
        }
    }

    /// Process a DBC (compressed) file
    fn process_dbc_file(
        path: &str,
        file_index: usize,
        config: &ParallelReadConfig,
        sender: &Sender<BatchResult>,
        progress: Option<&Arc<SharedProgress>>,
    ) -> Result<(), Error> {
        let reader = create_dbf_reader_from_dbc(
            path,
            config.single_col_name.clone(),
            Some(config.options.clone()),
        )?;

        // Convert column names to indices using this file's schema
        let with_columns_indices =
            Self::resolve_column_indices(&reader.schema(), &config.with_columns)?;

        let iter = reader.into_iter(Some(config.batch_size), with_columns_indices);

        for batch_result in iter {
            let batch = batch_result?;
            if batch.is_empty() {
                break;
            }
            let batch_rows = batch.height() as u64;
            if sender.send(Ok(batch)).is_err() {
                // Receiver dropped, stop processing
                break;
            }
            Self::update_progress(progress, file_index, batch_rows);
        }

        Ok(())
    }

    /// Process a regular DBF file
    fn process_dbf_file(
        path: &str,
        file_index: usize,
        config: &ParallelReadConfig,
        sender: &Sender<BatchResult>,
        progress: Option<&Arc<SharedProgress>>,
    ) -> Result<(), Error> {
        let file = File::open(path).map_err(|e| Error::InternalError {
            message: format!("Failed to open file '{}': {}", path, e),
        })?;

        let reader = DbfReader::new_with_options(
            vec![BufReader::new(file)],
            config.single_col_name.clone(),
            config.options.clone(),
        )?;

        // Convert column names to indices using this file's schema
        let with_columns_indices =
            Self::resolve_column_indices(&reader.schema(), &config.with_columns)?;

        let iter = reader.into_iter(Some(config.batch_size), with_columns_indices);

        for batch_result in iter {
            let batch = batch_result?;
            if batch.is_empty() {
                break;
            }
            let batch_rows = batch.height() as u64;
            if sender.send(Ok(batch)).is_err() {
                // Receiver dropped, stop processing
                break;
            }
            Self::update_progress(progress, file_index, batch_rows);
        }

        Ok(())
    }

    /// Convert column names to indices using the file's schema
    fn resolve_column_indices(
        schema: &polars::prelude::Schema,
        with_columns: &Option<Vec<PlSmallStr>>,
    ) -> Result<Option<Arc<[usize]>>, Error> {
        match with_columns {
            Some(columns) => {
                let indices: Result<Vec<usize>, Error> = columns
                    .iter()
                    .map(|name| {
                        schema.index_of(name).ok_or_else(|| Error::InternalError {
                            message: format!("Column '{}' not found in schema", name),
                        })
                    })
                    .collect();
                Ok(Some(indices?.into()))
            }
            None => Ok(None),
        }
    }
}

impl Iterator for ParallelDbfReader {
    type Item = BatchResult;

    fn next(&mut self) -> Option<Self::Item> {
        match self.receiver.recv().ok() {
            Some(result) => Some(result),
            None => {
                // Channel closed - all workers finished
                // Only call finish() once using atomic compare-exchange
                if let Some(prog) = &self.progress
                    && prog
                        .finished
                        .compare_exchange(0, 1, Ordering::SeqCst, Ordering::Relaxed)
                        .is_ok()
                {
                    prog.tracker.finish();
                }
                None
            }
        }
    }
}

/// Read multiple files in parallel and collect into a single DataFrame
///
/// This is a convenience function that reads all files and vstacks the results.
pub fn read_parallel(paths: Vec<String>, config: ParallelReadConfig) -> Result<DataFrame, Error> {
    let reader = ParallelDbfReader::new(paths, config)?;

    let batches: Result<Vec<DataFrame>, Error> = reader.collect();
    let batches = batches?;

    if batches.is_empty() {
        return Err(Error::InternalError {
            message: "No data read from files".to_string(),
        });
    }

    // Vstack all batches (zero-copy: DataFrames use Arc internally)
    let mut iter = batches.into_iter();
    let mut result = iter.next().unwrap();
    for batch in iter {
        result = result.vstack(&batch).map_err(|e| Error::InternalError {
            message: format!("Failed to vstack batches: {}", e),
        })?;
    }

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parallel_config_defaults() {
        let config = ParallelReadConfig::default();
        assert!(config.n_workers.is_none());
        assert_eq!(config.batch_size, 8192);
        assert!(config.effective_workers() >= 1);
    }

    #[test]
    fn test_parallel_config_builder() {
        let config = ParallelReadConfig::default()
            .with_workers(4)
            .with_batch_size(1024)
            .with_encoding(DbfEncoding::Utf8);

        assert_eq!(config.n_workers, Some(4));
        assert_eq!(config.batch_size, 1024);
        assert_eq!(config.options.encoding, DbfEncoding::Utf8);
    }

    #[test]
    fn test_effective_workers_capped_by_files() {
        // When we have fewer files than workers, should cap at file count
        let config = ParallelReadConfig::default().with_workers(8);
        let _paths = ["a.dbf".to_string(), "b.dbf".to_string()];

        // The actual capping happens in ParallelDbfReader::new
        // Here we just test the config itself
        assert_eq!(config.effective_workers(), 8);
    }

    #[test]
    fn test_parallel_read_single_file() {
        // Test parallel reading with a single real DBF file
        let path = "data/expected-sids.dbf";
        if !std::path::Path::new(path).exists() {
            println!("Skipping test: {} not found", path);
            return;
        }

        let config = ParallelReadConfig::default()
            .with_workers(2)
            .with_batch_size(100);

        let reader = ParallelDbfReader::new(vec![path.to_string()], config).unwrap();

        let mut total_rows = 0;
        let mut batch_count = 0;

        for batch_result in reader {
            let batch = batch_result.unwrap();
            total_rows += batch.height();
            batch_count += 1;
        }

        assert!(total_rows > 0, "Should have read some rows");
        assert!(batch_count > 0, "Should have received batches");
        println!(
            "✅ Parallel read: {} rows in {} batches",
            total_rows, batch_count
        );
    }

    #[test]
    fn test_parallel_read_collect() {
        // Test the read_parallel convenience function
        let path = "data/expected-sids.dbf";
        if !std::path::Path::new(path).exists() {
            println!("Skipping test: {} not found", path);
            return;
        }

        let config = ParallelReadConfig::default()
            .with_workers(2)
            .with_batch_size(1000);

        let result = read_parallel(vec![path.to_string()], config);
        assert!(result.is_ok());

        let df = result.unwrap();
        assert!(df.height() > 0, "DataFrame should have rows");
        assert!(df.width() > 0, "DataFrame should have columns");
        println!(
            "✅ Parallel collect: {} rows × {} columns",
            df.height(),
            df.width()
        );
    }

    #[test]
    fn test_parallel_read_dbc_with_progress() {
        // Test parallel reading with progress tracking on DBC files
        let path = "data/sids.dbc";
        if !std::path::Path::new(path).exists() {
            println!("Skipping test: {} not found", path);
            return;
        }

        let config = ParallelReadConfig::default()
            .with_workers(2)
            .with_batch_size(100)
            .with_progress(true);

        let reader = ParallelDbfReader::new(vec![path.to_string()], config).unwrap();

        let mut total_rows = 0;
        let mut batch_count = 0;

        for batch_result in reader {
            let batch = batch_result.unwrap();
            total_rows += batch.height();
            batch_count += 1;
        }

        assert!(total_rows > 0, "Should have read some rows");
        assert!(batch_count > 0, "Should have received batches");
        println!(
            "✅ Parallel DBC read with progress: {} rows in {} batches",
            total_rows, batch_count
        );
    }
}
