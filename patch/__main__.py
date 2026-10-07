"""CLI entry point for cross-checking `res/` + `patch/` against `static/`."""

from . import verify_all_versions_against_static

if __name__ == "__main__":
    verify_all_versions_against_static()
