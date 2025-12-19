pub mod py;

use pyo3::prelude::*;

#[pymodule]
#[pyo3(name = "_random_rs")]
fn klaw_random_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<py::PyRand>()?;
    m.add_function(wrap_pyfunction!(py::rand_u32, m)?)?;
    m.add_function(wrap_pyfunction!(py::rand_u64, m)?)?;
    m.add_function(wrap_pyfunction!(py::rand_f32, m)?)?;
    m.add_function(wrap_pyfunction!(py::rand_f64, m)?)?;
    m.add_function(wrap_pyfunction!(py::rand_range_u64, m)?)?;
    // Python random API compatible functions
    m.add_function(wrap_pyfunction!(py::random, m)?)?;
    m.add_function(wrap_pyfunction!(py::randint, m)?)?;
    m.add_function(wrap_pyfunction!(py::uniform, m)?)?;
    m.add_function(wrap_pyfunction!(py::choice, m)?)?;
    m.add_function(wrap_pyfunction!(py::shuffle, m)?)?;
    m.add_function(wrap_pyfunction!(py::sample, m)?)?;
    m.add_function(wrap_pyfunction!(py::choices, m)?)?;
    m.add_function(wrap_pyfunction!(py::gauss, m)?)?;
    Ok(())
}
