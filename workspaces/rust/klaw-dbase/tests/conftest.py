"""Pytest configuration for klaw-dbase tests."""

import os
import pathlib
import sys

# Add tests directory to path for utils import
sys.path.insert(0, pathlib.Path(__file__).parent)

# Change to klaw-dbase directory so relative data paths work
os.chdir(pathlib.Path(pathlib.Path(__file__).parent).parent)
