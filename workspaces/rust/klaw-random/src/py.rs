//! PyO3 bindings for FRand

use frand::Rand;
use pyo3::exceptions::{PyIndexError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyList;

/// Fast pseudo-random number generator
///
/// A blazingly fast, non-cryptographic PRNG with 5-7x better performance than
/// standard random libraries.
#[pyclass]
pub struct PyRand {
    rng: Rand,
}

#[pymethods]
impl PyRand {
    /// Create a new RNG instance
    #[new]
    fn new() -> Self {
        PyRand {
            rng: Rand::new(),
        }
    }

    /// Generate a random u32
    fn gen_u32(&mut self) -> u32 {
        self.rng.gen::<u32>()
    }

    /// Generate a random u64
    fn gen_u64(&mut self) -> u64 {
        self.rng.gen::<u64>()
    }

    /// Generate a random f32 in [0.0, 1.0)
    fn gen_f32(&mut self) -> f32 {
        self.rng.gen::<f32>()
    }

    /// Generate a random f64 in [0.0, 1.0)
    fn gen_f64(&mut self) -> f64 {
        self.rng.gen::<f64>()
    }

    /// Generate a random integer in [start, end)
    fn gen_range(&mut self, start: u64, end: u64) -> u64 {
        if start >= end {
            panic!("start must be less than end");
        }
        let range = end - start;
        let random = self.rng.gen::<u64>();
        start + (random % range)
    }

    /// Generate multiple random f64 values
    fn gen_multiple_f64(&mut self, count: usize) -> Vec<f64> {
        (0..count).map(|_| self.rng.gen::<f64>()).collect()
    }

    /// Generate multiple random u64 values
    fn gen_multiple_u64(&mut self, count: usize) -> Vec<u64> {
        (0..count).map(|_| self.rng.gen::<u64>()).collect()
    }

    // ========== Python random API compatible methods ==========

    /// Seed the random number generator with an integer.
    ///
    /// Note: FRand uses time-based seeding internally. This method creates
    /// a new RNG instance. For reproducible sequences, use the same seed.
    fn seed(&mut self, a: Option<u64>) {
        match a {
            Some(seed_val) => {
                self.rng = Rand::with_seed(seed_val);
            }
            None => {
                self.rng = Rand::new();
            }
        }
    }

    /// Return a random float in [0.0, 1.0).
    ///
    /// Compatible with Python's random.random()
    fn random(&mut self) -> f64 {
        self.rng.gen::<f64>()
    }

    /// Return a random integer N such that a <= N <= b.
    ///
    /// Compatible with Python's random.randint(a, b)
    fn randint(&mut self, a: i64, b: i64) -> PyResult<i64> {
        if a > b {
            return Err(PyValueError::new_err("empty range for randint()"));
        }
        let range = (b - a + 1) as u64;
        let random = self.rng.gen::<u64>();
        Ok(a + (random % range) as i64)
    }

    /// Return a random float N such that a <= N <= b.
    ///
    /// Compatible with Python's random.uniform(a, b)
    fn uniform(&mut self, a: f64, b: f64) -> f64 {
        let t = self.rng.gen::<f64>();
        a + t * (b - a)
    }

    /// Return a random element from the non-empty sequence.
    ///
    /// Compatible with Python's random.choice(seq)
    fn choice<'py>(&mut self, seq: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let len: usize = seq.len()?;
        if len == 0 {
            return Err(PyIndexError::new_err("Cannot choose from an empty sequence"));
        }
        let idx = (self.rng.gen::<u64>() as usize) % len;
        seq.get_item(idx)
    }

    /// Shuffle list x in place.
    ///
    /// Compatible with Python's random.shuffle(x)
    fn shuffle(&mut self, x: &Bound<'_, PyList>) -> PyResult<()> {
        let len = x.len();
        if len <= 1 {
            return Ok(());
        }
        for i in (1..len).rev() {
            let j = (self.rng.gen::<u64>() as usize) % (i + 1);
            if i != j {
                let temp = x.get_item(i)?;
                x.set_item(i, x.get_item(j)?)?;
                x.set_item(j, temp)?;
            }
        }
        Ok(())
    }

    /// Return a k-length list of unique elements chosen from the population.
    ///
    /// Compatible with Python's random.sample(population, k)
    fn sample<'py>(
        &mut self,
        py: Python<'py>,
        population: &Bound<'py, PyAny>,
        k: usize,
    ) -> PyResult<Bound<'py, PyList>> {
        let len: usize = population.len()?;
        if k > len {
            return Err(PyValueError::new_err(
                "Sample larger than population or is negative",
            ));
        }

        let mut indices: Vec<usize> = (0..len).collect();
        for i in (1..len).rev() {
            let j = (self.rng.gen::<u64>() as usize) % (i + 1);
            indices.swap(i, j);
        }

        let result = PyList::empty(py);
        for &idx in indices.iter().take(k) {
            result.append(population.get_item(idx)?)?;
        }
        Ok(result)
    }

    /// Return a k-length list of elements chosen from the population with replacement.
    ///
    /// Compatible with Python's random.choices(population, k=k)
    #[pyo3(signature = (population, k=1))]
    fn choices<'py>(
        &mut self,
        py: Python<'py>,
        population: &Bound<'py, PyAny>,
        k: usize,
    ) -> PyResult<Bound<'py, PyList>> {
        let len: usize = population.len()?;
        if len == 0 {
            return Err(PyValueError::new_err("Cannot choose from an empty population"));
        }
        let result = PyList::empty(py);
        for _ in 0..k {
            let idx = (self.rng.gen::<u64>() as usize) % len;
            result.append(population.get_item(idx)?)?;
        }
        Ok(result)
    }

    /// Return a random float from a Gaussian distribution.
    ///
    /// mu is the mean, sigma is the standard deviation.
    /// Compatible with Python's random.gauss(mu, sigma)
    fn gauss(&mut self, mu: f64, sigma: f64) -> f64 {
        let u1 = self.rng.gen::<f64>();
        let u2 = self.rng.gen::<f64>();
        let z0 = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
        mu + z0 * sigma
    }
}

