# Pure Google GApps Builder & Auto-Sync

100% genuine, pure Google GApps extractor and automated release pipeline without any third-party repositories or modified binaries.

## How It Works

1. **Direct Google Communication (`check_updates.py`)**:
   - Queries `https://dl.google.com/android/repository/sys-img/google_apis_playstore/sys-img2-3.xml` directly.
   - Detects new official Google releases, revisions, and checksums for Android 9, 10, 11, 12, 13, 14, 15.
   - Triggers build only when Google actually publishes an update.

2. **Pure Extraction (`extract_pure_gapps.py`)**:
   - Downloads official Google system images directly from `dl.google.com`.
   - Extracts genuine Google APKs (`GmsCore`, `Phonesky`, `GoogleServicesFramework`, etc.), permissions XMLs, sysconfigs, and native libraries.
   - Packages into standard clean format: `GoogleGapps-<version>-<arch>.zip`.

3. **Automated Parallel Workflow (`.github/workflows/pure_google_gapps.yml`)**:
   - Runs daily cron or manual trigger.
   - Builds all versions in parallel.
   - Publishes directly to GitHub Releases.
