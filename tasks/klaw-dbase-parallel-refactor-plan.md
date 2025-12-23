# klaw-dbase Parallel File Reading Refactor Plan

> **Generated from Oracle Analysis Sessions**
> **Date:** 2024-12-23
> **Scope:** Full redesign to enable parallel file reading with Send+Sync compatibility

______________________________________________________________________

## Table of Contents

1. [Executive Summary](#1-executive-summary)
1. [Current State Analysis](#2-current-state-analysis)
   - [Progress Bar Issues](#21-progress-bar-issues)
   - [Parallel File Reading Blockers](#22-parallel-file-reading-blockers)
1. [Architecture Overview](#3-architecture-overview)
1. [Phased Implementation Plan](#4-phased-implementation-plan)
   - [Phase 1: Typed Encoding Enum](#phase-1--introduce-a-typed-encoding-enum)
   - [Phase 2: Migrate to encoding_rs](#phase-2--migrate-to-encoding_rs--eliminate-yore-based-trait-objects)
   - [Phase 3: Make DbfReader/DbfIter Send+Sync](#phase-3--make-dbfreader--dbfiter-send--sync--wire-progress-modes)
   - [Phase 4: Python Bindings](#phase-4--python-bindings-progress-enum-send-ability-and-parallelism)
   - [Phase 5: Two-Phase Pipeline (Advanced)](#phase-5--optional-two-phase-pipeline-raw-read--parallel-decodebuild)
1. [Code Examples](#5-code-examples)
1. [Risks and Guardrails](#6-risks-and-guardrails)
1. [Alternative Approaches](#7-alternative-approaches)
1. [References](#8-references)

______________________________________________________________________

## 1. Executive Summary

### TL;DR

- **Progress bar totals** are computed from `header.num_records` (physical records), but the scanner only advances progress for non-deleted records, causing bars to never reach 100%.
- **Parallel file reading is technically possible**, but not with the current single multi-file `DbfReader` + `PyDbaseIter` design.
- **Root blockers:** dbase's non-Send encoding trait objects, pyo3's non-Send PyObjects, and explicit `unsendable` markers.
- **Solution:** Refactor in three main steps:
  1. Internalize encoding as an enum and move all decoding to `encoding_rs`
  1. Make `dbase::Reader` and `DbfReader/DbfIter` graph `Send + Sync` by eliminating trait-object encoders
  1. Rewire Python side to support optional progress modes and remove `unsendable` markers

### Effort Estimates

| Phase              | Effort | Duration |
| ------------------ | ------ | -------- |
| Phase 1-2          | M      | 1-3 days |
| Phase 3-4          | M      | 1-3 days |
| Phase 5 (Advanced) | L-XL   | 2-5 days |

______________________________________________________________________

## 2. Current State Analysis

### 2.1 Progress Bar Issues

#### Problem 1: Totals Mismatch (Main Issue)

**Location:** `read.rs`, `py.rs`, `progress.rs`

Progress bar **totals** use `header.num_records` (physical records), but `iter_records()` **skips deleted records**, so counters only advance for non-deleted rows.

**How totals are set:**

```rust
// py.rs - batch_iter_with_progress
file_infos.push(DbaseFileInfo::new(
    file_name.to_string(),
    dbc_reader.total_records() as u64,  // Uses header.num_records
    file_extension.to_string(),
));
```

```rust
// read.rs - total_records()
pub fn total_records(&self) -> usize {
    self.reader.header().num_records as usize  // Physical records including deleted
}
```

**How updates happen:**

```rust
// read.rs - read_columns()
for _ in 0..self.batch_size {
    if let Some(record_result) = self.reader.iter_records().next() {
        // iter_records() SKIPS deleted records - no item yielded for them
        records.push(record_result);

        if let Some(ref tracker) = self.progress_tracker {
            self.records_processed_in_batch += 1;  // Only counts non-deleted
            tracker.update_file_progress(...);
            tracker.update_overall_progress(1);    // Only advances for non-deleted
        }
    }
}
```

**Symptoms:**

- Progress bars stall below 100% even after all data is processed
- Startup message shows larger record count than actual rows in DataFrame

#### Problem 2: create_progress_callback Double-Counts

**Location:** `progress.rs:172-181`

```rust
pub fn create_progress_callback(&self, file_index: usize) -> impl Fn(u64, u64) + '_ {
    let tracker = self.current_progress.clone();
    let file_pb = self.file_progress_bars[file_index].clone();
    let overall_pb = self.overall_pb.as_ref().unwrap().clone();

    move |records_read: u64, _total: u64| {
        file_pb.set_position(records_read);  // Absolute per-file position
        // BUG: records_read is added as delta, but it's actually absolute!
        let current = tracker.fetch_add(records_read, Ordering::SeqCst) + records_read;
        overall_pb.set_position(current);
    }
}
```

**Result:** Overall progress grows as 1→3→6→10 instead of 1→2→3→4.

#### Fix Options for Progress

**Option A1 (Recommended): Progress over non-deleted rows (logical records)**

Pre-scan to count non-deleted rows when building `DbaseFileInfo`:

```rust
// In batch_iter_with_progress when building file_infos
match create_dbf_reader_from_dbc(path, ...) {
    Ok(mut dbc_reader) => {
        let mut logical_rows: u64 = 0;
        let mut iter = dbc_reader.into_iter(Some(10_000), None);
        while let Some(batch_res) = iter.next() {
            let batch = batch_res?;
            if batch.is_empty() { break; }
            logical_rows += batch.height() as u64;
        }
        file_infos.push(DbaseFileInfo::new(
            file_name.to_string(),
            logical_rows,  // Actual non-deleted count
            file_extension.to_string(),
        ));
    }
    // ...
}
```

**Trade-off:** Doubles I/O for compressed files (pre-scan), but only when progress is enabled.

**Option A2: Progress over physical records**

Keep `record_count` as `header.num_records` but adjust per-record counter to advance on every physical record (requires lower-level dbase API or custom iterator).

**Fix for create_progress_callback:**

```rust
pub fn create_progress_callback(&self, file_index: usize) -> impl Fn(u64, u64) + '_ {
    use std::sync::atomic::AtomicU64;

    let global = self.current_progress.clone();
    let file_pb = self.file_progress_bars[file_index].clone();
    let overall_pb = self.overall_pb.as_ref().unwrap().clone();
    let last_file_pos = Arc::new(AtomicU64::new(0));

    move |records_read: u64, _total: u64| {
        file_pb.set_position(records_read);

        // Compute delta from last position
        let prev = last_file_pos.swap(records_read, Ordering::SeqCst);
        let delta = records_read.saturating_sub(prev);

        if delta > 0 {
            let current = global.fetch_add(delta, Ordering::SeqCst) + delta;
            overall_pb.set_position(current);
        }
    }
}
```

______________________________________________________________________

### 2.2 Parallel File Reading Blockers

#### Current Parallelization State

| Level                    | Status          | Implementation                                 |
| ------------------------ | --------------- | ---------------------------------------------- |
| Row-level (within batch) | ✅ Parallelized | rayon for column building in `read_columns`    |
| File-level               | ❌ Sequential   | Files processed one at a time through iterator |

#### Root Blockers

**1. dbase::Reader uses encoding trait objects (not Send+Sync)**

```rust
// read.rs:264-292 (simplified)
let reader = match validated_encoding.as_str() {
    "utf8" => ReaderBuilder::new(source)
        .with_encoding(Unicode)  // Trait object!
        .build()?,
    "cp1252" => ReaderBuilder::new(source)
        .with_encoding(yore::code_pages::CP1252)  // Trait object!
        .build()?,
    // ...
};
```

**2. Python types explicitly marked unsendable**

```rust
// py.rs:134-136
#[pyclass(unsendable)] // Keep unsendable due to encoding trait objects
pub struct PyDbaseIter(Fuse<DbfIter<ScanSource, SourceIter>>);

// py.rs:240-247
#[pyclass(unsendable)] // Keep unsendable due to encoding trait objects
pub struct DbaseSource { ... }
```

**3. Code comment documenting the limitation**

```rust
// py.rs:386-387
// Sequential processing of DBC files due to trait object limitations
// TODO: Re-enable parallel processing when encoding trait objects are Send + Sync
```

**4. pyo3's PyObject is not Send/Sync**

`PyReader` holds `Arc<PyObject>` and calls back into Python with GIL - cannot use from rayon workers.

______________________________________________________________________

## 3. Architecture Overview

### Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Python Layer                              │
│  DbaseSource (unsendable) ─► PyDbaseIter (unsendable)           │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                         Rust Layer                               │
│                                                                  │
│  DbfReader<R, I>                                                │
│    ├── reader: dbase::Reader<R>  ◄── Contains trait objects!   │
│    ├── sources: I (iterator)                                    │
│    ├── schema: Arc<PlSchema>                                    │
│    └── options: DbfReadOptions { encoding: String }             │
│                          │                                       │
│                          ▼                                       │
│  DbfIter<R, I>                                                  │
│    ├── reader: dbase::Reader<R>  ◄── NOT Send+Sync             │
│    ├── progress_tracker: Option<DbaseProgressTracker>           │
│    └── Iterates batches, builds DataFrame                       │
└──────────────────────────────────────────────────────────────────┘
```

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Python Layer                              │
│  DbaseSource (Send) ─► PyDbaseIter (Send)                       │
│       │                     │                                    │
│       └── progress_mode: PyProgressMode {None, Total, PerFile}  │
└────────────────────────────────┬────────────────────────────────┘
                                 │ py.allow_threads
┌────────────────────────────────▼────────────────────────────────┐
│                         Rust Layer                               │
│                                                                  │
│  DbfReader<R, I> where R: Send+Sync                             │
│    ├── reader: dbase::Reader<R>  ◄── Uses DbfEncoding enum     │
│    ├── encoding: DbfEncoding (Copy + Send + Sync)               │
│    └── encoding_config: EncodingConfig (&'static Encoding)      │
│                          │                                       │
│                          ▼                                       │
│  DbfIter<R, I>  ◄── NOW Send+Sync!                              │
│    ├── progress_mode: ProgressMode                              │
│    └── Can use rayon::par_iter over files                       │
│                          │                                       │
│            ┌─────────────┴─────────────┐                        │
│            ▼                           ▼                         │
│     Phase 1: I/O              Phase 2: Decode/Build             │
│   (single-threaded)           (rayon per-column)                │
└──────────────────────────────────────────────────────────────────┘
```

______________________________________________________________________

## 4. Phased Implementation Plan

### Phase 1 – Introduce a Typed Encoding Enum

**Goal:** Stop passing around raw `String` encoding names; turn them into a small, `Send + Sync` enum.

**Files affected:** `read.rs`

#### 1.1 Create `DbfEncoding` enum

Add just below `DbfReadOptions` in `read.rs`:

```rust
// read.rs (new, around line 76)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DbfEncoding {
    Utf8,
    Utf8Lossy,
    Ascii,
    Cp1252,
    Cp850,
    Cp437,
    Cp852,
    Cp866,
    Cp865,
    Cp861,
    Cp874,
    Cp1255,
    Cp1256,
    Cp1250,
    Cp1251,
    Cp1254,
    Cp1253,
    Gbk,
    Big5,
    ShiftJis,
    EucJp,
    EucKr,
}

impl Default for DbfEncoding {
    fn default() -> Self {
        Self::Cp1252  // Default for DataSUS files
    }
}
```

#### 1.2 Change `DbfReadOptions.encoding` from `String` to `DbfEncoding`

**Before:** `read.rs:27-40`

```rust
pub struct DbfReadOptions {
    pub batch_size: usize,
    pub character_trim: dbase::TrimOption,
    pub skip_deleted: bool,
    pub validate_schema: bool,
    pub encoding: String,
}
```

**After:**

```rust
pub struct DbfReadOptions {
    pub batch_size: usize,
    pub character_trim: dbase::TrimOption,
    pub skip_deleted: bool,
    pub validate_schema: bool,
    pub encoding: DbfEncoding,
}

impl Default for DbfReadOptions {
    fn default() -> Self {
        Self {
            batch_size: 1024,
            character_trim: dbase::TrimOption::BeginEnd,
            skip_deleted: true,
            validate_schema: true,
            encoding: DbfEncoding::Cp1252,
        }
    }
}

impl DbfReadOptions {
    pub fn with_encoding(encoding: DbfEncoding) -> Self {
        Self {
            encoding,
            ..Self::default()
        }
    }

    /// Parse encoding from string (for Python compatibility)
    pub fn with_encoding_str(encoding: impl AsRef<str>) -> Result<Self, ValueError> {
        let encoding = resolve_encoding_string(encoding.as_ref())?;
        Ok(Self { encoding, ..Self::default() })
    }

    pub fn with_batch_size(mut self, batch_size: usize) -> Self {
        self.batch_size = batch_size;
        self
    }

    pub fn with_character_trim(mut self, trim: dbase::TrimOption) -> Self {
        self.character_trim = trim;
        self
    }
}
```

#### 1.3 Rewrite `resolve_encoding_string` to return `DbfEncoding`

**Before:** `read.rs:76-112`

```rust
pub fn resolve_encoding_string(encoding_name: &str) -> Result<String, ValueError> { ... }
```

**After:**

```rust
pub fn resolve_encoding_string(encoding_name: &str) -> Result<DbfEncoding, ValueError> {
    use DbfEncoding::*;
    match encoding_name.to_lowercase().as_str() {
        // Default encodings
        "utf8" | "utf-8" => Ok(Utf8),
        "utf8-lossy" | "utf-8-lossy" => Ok(Utf8Lossy),
        "ascii" => Ok(Ascii),

        // Windows code pages
        "cp1252" | "windows-1252" => Ok(Cp1252),
        "cp1250" | "windows-1250" => Ok(Cp1250),
        "cp1251" | "windows-1251" => Ok(Cp1251),
        "cp1253" | "windows-1253" => Ok(Cp1253),
        "cp1254" | "windows-1254" => Ok(Cp1254),
        "cp1255" | "windows-1255" => Ok(Cp1255),
        "cp1256" | "windows-1256" => Ok(Cp1256),

        // DOS code pages
        "cp850" | "dos-850" => Ok(Cp850),
        "cp437" | "dos-437" => Ok(Cp437),
        "cp852" | "dos-852" => Ok(Cp852),
        "cp866" | "dos-866" => Ok(Cp866),
        "cp865" | "dos-865" => Ok(Cp865),
        "cp861" | "dos-861" => Ok(Cp861),
        "cp874" | "dos-874" => Ok(Cp874),

        // CJK encodings (encoding_rs)
        "gbk" | "gb2312" => Ok(Gbk),
        "big5" => Ok(Big5),
        "shift_jis" | "sjis" => Ok(ShiftJis),
        "euc-jp" => Ok(EucJp),
        "euc-kr" => Ok(EucKr),

        _ => Err(ValueError::InternalError {
            message: format!("Unsupported encoding: {}", encoding_name),
        }),
    }
}
```

______________________________________________________________________

### Phase 2 – Migrate to encoding_rs & Eliminate yore-based Trait Objects

**Goal:** Ensure all string decoding is done via `encoding_rs` (pure functions / `'static Encoding`), not via yore/encoding trait objects.

**Files affected:** `Cargo.toml`, `read.rs`

#### 2.1 Dependency Cleanup

**Before:** `Cargo.toml:72-82`

```toml
dbase = { version = "0.6.1", features = [
    "encoding_rs",
    "yore",
    "chrono",
    "serde",
] }
yore = "1.1.0"
encoding_rs = "0.8"
encoding = "0.2.33"
```

**After:**

```toml
dbase = { version = "0.6.1", features = [
    "encoding_rs",
    "chrono",
    "serde",
] }
# Remove yore and encoding - use encoding_rs exclusively
encoding_rs = "0.8"
```

#### 2.2 Create EncodingConfig Bridge

Add to `read.rs`:

```rust
use encoding_rs::Encoding;
use std::borrow::Cow;

/// Thread-safe encoding configuration using encoding_rs
///
/// This replaces the yore/encoding trait objects with static references
/// that are Copy + Send + Sync.
#[derive(Debug, Clone, Copy)]
pub struct EncodingConfig {
    /// The encoding_rs encoding (static reference, Send+Sync)
    enc: &'static Encoding,
    /// Whether to use lossy decoding (replace invalid chars with �)
    lossy: bool,
}

impl EncodingConfig {
    /// Create an EncodingConfig from our DbfEncoding enum
    pub fn from_dbf_encoding(enc: DbfEncoding) -> Self {
        use DbfEncoding::*;
        match enc {
            Utf8 => Self { enc: encoding_rs::UTF_8, lossy: false },
            Utf8Lossy => Self { enc: encoding_rs::UTF_8, lossy: true },
            Ascii => Self { enc: encoding_rs::WINDOWS_1252, lossy: false }, // ASCII subset

            // Windows code pages
            Cp1252 => Self { enc: encoding_rs::WINDOWS_1252, lossy: false },
            Cp1250 => Self { enc: encoding_rs::WINDOWS_1250, lossy: false },
            Cp1251 => Self { enc: encoding_rs::WINDOWS_1251, lossy: false },
            Cp1253 => Self { enc: encoding_rs::WINDOWS_1253, lossy: false },
            Cp1254 => Self { enc: encoding_rs::WINDOWS_1254, lossy: false },
            Cp1255 => Self { enc: encoding_rs::WINDOWS_1255, lossy: false },
            Cp1256 => Self { enc: encoding_rs::WINDOWS_1256, lossy: false },
            Cp874 => Self { enc: encoding_rs::WINDOWS_874, lossy: false },

            // IBM/DOS code pages
            Cp850 => Self { enc: encoding_rs::IBM850, lossy: false },
            Cp437 => Self { enc: encoding_rs::IBM437, lossy: false },
            Cp852 => Self { enc: encoding_rs::IBM852, lossy: false },
            Cp866 => Self { enc: encoding_rs::IBM866, lossy: false },
            Cp865 => Self { enc: encoding_rs::IBM865, lossy: false },
            Cp861 => Self { enc: encoding_rs::IBM861, lossy: false },

            // CJK encodings
            Gbk => Self { enc: encoding_rs::GBK, lossy: false },
            Big5 => Self { enc: encoding_rs::BIG5, lossy: false },
            ShiftJis => Self { enc: encoding_rs::SHIFT_JIS, lossy: false },
            EucJp => Self { enc: encoding_rs::EUC_JP, lossy: false },
            EucKr => Self { enc: encoding_rs::EUC_KR, lossy: false },
        }
    }

    /// Decode bytes to string using this encoding
    pub fn decode<'a>(&self, bytes: &'a [u8]) -> Cow<'a, str> {
        if self.enc == encoding_rs::UTF_8 && !self.lossy {
            // Fast path for UTF-8: try to borrow if valid
            match std::str::from_utf8(bytes) {
                Ok(s) => Cow::Borrowed(s),
                Err(_) => {
                    // Fall back to lossy decode
                    let (cow, _, _) = self.enc.decode(bytes);
                    cow
                }
            }
        } else {
            // Use encoding_rs for all other encodings
            let (cow, _, _) = self.enc.decode(bytes);
            cow
        }
    }

    /// Decode without BOM handling (for raw field data)
    pub fn decode_without_bom<'a>(&self, bytes: &'a [u8]) -> Cow<'a, str> {
        let (cow, _had_errors) = self.enc.decode_without_bom_handling(bytes);
        cow
    }
}
```

#### 2.3 Decouple from dbase::Unicode & yore

**Option A: Minimal dbase fork/patch**

If dbase's encoding_rs backend still uses trait objects internally, you need to patch it:

```rust
// In dbase crate (conceptual fork)
pub enum TextEncoding {
    Utf8,
    Utf8Lossy,
    SingleByte { enc: &'static encoding_rs::Encoding },
    MultiByte { enc: &'static encoding_rs::Encoding },
}

impl TextEncoding {
    pub fn decode(&self, bytes: &[u8]) -> Cow<'_, str> {
        match self {
            Self::Utf8 => Cow::Borrowed(std::str::from_utf8(bytes).unwrap_or("")),
            Self::Utf8Lossy => String::from_utf8_lossy(bytes),
            Self::SingleByte { enc } | Self::MultiByte { enc } => {
                let (cow, _, _) = enc.decode(bytes);
                cow
            }
        }
    }
}

pub struct Reader<R> {
    source: R,
    encoding: TextEncoding,  // Now Send+Sync!
    // ...
}
```

**Option B: Post-read decoding (no dbase fork)**

If you can't fork dbase, decode after reading:

```rust
// In DbfIter, after reading raw records:
impl<R, E, I> DbfIter<R, I> {
    fn decode_character_field(&self, raw_value: &dbase::FieldValue) -> FieldValue {
        match raw_value {
            FieldValue::Character(Some(s)) => {
                // Re-decode using our EncodingConfig if needed
                // This assumes dbase gives us the raw bytes somewhere
                FieldValue::Character(Some(s.clone()))
            }
            other => other.clone(),
        }
    }
}
```

______________________________________________________________________

### Phase 3 – Make DbfReader / DbfIter Send + Sync & Wire Progress Modes

**Goal:** Ensure scanner types are `Send + Sync` and can run under Rayon; add clean progress mode abstraction.

**Files affected:** `read.rs`, `progress.rs`

#### 3.1 Progress Mode Enum

Add to `read.rs` or a shared module:

```rust
/// Progress tracking mode for batch iteration
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ProgressMode {
    /// No progress tracking
    #[default]
    None,
    /// Track only overall progress (single bar)
    Total,
    /// Track per-file and overall progress (multiple bars)
    PerFile,
}
```

#### 3.2 Update DbfIter with Progress Mode

**Before:** `read.rs:411-428`

```rust
pub struct DbfIter<R, I>
where
    R: Read + Seek,
{
    reader: Reader<R>,
    sources: I,
    schema: Arc<PlSchema>,
    _field_info: Vec<FieldInfo>,
    field_name_mapping: std::collections::HashMap<String, String>,
    single_column_name: Option<PlSmallStr>,
    options: DbfReadOptions,
    batch_size: usize,
    with_columns: Option<Arc<[usize]>>,
    progress_tracker: Option<DbaseProgressTracker>,
    current_file_index: usize,
    records_processed_in_batch: usize,
}
```

**After:**

```rust
pub struct DbfIter<R, I>
where
    R: Read + Seek + Send + Sync + 'static,
    I: Iterator<Item = Result<R, std::io::Error>> + Send,
{
    reader: Reader<R>,
    sources: I,
    schema: Arc<PlSchema>,
    _field_info: Vec<FieldInfo>,
    field_name_mapping: std::collections::HashMap<String, String>,
    single_column_name: Option<PlSmallStr>,
    options: DbfReadOptions,
    batch_size: usize,
    with_columns: Option<Arc<[usize]>>,
    // Progress tracking
    progress_tracker: Option<DbaseProgressTracker>,
    progress_mode: ProgressMode,
    current_file_index: usize,
    records_processed_in_batch: usize,
    records_processed_in_file: usize,
}
```

#### 3.3 Update Iterator Methods

```rust
impl<R, E, I> DbfReader<R, I>
where
    R: Read + Seek + Send + Sync + 'static,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>> + Send,
{
    /// Convert the scanner into an iterator with optional progress tracking
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
            records_processed_in_batch: 0,
            records_processed_in_file: 0,
        }
        .fuse()
    }
}
```

#### 3.4 Update Progress Handling in read_columns

```rust
impl<R, E, I> DbfIter<R, I>
where
    R: Read + Seek + Send + Sync + 'static,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>> + Send,
{
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

    fn read_columns(
        &mut self,
        with_columns: impl IntoIterator<Item = usize> + Clone,
    ) -> Result<Vec<Column>, ValueError> {
        let column_indices: Vec<usize> = with_columns.into_iter().collect();

        let mut records = Vec::with_capacity(self.batch_size);

        // Collect records from current file
        for _ in 0..self.batch_size {
            if let Some(record_result) = self.reader.iter_records().next() {
                records.push(record_result);
            } else {
                break;
            }
        }

        // Update progress after collecting (not per-record for performance)
        if !records.is_empty() {
            self.update_progress(records.len());
        }

        // ... rest of column building logic
    }
}
```

______________________________________________________________________

### Phase 4 – Python Bindings: Progress Enum, Send-ability, and Parallelism

**Goal:** Expose configurable progress modes to Python and remove `unsendable` markers.

**Files affected:** `py.rs`

#### 4.1 Python ProgressMode Enum

```rust
// py.rs (new)
use pyo3::pyclass;

/// Progress tracking mode for Python API
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PyProgressMode {
    /// No progress tracking
    None = 0,
    /// Track only overall progress (single bar)
    Total = 1,
    /// Track per-file and overall progress (multiple bars)
    PerFile = 2,
}

impl Default for PyProgressMode {
    fn default() -> Self {
        Self::None
    }
}

impl From<PyProgressMode> for crate::read::ProgressMode {
    fn from(m: PyProgressMode) -> Self {
        match m {
            PyProgressMode::None => crate::read::ProgressMode::None,
            PyProgressMode::Total => crate::read::ProgressMode::Total,
            PyProgressMode::PerFile => crate::read::ProgressMode::PerFile,
        }
    }
}
```

#### 4.2 Update Module Registration

```rust
// py.rs - in polars_dbase function
#[pymodule]
#[pyo3(name = "_dbase_rs")]
fn polars_dbase(py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    // Register classes
    m.add_class::<DbaseSource>()?;
    m.add_class::<PyProgressMode>()?;  // New!

    // ... rest of registration
}
```

#### 4.3 Update DbaseSource

**Before:**

```rust
#[pyclass(unsendable)]
pub struct DbaseSource {
    paths: Arc<[String]>,
    buffs: Arc<[Arc<PyObject>]>,
    // ...
    compressed: Option<bool>,
}
```

**After:**

```rust
#[pyclass]  // Remove unsendable!
pub struct DbaseSource {
    paths: Arc<[String]>,
    buffs: Arc<[Arc<PyObject>]>,
    single_col_name: Option<PlSmallStr>,
    schema: Option<Arc<Schema>>,
    last_scanner: Option<DbfReader<ScanSource, SourceIter>>,
    // DBF options
    encoding: Option<String>,
    character_trim: Option<String>,
    skip_deleted: Option<bool>,
    validate_schema: Option<bool>,
    compressed: Option<bool>,
    // Progress options (NEW)
    progress_mode: PyProgressMode,
}
```

#### 4.4 Update Python Methods

```rust
#[pymethods]
impl DbaseSource {
    #[new]
    #[pyo3(signature = (
        paths,
        buffs,
        single_col_name=None,
        encoding=None,
        character_trim=None,
        skip_deleted=None,
        validate_schema=None,
        compressed=None,
        progress_mode=None
    ))]
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
        progress_mode: Option<PyProgressMode>,
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
            compressed,
            progress_mode: progress_mode.unwrap_or_default(),
        }
    }

    #[pyo3(signature = (batch_size, with_columns=None))]
    fn batch_iter(
        &mut self,
        py: Python<'_>,
        batch_size: usize,
        with_columns: Option<Vec<String>>,
    ) -> PyResult<PyDbaseIter> {
        let scanner = self.take_scanner(py)?;

        // Build progress tracker based on mode
        let (progress_tracker, progress_mode) = match self.progress_mode {
            PyProgressMode::None => (None, ProgressMode::None),
            PyProgressMode::Total | PyProgressMode::PerFile => {
                if self.compressed.unwrap_or(false) && !self.paths.is_empty() {
                    let file_infos = self.build_file_infos()?;
                    if file_infos.iter().any(|info| info.get_file_size() > 0) {
                        (
                            Some(create_multi_file_progress(file_infos)),
                            self.progress_mode.into(),
                        )
                    } else {
                        (None, ProgressMode::None)
                    }
                } else {
                    (None, ProgressMode::None)
                }
            }
        };

        let with_columns_indices = self.resolve_column_indices(&scanner, with_columns)?;

        let iter = scanner.into_iter_with_progress(
            Some(batch_size),
            with_columns_indices,
            progress_tracker,
            progress_mode,
        );

        Ok(PyDbaseIter(iter))
    }
}
```

#### 4.5 Remove unsendable from PyDbaseIter

**Before:**

```rust
#[pyclass(unsendable)]
pub struct PyDbaseIter(Fuse<DbfIter<ScanSource, SourceIter>>);
```

**After:**

```rust
#[pyclass]  // Now Send!
pub struct PyDbaseIter(Fuse<DbfIter<ScanSource, SourceIter>>);
```

#### 4.6 Enable Rayon Parallelism

Once types are `Send`, you can parallelize across sources:

```rust
impl DbaseSource {
    /// Read all files in parallel and return concatenated DataFrame
    #[pyo3(signature = (batch_size=10000, with_columns=None))]
    fn collect_parallel(
        &self,
        py: Python<'_>,
        batch_size: usize,
        with_columns: Option<Vec<String>>,
    ) -> PyResult<PyDataFrame> {
        use rayon::prelude::*;

        // Only works with path sources, not buffers
        if !self.buffs.is_empty() {
            return Err(PyRuntimeError::new_err(
                "Parallel collection only supported for file paths, not buffers"
            ));
        }

        let paths = self.paths.clone();
        let options = self.build_dbf_options();
        let single_col = self.single_col_name.clone();
        let compressed = self.compressed.unwrap_or(false);

        // Release GIL for parallel work
        let dataframes: Vec<DataFrame> = py.allow_threads(|| {
            paths
                .par_iter()
                .map(|path| {
                    // Each worker creates its own reader (no Send needed across threads)
                    let reader = if compressed {
                        create_dbf_reader_from_dbc(path, single_col.clone(), Some(options.clone()))?
                    } else {
                        let file = std::fs::File::open(path)?;
                        DbfReader::new_with_options(vec![file], single_col.clone(), options.clone())?
                    };

                    // Collect all batches for this file
                    let mut file_dfs = Vec::new();
                    let mut iter = reader.into_iter(Some(batch_size), None);
                    while let Some(batch) = iter.next() {
                        let df = batch?;
                        if !df.is_empty() {
                            file_dfs.push(df);
                        }
                    }

                    // Concatenate batches for this file
                    if file_dfs.is_empty() {
                        Ok(DataFrame::empty())
                    } else {
                        polars::functions::concat_df_horizontal(&file_dfs)
                            .map_err(|e| ValueError::InternalError { message: e.to_string() })
                    }
                })
                .collect::<Result<Vec<_>, ValueError>>()
        })?;

        // Concatenate all file DataFrames
        let result = polars::functions::concat_df_horizontal(&dataframes)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;

        Ok(PyDataFrame(result))
    }
}
```

______________________________________________________________________

### Phase 5 – Optional: Two-Phase Pipeline (Raw Read → Parallel Decode/Build)

**Goal:** Get parallelism even if `dbase::Reader` remains single-threaded; parallelize the heaviest part (decode/build).

**Files affected:** `read.rs`

#### 5.1 Split read_frame into Two Phases

```rust
impl<R, E, I> DbfIter<R, I>
where
    R: Read + Seek + Send + Sync + 'static,
    ValueError: From<E>,
    I: Iterator<Item = Result<R, E>> + Send,
{
    /// Phase 1: Collect raw records (I/O bound, single-threaded)
    fn collect_raw_records(&mut self) -> Result<Vec<dbase::Record>, ValueError> {
        let mut records = Vec::with_capacity(self.batch_size);

        for _ in 0..self.batch_size {
            match self.reader.iter_records().next() {
                Some(Ok(record)) => records.push(record),
                Some(Err(e)) => return Err(e.into()),
                None => {
                    // Try next source
                    if !self.advance_to_next_source()? {
                        break;
                    }
                }
            }
        }

        Ok(records)
    }

    /// Phase 2: Build columns in parallel (CPU bound)
    fn build_columns_parallel(
        &self,
        records: &[dbase::Record],
        column_indices: &[usize],
    ) -> Result<Vec<Column>, ValueError> {
        use rayon::prelude::*;

        let schema = &self.schema;
        let field_info = &self._field_info;
        let field_name_mapping = &self.field_name_mapping;

        column_indices
            .par_iter()
            .map(|&col_idx| {
                let (field_name, dtype) = schema.get_at_index(col_idx)
                    .ok_or_else(|| ValueError::InternalError {
                        message: format!("Column index {} out of bounds", col_idx),
                    })?;

                // Get original field name for lookup
                let original_name = field_name_mapping
                    .get(field_name.as_str())
                    .map(|s| s.as_str())
                    .unwrap_or(field_name.as_str());

                // Build column
                let mut builder = new_value_builder(dtype, records.len());

                for record in records {
                    let value = record.get(original_name)
                        .unwrap_or(&dbase::FieldValue::Character(None));
                    builder.try_push_value(value)?;
                }

                let array = builder.as_box();
                let series = Series::try_from((field_name.clone(), array))?;
                Ok(Column::from(series))
            })
            .collect()
    }

    /// Combined read_frame with two-phase processing
    fn read_frame(&mut self) -> Result<DataFrame, ValueError> {
        // Phase 1: I/O (single-threaded)
        let records = self.collect_raw_records()?;

        if records.is_empty() {
            // Signal completion
            if let Some(ref tracker) = self.progress_tracker {
                tracker.finish();
            }
            return Ok(DataFrame::empty());
        }

        // Update progress after I/O
        self.update_progress(records.len());

        // Phase 2: Build columns (parallel)
        let column_indices: Vec<usize> = match &self.with_columns {
            Some(cols) => cols.iter().copied().collect(),
            None => (0..self.schema.len()).collect(),
        };

        let columns = self.build_columns_parallel(&records, &column_indices)?;

        DataFrame::new(columns).map_err(|e| e.into())
    }
}
```

#### 5.2 Alternative: Channel-Based Streaming Parallelism

For true streaming with parallel file reading:

```rust
use crossbeam::channel::{bounded, Receiver, Sender};
use std::thread;

/// Parallel file reader that processes files concurrently
pub struct ParallelDbfReader {
    receiver: Receiver<Result<DataFrame, ValueError>>,
    _workers: Vec<thread::JoinHandle<()>>,
}

impl ParallelDbfReader {
    pub fn new(
        paths: Vec<String>,
        options: DbfReadOptions,
        batch_size: usize,
        num_workers: usize,
    ) -> Self {
        let (tx, rx) = bounded::<Result<DataFrame, ValueError>>(num_workers * 2);
        let paths = Arc::new(paths);
        let options = Arc::new(options);

        let mut workers = Vec::with_capacity(num_workers);

        for worker_id in 0..num_workers {
            let tx = tx.clone();
            let paths = paths.clone();
            let options = options.clone();

            let handle = thread::spawn(move || {
                // Each worker processes files round-robin
                for (idx, path) in paths.iter().enumerate() {
                    if idx % num_workers != worker_id {
                        continue;
                    }

                    // Create reader for this file
                    let reader_result = (|| {
                        let file = std::fs::File::open(path)?;
                        DbfReader::new_with_options(
                            vec![file],
                            None,
                            (*options).clone(),
                        )
                    })();

                    match reader_result {
                        Ok(reader) => {
                            let mut iter = reader.into_iter(Some(batch_size), None);
                            while let Some(batch_result) = iter.next() {
                                if tx.send(batch_result).is_err() {
                                    return; // Receiver dropped
                                }
                            }
                        }
                        Err(e) => {
                            let _ = tx.send(Err(e));
                        }
                    }
                }
            });

            workers.push(handle);
        }

        // Drop our sender so receiver knows when all workers are done
        drop(tx);

        Self {
            receiver: rx,
            _workers: workers,
        }
    }
}

impl Iterator for ParallelDbfReader {
    type Item = Result<DataFrame, ValueError>;

    fn next(&mut self) -> Option<Self::Item> {
        self.receiver.recv().ok()
    }
}
```

______________________________________________________________________

## 5. Code Examples

### Complete DbfEncoding Implementation

```rust
// read.rs - Complete encoding module

use encoding_rs::Encoding;
use std::borrow::Cow;

/// Strongly-typed encoding enum (Copy + Send + Sync)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DbfEncoding {
    Utf8,
    Utf8Lossy,
    Ascii,
    // Windows
    Cp1252,
    Cp1250,
    Cp1251,
    Cp1253,
    Cp1254,
    Cp1255,
    Cp1256,
    Cp874,
    // DOS/IBM
    Cp850,
    Cp437,
    Cp852,
    Cp866,
    Cp865,
    Cp861,
    // CJK
    Gbk,
    Big5,
    ShiftJis,
    EucJp,
    EucKr,
}

impl DbfEncoding {
    /// Get the encoding_rs Encoding for this DbfEncoding
    pub fn as_encoding_rs(&self) -> &'static Encoding {
        use DbfEncoding::*;
        match self {
            Utf8 | Utf8Lossy | Ascii => encoding_rs::UTF_8,
            Cp1252 => encoding_rs::WINDOWS_1252,
            Cp1250 => encoding_rs::WINDOWS_1250,
            Cp1251 => encoding_rs::WINDOWS_1251,
            Cp1253 => encoding_rs::WINDOWS_1253,
            Cp1254 => encoding_rs::WINDOWS_1254,
            Cp1255 => encoding_rs::WINDOWS_1255,
            Cp1256 => encoding_rs::WINDOWS_1256,
            Cp874 => encoding_rs::WINDOWS_874,
            Cp850 => encoding_rs::IBM850,
            Cp437 => encoding_rs::IBM437,
            Cp852 => encoding_rs::IBM852,
            Cp866 => encoding_rs::IBM866,
            Cp865 => encoding_rs::IBM865,
            Cp861 => encoding_rs::IBM861,
            Gbk => encoding_rs::GBK,
            Big5 => encoding_rs::BIG5,
            ShiftJis => encoding_rs::SHIFT_JIS,
            EucJp => encoding_rs::EUC_JP,
            EucKr => encoding_rs::EUC_KR,
        }
    }

    /// Whether this encoding uses lossy decoding
    pub fn is_lossy(&self) -> bool {
        matches!(self, DbfEncoding::Utf8Lossy)
    }

    /// Decode bytes to string
    pub fn decode<'a>(&self, bytes: &'a [u8]) -> Cow<'a, str> {
        let enc = self.as_encoding_rs();

        if *self == DbfEncoding::Utf8 {
            // Fast path: try to borrow valid UTF-8
            match std::str::from_utf8(bytes) {
                Ok(s) => return Cow::Borrowed(s),
                Err(_) => {} // Fall through to encoding_rs
            }
        }

        let (cow, _, _) = enc.decode(bytes);
        cow
    }
}

impl Default for DbfEncoding {
    fn default() -> Self {
        Self::Cp1252
    }
}

impl std::fmt::Display for DbfEncoding {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        use DbfEncoding::*;
        let name = match self {
            Utf8 => "utf-8",
            Utf8Lossy => "utf-8-lossy",
            Ascii => "ascii",
            Cp1252 => "cp1252",
            Cp1250 => "cp1250",
            Cp1251 => "cp1251",
            Cp1253 => "cp1253",
            Cp1254 => "cp1254",
            Cp1255 => "cp1255",
            Cp1256 => "cp1256",
            Cp874 => "cp874",
            Cp850 => "cp850",
            Cp437 => "cp437",
            Cp852 => "cp852",
            Cp866 => "cp866",
            Cp865 => "cp865",
            Cp861 => "cp861",
            Gbk => "gbk",
            Big5 => "big5",
            ShiftJis => "shift_jis",
            EucJp => "euc-jp",
            EucKr => "euc-kr",
        };
        write!(f, "{}", name)
    }
}
```

### Complete ProgressMode Implementation

```rust
// read.rs or progress.rs

/// Progress tracking mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ProgressMode {
    /// No progress tracking (fastest)
    #[default]
    None,
    /// Track only overall progress across all files
    Total,
    /// Track per-file progress with individual bars
    PerFile,
}

impl ProgressMode {
    /// Whether any progress tracking is enabled
    pub fn is_enabled(&self) -> bool {
        !matches!(self, Self::None)
    }

    /// Whether per-file tracking is enabled
    pub fn tracks_files(&self) -> bool {
        matches!(self, Self::PerFile)
    }
}
```

______________________________________________________________________

## 6. Risks and Guardrails

### dbase Crate Assumptions

**Risk:** If dbase 0.6.1's `encoding_rs` backend still hides decoders behind non-Send trait objects, you'll need a fork/PR.

**Guardrail:** Keep that change minimal - just replace trait objects with an enum of supported encodings.

### Encoding Coverage

**Risk:** Not all code pages supported by yore are available in encoding_rs.

**Guardrail:**

- Verify all code pages before removing yore
- For missing ones, implement as lookup tables in your own enum (still Send+Sync)
- encoding_rs covers: UTF-8, Windows-125x, IBM-85x/86x, GBK, Big5, Shift_JIS, EUC-JP/KR

### Python GIL Interactions

**Risk:** `PyReader` uses `Python::with_gil` which is safe in worker threads, but slow.

**Guardrail:**

- Document that Python IO sources will be slower
- Consider keeping buffer sources single-threaded
- Only parallelize path-based sources

### Progress Spam

**Risk:** In PerFile mode with many files and high concurrency, terminal progress may become noisy.

**Guardrail:**

- Default to `Total` for large file counts
- Only use `PerFile` when explicitly requested
- Consider batching progress updates (every N records, not every record)

### Thread Safety Verification

**Guardrail:** Add compile-time assertions:

```rust
// In read.rs or lib.rs
fn _assert_send_sync() {
    fn assert_send<T: Send>() {}
    fn assert_sync<T: Sync>() {}

    // These should compile once refactor is complete
    assert_send::<DbfEncoding>();
    assert_sync::<DbfEncoding>();
    assert_send::<EncodingConfig>();
    assert_sync::<EncodingConfig>();
    // assert_send::<DbfIter<std::fs::File, _>>(); // Add once Send
}
```

______________________________________________________________________

## 7. Alternative Approaches

### Alternative A: spawn_blocking Pattern (arrow-sus style)

Instead of making Reader Send+Sync, isolate non-Send types in blocking tasks:

```rust
pub async fn read_dbf_parallel<P: AsRef<Path>>(
    file_path: P,
) -> Result<Vec<DataFrame>, ValueError> {
    let path = file_path.as_ref().to_path_buf();

    // Phase 1: Read raw data in blocking task (isolates non-Send Reader)
    let raw_data = tokio::task::spawn_blocking(move || {
        let reader = Reader::from_path(path)?;
        let records: Vec<RawRecord> = reader
            .iter_records()
            .map(|r| r.map(|rec| RawRecord { data: rec.data().to_vec() }))
            .collect::<Result<_, _>>()?;
        Ok::<_, ValueError>(records)
    })
    .await??;

    // Phase 2: Decode in parallel (rayon, no trait objects)
    let decoded = raw_data
        .into_par_iter()
        .map(|rec| decode_record(&rec))
        .collect::<Result<Vec<_>, _>>()?;

    Ok(decoded)
}
```

**Pros:** No dbase fork needed, works today
**Cons:** Runtime complexity, harder to reason about performance, requires tokio

### Alternative B: Per-File Workers (Simple Path)

Don't try to make DbfIter Send; instead create separate readers per file:

```rust
fn read_files_parallel(paths: &[String], options: DbfReadOptions) -> Vec<DataFrame> {
    paths
        .par_iter()
        .flat_map(|path| {
            // Each worker creates its own reader
            let file = std::fs::File::open(path).unwrap();
            let reader = DbfReader::new_with_options(vec![file], None, options.clone()).unwrap();
            let mut iter = reader.into_iter(Some(10000), None);

            let mut results = Vec::new();
            while let Some(Ok(df)) = iter.next() {
                if !df.is_empty() {
                    results.push(df);
                }
            }
            results
        })
        .collect()
}
```

**Pros:** No changes to dbase or DbfIter needed
**Cons:** Loses streaming semantics, uses more memory

### Alternative C: Keep Sequential, Optimize I/O

If parallel isn't critical, focus on:

- Larger batch sizes
- Memory-mapped files
- Better streaming decompression
- Column pruning at read time

______________________________________________________________________

## 8. References

### Code Locations

| File          | Lines   | Description                                   |
| ------------- | ------- | --------------------------------------------- |
| `read.rs`     | 27-40   | DbfReadOptions struct                         |
| `read.rs`     | 76-112  | resolve_encoding_string                       |
| `read.rs`     | 150-161 | DbfReader struct                              |
| `read.rs`     | 264-292 | Encoding match (mentioned, after line 250)    |
| `read.rs`     | 383-405 | into_iter_with_progress                       |
| `read.rs`     | 411-428 | DbfIter struct                                |
| `read.rs`     | 436-462 | read_columns method                           |
| `py.rs`       | 134-136 | PyDbaseIter (unsendable)                      |
| `py.rs`       | 240-247 | DbaseSource (unsendable)                      |
| `py.rs`       | 386-387 | TODO comment about parallelism                |
| `progress.rs` | 11-22   | DbaseProgressTracker struct                   |
| `progress.rs` | 131-149 | update_file_progress, update_overall_progress |
| `progress.rs` | 172-181 | create_progress_callback (bug)                |
| `Cargo.toml`  | 72-82   | dbase, yore, encoding_rs deps                 |

### External References

- [encoding_rs documentation](https://docs.rs/encoding_rs)
- [dbase crate](https://docs.rs/dbase)
- [pyo3 Send/Sync requirements](https://pyo3.rs/v0.25.1/class.html#pyclass-and-send)
- [rayon parallelism](https://docs.rs/rayon)
- [arrow-sus dbase_utils.rs](https://github.com/wrath-codes/arrow-sus/blob/main/rust/crates/shared/src/models/dbase_utils.rs) - spawn_blocking pattern reference
- [Fearless Concurrency patterns](./fearless-concurrency.md)

### Dependencies (Current)

```toml
pyo3 = "0.25.1"
dbase = "0.6.1"
rayon = "1.8"
encoding_rs = "0.8"
yore = "1.1.0"      # To be removed
encoding = "0.2.33" # To be removed
indicatif = "0.18.0"
```

### Dependencies (Target)

```toml
pyo3 = "0.25.1"
dbase = "0.6.1"  # May need fork for Send+Sync
rayon = "1.8"
encoding_rs = "0.8"
indicatif = "0.18.0"
crossbeam = "0.8"  # Optional, for channel-based parallelism
```

______________________________________________________________________

## 9. Patterns from polars-avro Analysis

> Analysis of [hafaio/polars-avro](https://github.com/hafaio/polars-avro) for applicable patterns.

### 9.1 What We Already Have (Correctly Borrowed)

| Pattern                          | Status         | Location          |
| -------------------------------- | -------------- | ----------------- |
| InfallableIter wrapper           | ✅ Implemented | `read.rs:179-198` |
| ValueBuilder trait               | ✅ Implemented | `des.rs:185-232`  |
| Lazy scanner with cached schema  | ✅ Implemented | `read.rs:150-313` |
| FusedIterator return             | ✅ Implemented | `read.rs:335-352` |
| Multi-source iteration           | ✅ Implemented | `read.rs:464-512` |
| Column projection (with_columns) | ✅ Implemented | `read.rs:361-380` |
| PyO3 source caching pattern      | ✅ Implemented | `py.rs:240-328`   |

### 9.2 Patterns We Should Adopt

#### A. Pre-allocation with Batch Size

**polars-avro pattern:**

```rust
fn read_columns(&mut self, with_columns: ...) -> Result<Vec<Column>, Error> {
    let mut arrow_columns: Box<[_]> = with_columns
        .clone()
        .into_iter()
        .map(|idx| {
            let (_, dtype) = self.schema.get_at_index(idx).unwrap();
            new_value_builder(dtype, self.batch_size)  // Pre-allocate!
        })
        .collect();
    // ...
}
```

**Current klaw-dbase:** We do this, but should verify capacity is always set.

#### B. Lazy Validity Bitmap Allocation

**polars-avro pattern:**

```rust
fn push_null(&mut self) {
    match &mut self.validity {
        Some(val) => val.push(false),
        empty @ None => {
            // Only allocate when first null is encountered
            let mut val = MutableBitmap::from_len_set(self.len);  // Back-fill with trues
            val.push(false);
            *empty = Some(val);
        }
    }
}
```

**Action:** Verify `StructBuilder` in `des.rs` follows this pattern (it does at line 542-556).

#### C. Box Large Types in Errors

**polars-avro pattern:**

```rust
#[non_exhaustive]
#[derive(Debug)]
pub enum Error {
    Avro(Box<AvroError>),           // Boxed - expensive
    NonRecordSchema(Box<Schema>),   // Boxed - expensive
    IO(io::Error, String),          // Context preserved
    // ...
}
```

**Current klaw-dbase error.rs:** Should review and box large variants.

#### D. Source Iterator Chaining

**polars-avro pattern:**

```rust
type SourceIter = Chain<BytesIter, PathIter>;

// Allows mixing bytes and file sources in single iterator
let combined = bytes_iter.chain(path_iter);
```

**Current klaw-dbase:** We have this with `Chain<Chain<DbcIter, PathIter>, BytesIter>`.

### 9.3 Patterns for DBF-Specific Improvements

#### A. Parallel File Reading (DBF Advantage)

Unlike Avro, DBF has fixed-width records and clear headers, enabling:

```rust
// Pattern: Per-file parallel reading
impl<R, I> DBFScanner<R, I>
where
    R: Read + Seek + Send + Sync,
    I: Iterator<Item = Result<R, E>> + Send,
{
    pub fn par_collect(self, batch_size: usize) -> Result<Vec<DataFrame>, Error> {
        use rayon::prelude::*;

        // Collect sources first
        let sources: Vec<R> = self.sources.collect::<Result<Vec<_>, _>>()?;

        // Process files in parallel
        sources
            .into_par_iter()
            .map(|source| {
                // Each thread creates own reader - no Send required for Reader itself
                let reader = create_reader(source)?;
                collect_all_batches(reader, batch_size)
            })
            .collect()
    }
}
```

#### B. Record-Level Parallel Decoding

```rust
// Pattern: Parallel decoding within a batch
fn build_columns_parallel(
    &self,
    raw_records: &[RawRecord],
    column_indices: &[usize],
) -> Result<Vec<Column>, Error> {
    use rayon::prelude::*;

    column_indices
        .par_iter()
        .map(|&col_idx| {
            let dtype = self.schema.get_at_index(col_idx)?.1;
            let mut builder = new_value_builder(dtype, raw_records.len());

            for record in raw_records {
                builder.try_push_value(&record.field(col_idx))?;
            }

            Ok(Column::from(builder.as_box()))
        })
        .collect()
}
```

#### C. Seek Support for Random Access

DBF allows record-level seeking (Avro doesn't):

```rust
impl<R: Read + Seek> DBFReader<R> {
    /// Seek to a specific record by index
    pub fn seek_to_record(&mut self, record_idx: usize) -> Result<(), Error> {
        let offset = self.header_size + (record_idx * self.record_size);
        self.reader.seek(SeekFrom::Start(offset as u64))?;
        self.current_record = record_idx;
        Ok(())
    }

    /// Read a range of records (useful for parallel chunking)
    pub fn read_record_range(&mut self, start: usize, count: usize) -> Result<Vec<Record>, Error> {
        self.seek_to_record(start)?;
        // Read count records...
    }
}
```

#### D. Progress Wrapper Pattern

polars-avro doesn't have progress tracking. We add:

```rust
/// Progress-aware iterator wrapper
pub struct ProgressIter<I> {
    inner: I,
    tracker: Option<DbaseProgressTracker>,
    mode: ProgressMode,
    file_index: usize,
    records_in_file: u64,
}

impl<I: Iterator<Item = Result<DataFrame, Error>>> Iterator for ProgressIter<I> {
    type Item = Result<DataFrame, Error>;

    fn next(&mut self) -> Option<Self::Item> {
        let result = self.inner.next()?;

        if let Ok(ref df) = result {
            let rows = df.height() as u64;
            self.update_progress(rows);
        }

        Some(result)
    }

    fn update_progress(&mut self, rows: u64) {
        if let Some(ref tracker) = self.tracker {
            match self.mode {
                ProgressMode::None => {}
                ProgressMode::Total => {
                    tracker.update_overall_progress(rows);
                }
                ProgressMode::PerFile => {
                    self.records_in_file += rows;
                    tracker.update_file_progress(self.file_index, self.records_in_file);
                    tracker.update_overall_progress(rows);
                }
            }
        }
    }
}
```

### 9.4 Architecture Comparison

| Aspect            | polars-avro          | klaw-dbase (current)     | klaw-dbase (target)           |
| ----------------- | -------------------- | ------------------------ | ----------------------------- |
| Send+Sync         | ❌ Not supported     | ❌ Not supported         | ✅ Full support               |
| Progress tracking | ❌ None              | ✅ Basic                 | ✅ Modal (None/Total/PerFile) |
| Parallel files    | ❌ Sequential only   | ❌ Sequential only       | ✅ Rayon parallel             |
| Parallel columns  | ❌ Sequential        | ✅ Rayon in read_columns | ✅ Enhanced                   |
| Random access     | ❌ Avro is streaming | ❌ Not used              | ✅ Seek support               |
| Compression       | ❌ N/A               | ✅ DBC support           | ✅ DBC support                |
| Encoding          | Avro binary          | Trait objects (yore)     | encoding_rs enum              |

### 9.5 Key Takeaways

1. **We're already using most of polars-avro's patterns correctly**
1. **DBF format allows optimizations Avro can't do** (parallel, seeking)
1. **Our main gap is Send+Sync** - encoding trait objects block parallelism
1. **Progress tracking is our unique feature** - enhance, don't remove
1. **The refactor plan (Phases 1-5) addresses all gaps**

______________________________________________________________________

## Appendix: InfallableIter Pattern

The InfallableIter pattern from polars-avro should be preserved:

```rust
// read.rs:179-198

/// An infallible error type for iterators that cannot fail
pub enum Infallable {}

impl From<Infallable> for ValueError {
    fn from(_: Infallable) -> Self {
        unreachable!()
    }
}

/// Wrapper to convert an infallible iterator into a Result iterator
pub struct InfallableIter<I>(pub I);

impl<I: Iterator> Iterator for InfallableIter<I> {
    type Item = Result<I::Item, Infallable>;

    fn next(&mut self) -> Option<Self::Item> {
        self.0.next().map(Result::Ok)
    }
}

impl<I: ExactSizeIterator> ExactSizeIterator for InfallableIter<I> {}
impl<I: FusedIterator> FusedIterator for InfallableIter<I> {}
```

This allows unified error handling for both fallible (file-based) and infallible (memory-based) iterators.
