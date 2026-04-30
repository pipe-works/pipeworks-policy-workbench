"""Sphinx configuration for the Pipeworks Policy Workbench docs."""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Make the source tree importable so autodoc can resolve symbols.
sys.path.insert(0, os.path.abspath("../.."))
sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------

project = "Pipeworks Policy Workbench"
author = "aapark"
copyright = f"2026, {author}"

try:
    release = _pkg_version("pipeworks-policy-workbench")
except PackageNotFoundError:
    release = "0.0.0-dev"
version = release

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinxcontrib.mermaid",
]

# Render Mermaid diagrams as inline SVG so RTD/PDF builds work without a
# headless browser. The default ("raw") relies on a client-side mermaid.js
# bundle, which doesn't help non-HTML formats.
mermaid_output_format = "raw"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns: list[str] = []

language = "en"

# -- HTML output -------------------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "includehidden": True,
    "titles_only": False,
}

# -- Autodoc / napoleon ------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

todo_include_todos = True
