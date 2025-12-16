"""Hypothesis strategies for property-based testing of klaw-result types."""

from hypothesis import strategies as st

# Strategies for generating test values - to be expanded in Task 9.0

# Basic value strategies
integers = st.integers()
texts = st.text(min_size=0, max_size=100)
booleans = st.booleans()

# Exception strategies
exceptions = st.sampled_from(
    [
        ValueError("test"),
        TypeError("test"),
        RuntimeError("test"),
    ]
)
