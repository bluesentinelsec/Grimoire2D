"""Grimoire2D game framework.

The package root provides only the public version for now.
All real functionality lives in the subpackages (models for data, logic for business rules, presentation for front-end, ...).

This makes the data-model / logic / presentation separation obvious and scalable.
"""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("grimoire2d")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"