#!/usr/bin/env python3
"""Kept for old habits: the pages are built by tools/build.py."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

build.main()
