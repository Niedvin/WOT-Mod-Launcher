# Building the Niedvin modpack

Build with a World of Tanks EU 2.4.1.1 installation and the game closed. Use `source-map.json` to map source files to the game folder. Back up existing files before copying over them.

Build the in-game manager with x64 Python 2.7 available at `py27_dist/python.exe` and Python 3.12 on PATH. From the game root:

```powershell
python mod_manager/build.py
.\py27_dist\python.exe -B -m mod_manager.test_manager
node --check mod_manager/ui/mod-manager.js
```

The builder copies the native hangar markup from the installed client and packages the manager in `build/mod_manager/`. Use `--install` to stage the manager in the active game version with backups.

The other mods are declared in `src/mods/<id>/mod.json`. The build may also need Node.js, Visual Studio C++ x64 tools and Windows SDK for their assets and native modules.

Prepare a release from verified packages already installed in a local game folder and the preceding release manifest:

```powershell
python src/publish_release.py --previous-manifest <manifest.json> --game-root <game-folder> --manager <manager.wotmod> --pack-version <version> --output <new-folder>
```

Upload the resulting ZIP, manifest and individual packages together. The ZIP contains the default selection from the manifest. The publisher checks existing packages against the preceding release hashes.
