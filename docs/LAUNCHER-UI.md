# Launcher UI

`WotModLauncher.exe` uses the approved master/detail update layout. `Installer.exe` remains a separate application and is unchanged.

The left 62% contains one scrollable list, grouped into updates and new mods. Clicking a title reads its details without changing installation selection. Checkboxes select downloads. Each row has its own decline icon; confirmation names only that mod, preserves installed files and saves only its ID. New mods remain unchecked by default.

The right 38% shows full descriptions, authors and change notes from the release manifest. `description`, `author` and `summary` are optional fields, compatible with older launchers. Staging derives `summary` from the first existing `readme_features` entry, falling back to the full description. Missing change notes remain empty instead of being replaced by a description. Older manifests continue to work and display an explicit missing-description message.

The footer keeps update/play and skip actions visible. The overflow menu preserves launching without mods. Backup/download verification and rollback behavior are unchanged. A progress bar appears only while updating.

## Validation

On Linux with Mono, `mcs`, Xvfb, `timeout`, and Python 3 installed, run from the repository root:

```sh
bash tests/run_launcher_tests.sh
```

The runner creates isolated application-data and game-fixture directories and removes them on exit. It compiles the actual single-file launcher, runs native UI/update tests, then checks local and release manifest generation. Set `WOT_UI_SCREENSHOTS` to an absolute output directory to retain native captures. See `design-qa.md` for the visual comparison and Windows verification limits.

Launcher version: `1.4.4.0`. Build/sign the Windows release through the existing packaging process before publishing. No public release was created by this change.

Icons are from Lucide under the ISC license in `docs/licenses/lucide.txt`. The license is embedded in the executable's `LucideIconLicense` assembly metadata and accompanies the local build.
