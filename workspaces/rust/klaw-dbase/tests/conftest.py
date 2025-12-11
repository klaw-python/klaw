"""Pytest configuration for klaw-dbase tests."""

import os
import sys

# Add tests directory to path for utils import
sys.path.insert(0, os.path.dirname(__file__))

# Change to klaw-dbase directory so relative data paths work
os.chdir(os.path.dirname(os.path.dirname(__file__)))
