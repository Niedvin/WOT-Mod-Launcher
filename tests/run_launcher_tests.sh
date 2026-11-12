#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
wot_test_dir=$(mktemp -d)
trap 'rm -rf "$wot_test_dir"' EXIT
mcs -target:winexe -optimize+ -r:System.Windows.Forms -r:System.Drawing -r:System.Core -r:System.Web.Extensions -r:System.IO.Compression -r:System.IO.Compression.FileSystem -win32manifest:src/build/app.manifest -win32icon:src/build/app.ico -out:"$wot_test_dir/WotModLauncher.exe" src/WotModLauncher.cs
mcs -r:System.Windows.Forms -r:System.Drawing -r:System.Core -r:System.Web.Extensions -r:System.IO.Compression -r:System.IO.Compression.FileSystem -r:"$wot_test_dir/WotModLauncher.exe" -out:"$wot_test_dir/LauncherUiTests.exe" tests/LauncherUiTests.cs
mkdir -p "$wot_test_dir/home/.local/share"
xvfb-run -a -s '-screen 0 1600x1200x24' env HOME="$wot_test_dir/home" XDG_DATA_HOME="$wot_test_dir/home/.local/share" WOT_UI_TEST_HOME="$wot_test_dir/home" timeout 45 mono "$wot_test_dir/LauncherUiTests.exe"
python3 -m unittest discover -s tests -p 'test_release_manifest.py' -v
