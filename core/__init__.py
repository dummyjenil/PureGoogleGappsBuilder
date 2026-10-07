"""
PureGoogleGappsBuilder Core Package
Centralized modular architecture for building genuine Google GApps flashable packages.
"""

from .constants import (
    SDK_MAP,
    APK_PACKAGE_MAP,
    ARCH_TO_TOYBOX,
    ABI_TO_LIB_DIR,
    TARGET_APP_PATTERNS,
    PRIV_APPS_LIST,
    EXCLUDED_AOSP_APPS,
    ADDOND_HEAD,
    ADDOND_TAIL
)
from .downloader import download_file
from .extractor import (
    is_genuine_google_file,
    unpack_partition_filesystem,
    extract_partition_from_container
)
from .packager import (
    structure_gapps_hierarchy,
    create_flashable_zip
)

__all__ = [
    "SDK_MAP",
    "APK_PACKAGE_MAP",
    "ARCH_TO_TOYBOX",
    "ABI_TO_LIB_DIR",
    "TARGET_APP_PATTERNS",
    "PRIV_APPS_LIST",
    "EXCLUDED_AOSP_APPS",
    "ADDOND_HEAD",
    "ADDOND_TAIL",
    "download_file",
    "is_genuine_google_file",
    "unpack_partition_filesystem",
    "extract_partition_from_container",
    "structure_gapps_hierarchy",
    "create_flashable_zip",
]
