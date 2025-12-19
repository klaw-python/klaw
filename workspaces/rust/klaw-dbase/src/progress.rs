use console::{Style, Term};
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

/// Progress callback type for monitoring DBC file reading
pub type ProgressCallback = Arc<dyn Fn(u64, u64, &str) + Send + Sync>;

/// DBC file reader with progress tracking
#[derive(Clone)]
pub struct DbaseProgressTracker {
    /// Multi-progress instance to manage all progress bars
    multi_progress: MultiProgress,
    /// Overall progress bar
    overall_pb: Option<ProgressBar>,
    /// Individual file progress bars
    file_progress_bars: Vec<ProgressBar>,
    /// Total records across all files
    total_records: u64,
    /// Current progress (records processed)
    current_progress: Arc<AtomicU64>,
}

pub struct DbaseFileInfo {
    pub name: String,
    pub record_count: u64,
    pub extension: String,
}

impl DbaseFileInfo {
    pub fn new(name: String, record_count: u64, extension: String) -> Self {
        Self {
            name,
            record_count,
            extension,
        }
    }

    fn get_file_name(&self) -> String {
        self.name.clone()
    }

    pub fn get_file_size(&self) -> u64 {
        self.record_count
    }
}

impl Default for DbaseFileInfo {
    fn default() -> Self {
        Self::new("".to_string(), 0, "unknown".to_string())
    }
}

/// Helper function to get the total size of all files
pub fn get_total_size(files: &[DbaseFileInfo]) -> u64 {
    files.iter().map(|f| f.get_file_size()).sum()
}

impl DbaseProgressTracker {
    /// Create a new progress tracker for multiple DBC files
    pub fn new(files: Vec<DbaseFileInfo>) -> Self {
        let total_records: u64 = get_total_size(&files);
        let current_progress = Arc::new(AtomicU64::new(0));

        // Create beautiful colored styles
        let blue_bold = Style::new().blue().bold();

        // Create a single MultiProgress instance to manage all progress bars
        let mp = MultiProgress::new();

        // Show startup message
        mp.println(format!(
            "    {} Reading {} DBC files ({:.1} M records total)",
            blue_bold.apply_to("Starting"),
            files.len(),
            total_records as f64 / 1_000_000.0
        ))
        .unwrap();

        // Determine appropriate template based on terminal width
        let term_width = Term::stdout().size().1;

        // per_sec, elapsed, duration, eta
        // Create OVERALL progress bar FIRST (at the top)
        let overall_template = if term_width > 100 {
            "{prefix:>12.blue.bold} {elapsed_precise:>16.yellow} {wide_bar:.green/black.dim} {percent:.white}% {eta_precise:.cyan} {pos:>6.magenta.dim}/{len:<2.magenta}"
        } else {
            "{prefix:>12.blue.bold} {elapsed_precise:.yellow} {wide_bar:.green/black.dim} {percent:.white}% {eta_precise:.cyan} {pos.magenta.dim}/{len.magenta}"
        };
        // bar = "-" if ascii else "━"

        let overall_pb = mp.add(ProgressBar::new(total_records));
        overall_pb.set_style(
            ProgressStyle::with_template(overall_template)
                .unwrap()
                .progress_chars("━━-"),
        );
        overall_pb.set_prefix("Reading ...");

        // Pre-create individual progress bars
        let mut file_progress_bars = Vec::new();

        let file_template = if term_width > 100 {
            "{spinner:.yellow} {msg:<18.green.bold} {elapsed_precise:<10.yellow.dim} {wide_bar:>2.green.dim/black.dim} {percent:.white.dim}% {eta_precise:.cyan.dim} {pos:>8.blue.dim}/{len:<8.blue}"
        } else {
            "{spinner:.yellow} {msg:<12.green.bold} {elapsed:<10.dim} {wide_bar:>2.green.dim/black.dim} {percent:.white.dim}% {eta:.cyan.dim} {pos.blue.dim}/{len.blue}"
        };

        for file in files.iter() {
            let pb = mp.add(ProgressBar::new(file.get_file_size()));
            pb.set_style(
                ProgressStyle::with_template(file_template)
                    .unwrap()
                    .progress_chars("━━-")
                    .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]),
            );
            pb.set_message(file.get_file_name().to_string());
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            file_progress_bars.push(pb);
        }

        Self {
            multi_progress: mp,
            overall_pb: Some(overall_pb),
            file_progress_bars,
            total_records,
            current_progress,
        }
    }

    /// Update progress for a specific file
    pub fn update_file_progress(&self, file_index: usize, records_read: u64) {
        if let Some(pb) = self.file_progress_bars.get(file_index) {
            let total = pb.length().unwrap_or(u64::MAX);
            let position = records_read.min(total);
            pb.set_position(position);
        }
    }

    /// Update overall progress
    pub fn update_overall_progress(&self, records_read: u64) {
        let current = self
            .current_progress
            .fetch_add(records_read, Ordering::SeqCst)
            + records_read;
        if let Some(pb) = &self.overall_pb {
            pb.set_position(current);
        }
    }

    /// Finish progress tracking with completion message
    pub fn finish(&self) {
        let total_millions = self.total_records as f64 / 1_000_000.0;
        let green_bold = Style::new().green().bold();
        let blue = Style::new().blue();

        if let Some(pb) = &self.overall_pb {
            pb.finish_and_clear();
        }

        self.multi_progress
            .println(format!(
                "    {:>12} {} files {}",
                green_bold.apply_to("✅ Completed"),
                self.file_progress_bars.len(),
                blue.apply_to(format!("({:.1} M records)", total_millions))
            ))
            .unwrap();
    }

    /// Get a progress callback for use in file reading
    pub fn create_progress_callback(&self, file_index: usize) -> impl Fn(u64, u64) + '_ {
        let tracker = self.current_progress.clone();
        let file_pb = self.file_progress_bars[file_index].clone();
        let overall_pb = self.overall_pb.as_ref().unwrap().clone();

        move |records_read: u64, _total: u64| {
            file_pb.set_position(records_read);
            let current = tracker.fetch_add(records_read, Ordering::SeqCst) + records_read;
            overall_pb.set_position(current);
        }
    }
}

/// Create a progress tracker for a single DBC file
pub fn create_single_file_progress(file: DbaseFileInfo) -> DbaseProgressTracker {
    DbaseProgressTracker::new(vec![file])
}

/// Create a progress tracker for multiple DBC files
pub fn create_multi_file_progress(files: Vec<DbaseFileInfo>) -> DbaseProgressTracker {
    DbaseProgressTracker::new(files)
}

/// Create a silent progress callback (no visual output)
pub fn create_silent_progress_callback() -> ProgressCallback {
    Arc::new(|_read: u64, _total: u64, _filename: &str| {
        // No output - silent mode
    })
}
