"""
Modular GApps Release Analyzer & Deep Comparator Package.
Provides:
  - zip_inspector: Lightweight HTTP Range & Local ZIP inspection
  - xml_analyzer: Deep semantic XML parsing & diffing for any XML difference
  - apk_analyzer: Zero-download binary AXML / aapt APK versionName & versionCode extraction
  - report_generator: Structured Markdown, Text, and JSON table report formatting
"""

from .zip_inspector import RemoteZipInspector
from .xml_analyzer import compare_xml_files
from .apk_analyzer import compare_apk_files
from .report_generator import generate_reports

