"""Convenience launcher: python run.py"""
import os
import sys

if sys.version_info < (3, 10):
    sys.exit("Python 3.10+ required.")

os.system(f"{sys.executable} -m uvicorn app.main:app --reload --port {os.getenv('PORT', '8000')}")
