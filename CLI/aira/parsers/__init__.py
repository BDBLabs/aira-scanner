"""Language adapters for AIRA's non-scoring error-signal inventory."""

from aira.parsers.base import ParserOutput
from aira.parsers.js_ts_signals import JavaScriptTypeScriptSignalParser
from aira.parsers.python_signals import PythonSignalParser

__all__ = ["JavaScriptTypeScriptSignalParser", "ParserOutput", "PythonSignalParser"]
