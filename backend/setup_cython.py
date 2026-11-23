"""
Cython compilation script for Chat-BI backend.
Compiles all .py files under app/ to .so shared libraries,
excluding __init__.py (package markers) and main.py (uvicorn entry point).

Usage:
    python setup_cython.py build_ext --inplace
"""
import os
from pathlib import Path
from setuptools import setup
from setuptools.extension import Extension
from Cython.Build import cythonize

APP_DIR = Path(__file__).resolve().parent / "app"
EXCLUDE_FILES = {"__init__.py", "main.py", "runtime.py", "worker.py", "script_process.py"}


def collect_extensions():
    extensions = []
    for py_file in sorted(APP_DIR.rglob("*.py")):
        if py_file.name in EXCLUDE_FILES:
            continue
        rel_path = py_file.relative_to(APP_DIR.parent)
        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
        extensions.append(Extension(module_name, [str(rel_path)]))
    return extensions


if __name__ == "__main__":
    extensions = collect_extensions()
    print(f"Found {len(extensions)} modules to compile")

    setup(
        name="chat_bi_compiled",
        ext_modules=cythonize(
            extensions,
            compiler_directives={
                "binding": True,
                "language_level": "3",
                "annotation_typing": False,  # disable C-level type enforcement for FastAPI Depends()
            },
            nthreads=0,  # single-threaded: avoids macOS spawn issues
        ),
    )
