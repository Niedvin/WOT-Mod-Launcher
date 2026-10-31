# Building the modpack

This repository stores mod and launcher source. It does not contain the game client, Python runtime, private signing key, user configuration, logs or backups.

Build inside a backed-up World of Tanks EU 2.4.1.1 installation with the game closed. `source-map.json` maps each repository file to its destination relative to the game root. Inspect and back up existing files before copying them. Preserve existing configuration files.

Prerequisites: Python 3, a matching x64 Python 2.7 runtime with headers and import library in `py27_dist/`, Node.js, .NET Framework 4.x compiler, Visual Studio C++ x64 tools and Windows SDK. Install the released modpack first to supply framework packages and staging metadata. The packaging script uses a local Authenticode certificate; replace its certificate thumbprint with your own. No private certificate is distributed.

From the game root:

```powershell
python scratch/background_fps/build_native_focus.py
python scratch/build_mods.py
node --check scratch/research_btn/out_mono/bundle.js
python scratch/build_installer.py
python scratch/publish_release.py
```

Mod development and installer packaging are separate commands. Unit tests are opt-in and are not included in the default build. Research artwork uses the client's original module-button default/hover PNGs and the included `research_action.png`; `mono_build.py` fails if the expected native hangar component changes.

Research and FPS packages include their complete external resource payloads. On initialization, the mods verify and install their own payloads with backups. Research preserves an unrecognized shared Gameface override. Future owned overrides use a SHA-256 sidecar to distinguish them from other modifications.

The launcher normally opens the update panel before starting the game. `--update-only` runs the actual network update flow and exits without starting the game. `--check-only` performs a silent availability check. These options do not change `launcher.json` or redirect the public update source.

Release files are generated in `build/release_assets/`: 12 mod/framework packages, launcher, manifest, single-file installer and ZIP. Publish only after explicit user authorization and validate uploaded asset hashes. The installer is self-signed; its certificate is not trusted by Windows by default.

Spectator equipment placement is compiled and packaged, but still requires observation after death in a real battle. Component previews and package checks do not establish that behavior.