/// Generate a random u32
#[pyfunction]
pub fn rand_u32() -> u32 {
    let mut rng = Rand::new();
    rng.gen::<u32>()
}

/// Generate a random u64
#[pyfunction]
pub fn rand_u64() -> u64 {
    let mut rng = Rand::new();
    rng.gen::<u64>()
}

/// Generate a random f32 in [0.0, 1.0)
#[pyfunction]
pub fn rand_f32() -> f32 {
    let mut rng = Rand::new();
    rng.gen::<f32>()
}

/// Generate a random f64 in [0.0, 1.0)
#[pyfunction]
pub fn rand_f64() -> f64 {
    let mut rng = Rand::new();
    rng.gen::<f64>()
}

/// Generate a random integer in [start, end)
#[pyfunction]
pub fn rand_range_u64(start: u64, end: u64) -> u64 {
    if start >= end {
        panic!("start must be less than end");
    }
    let mut rng = Rand::new();
    let range = end - start;
    let random = rng.gen::<u64>();
    start + (random % range)
}

// ========== Python random API compatible module-level functions ==========

/// Return a random float in [0.0, 1.0).
///
/// Compatible with Python's random.random()
#[pyfunction]
pub fn random() -> f64 {
    let mut rng = Rand::new();
    rng.gen::<f64>()
}

/// Return a random integer N such that a <= N <= b.
///
/// Compatible with Python's random.randint(a, b)
#[pyfunction]
pub fn randint(a: i64, b: i64) -> PyResult<i64> {
    if a > b {
        return Err(PyValueError::new_err("empty range for randint()"));
    }
    let mut rng = Rand::new();
    let range = (b - a + 1) as u64;
    let random_val = rng.gen::<u64>();
    Ok(a + (random_val % range) as i64)
}

/// Return a random float N such that a <= N <= b.
///
/// Compatible with Python's random.uniform(a, b)
#[pyfunction]
pub fn uniform(a: f64, b: f64) -> f64 {
    let mut rng = Rand::new();
    let t = rng.gen::<f64>();
    a + t * (b - a)
}

/// Return a random element from the non-empty sequence.
///
/// Compatible with Python's random.choice(seq)
#[pyfunction]
pub fn choice<'py>(seq: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let len: usize = seq.len()?;
    if len == 0 {
        return Err(PyIndexError::new_err("Cannot choose from an empty sequence"));
    }
    let mut rng = Rand::new();
    let idx = (rng.gen::<u64>() as usize) % len;
    seq.get_item(idx)
}

/// Shuffle list x in place.
///
/// Compatible with Python's random.shuffle(x)
#[pyfunction]
pub fn shuffle(x: &Bound<'_, PyList>) -> PyResult<()> {
    let len = x.len();
    if len <= 1 {
        return Ok(());
    }
    let mut rng = Rand::new();
    for i in (1..len).rev() {
        let j = (rng.gen::<u64>() as usize) % (i + 1);
        if i != j {
            let temp = x.get_item(i)?;
            x.set_item(i, x.get_item(j)?)?;
            x.set_item(j, temp)?;
        }
    }
    Ok(())
}

/// Return a k-length list of unique elements chosen from the population.
///
/// Compatible with Python's random.sample(population, k)
#[pyfunction]
pub fn sample<'py>(
    py: Python<'py>,
    population: &Bound<'py, PyAny>,
    k: usize,
) -> PyResult<Bound<'py, PyList>> {
    let len: usize = population.len()?;
    if k > len {
        return Err(PyValueError::new_err(
            "Sample larger than population or is negative",
        ));
    }

    let mut rng = Rand::new();
    let mut indices: Vec<usize> = (0..len).collect();
    for i in (1..len).rev() {
        let j = (rng.gen::<u64>() as usize) % (i + 1);
        indices.swap(i, j);
    }

    let result = PyList::empty(py);
    for &idx in indices.iter().take(k) {
        result.append(population.get_item(idx)?)?;
    }
    Ok(result)
}

/// Return a k-length list of elements chosen from the population with replacement.
///
/// Compatible with Python's random.choices(population, k=k)
#[pyfunction]
#[pyo3(signature = (population, k=1))]
pub fn choices<'py>(
    py: Python<'py>,
    population: &Bound<'py, PyAny>,
    k: usize,
) -> PyResult<Bound<'py, PyList>> {
    let len: usize = population.len()?;
    if len == 0 {
        return Err(PyValueError::new_err("Cannot choose from an empty population"));
    }
    let mut rng = Rand::new();
    let result = PyList::empty(py);
    for _ in 0..k {
        let idx = (rng.gen::<u64>() as usize) % len;
        result.append(population.get_item(idx)?)?;
    }
    Ok(result)
}

/// Return a random float from a Gaussian distribution.
///
/// mu is the mean, sigma is the standard deviation.
/// Compatible with Python's random.gauss(mu, sigma)
#[pyfunction]
pub fn gauss(mu: f64, sigma: f64) -> f64 {
    let mut rng = Rand::new();
    let u1 = rng.gen::<f64>();
    let u2 = rng.gen::<f64>();
    let z0 = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
    mu + z0 * sigma
}
