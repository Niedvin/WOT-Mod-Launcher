import argparse
import hashlib
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

REPO_BASE_URL = "https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download"
LAUNCHER_VERSION = "1.1.0"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def detect_game_version():
    with open("version.xml", "r", encoding="utf-8") as f:
        m = re.search(r"<version>\s*v\.([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", f.read())
        return m.group(1) if m else "2.4.1.0"

def parse_wotmod_meta(wotmod_path, fallback_fname):
    m = re.match(r"^(.+)_([0-9]+(?:\.[0-9]+)*)\.wotmod$", fallback_fname, re.IGNORECASE)
    mod_id = m.group(1) if m else fallback_fname.replace(".wotmod", "")
    mod_ver = m.group(2) if m else "1.0.0"
    try:
        with zipfile.ZipFile(wotmod_path, "r") as z:
            if "meta.xml" in z.namelist():
                root = ET.fromstring(z.read("meta.xml").decode("utf-8", errors="ignore"))
                id_el = root.find("id")
                ver_el = root.find("version")
                if id_el is not None and id_el.text and id_el.text.strip():
                    mod_id = id_el.text.strip()
                if ver_el is not None and ver_el.text and ver_el.text.strip():
                    mod_ver = ver_el.text.strip()
    except Exception:
        pass
    return mod_id, mod_ver

def bump_version(v):
    parts = v.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)

def iter_staged_wotmods():
    mods_root = os.path.join("staging_modpack", "Mods")
    for folder in sorted(os.listdir(mods_root)):
        mod_dir = os.path.join(mods_root, folder)
        info_path = os.path.join(mod_dir, "info.json")
        if not os.path.isfile(info_path):
            continue
        with open(info_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        ver_dir = os.path.join(mod_dir, "game_files", "mods", "_VERSION_")
        if not os.path.isdir(ver_dir):
            continue
        for root, _, files in os.walk(ver_dir):
            for fname in sorted(files):
                if not fname.endswith(".wotmod"):
                    continue
                full_path = os.path.join(root, fname)
                rel_sub = os.path.relpath(root, ver_dir).replace("\\", "/")
                if rel_sub == ".":
                    rel_sub = ""
                yield full_path, fname, rel_sub, info

def reset_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def local_test(game_ver, bump, out_dir):
    out_dir = os.path.abspath(out_dir)
    reset_dir(out_dir)

    launcher_src = os.path.join("staging_modpack", "Launcher", "WotModLauncher.exe")
    launcher_dst = os.path.join(out_dir, "WotModLauncher.exe")
    shutil.copy2(launcher_src, launcher_dst)
    launcher_version = bump_version(LAUNCHER_VERSION) if bump else LAUNCHER_VERSION

    mods_entries = []
    for full_path, fname, rel_sub, info in iter_staged_wotmods():
        w_id, w_ver = parse_wotmod_meta(full_path, fname)
        if bump:
            w_ver = bump_version(w_ver)
        shutil.copy2(full_path, os.path.join(out_dir, fname))
        mods_entries.append({
            "id": w_id,
            "title": info["title"] if not rel_sub else f"{info['title']} ({w_id})",
            "version": w_ver,
            "file": fname,
            "subdir": rel_sub,
            "url": os.path.abspath(os.path.join(out_dir, fname)),
            "sha256": sha256_file(full_path),
            "size": os.path.getsize(full_path),
            "changes": info.get("changes") or info.get("description", "")
        })

    manifest = {
        "schema": 1,
        "pack_version": datetime.now().strftime("%Y.%m.%d") + "-local-test",
        "game_version": game_ver,
        "launcher": {
            "version": launcher_version,
            "url": os.path.abspath(launcher_dst),
            "sha256": sha256_file(launcher_dst)
        },
        "mods": mods_entries
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("Local test manifest:", manifest_path)
    print()
    print("1. Install the modpack with WoT_Modpack_by_Niedvin_Setup.exe and close the game.")
    print("2. Prepare an outdated mod for the test (if live mods are already up to date):")
    print("   python scratch/local_update_test.py --stage-old ua.background_fps_limiter 1.0.0")
    print("3. Run the installed launcher against the local manifest:")
    print('   "%LOCALAPPDATA%\\WotModpack\\WotModLauncher.exe" --manifest "' + manifest_path + '"')
    print("   Expected: update window lists the mod; 'Оновити і грати' copies local files,")
    print("   verifies SHA-256/size/meta.xml, backs up to <game>\\.backups\\launcher\\<stamp>, launches the game.")
    print("4. Silent check without windows/game launch: add --check-only.")
    if bump:
        print("Note: --bump fakes versions (+0.0.1); after the test restore mods from")
        print("      <game>\\.backups\\launcher\\<stamp> or rerun the installer.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-test", action="store_true",
                    help="build a local manifest for launcher update testing (no GitHub)")
    ap.add_argument("--bump", action="store_true",
                    help="with --local-test: raise every version by +0.0.1 so the launcher sees updates")
    ap.add_argument("--out", default=None,
                    help="with --local-test: output dir (default build/local_test)")
    args = ap.parse_args()

    game_ver = detect_game_version()

    if args.local_test:
        local_test(game_ver, args.bump, args.out or os.path.join("build", "local_test"))
        return

    pack_ver = datetime.now().strftime("%Y.%m.%d")
    assets_dir = os.path.join("build", "release_assets")
    reset_dir(assets_dir)

    launcher_exe = os.path.join("staging_modpack", "Launcher", "WotModLauncher.exe")
    shutil.copy2(launcher_exe, os.path.join(assets_dir, "WotModLauncher.exe"))

    mods_entries = []
    for full_path, fname, rel_sub, info in iter_staged_wotmods():
        w_id, w_ver = parse_wotmod_meta(full_path, fname)
        title = info["title"] if not rel_sub else f"{info['title']} ({w_id})"
        changes = info.get("changes") or info.get("description", "")

        shutil.copy2(full_path, os.path.join(assets_dir, fname))
        mods_entries.append({
            "id": w_id,
            "title": title,
            "version": w_ver,
            "file": fname,
            "subdir": rel_sub,
            "url": f"{REPO_BASE_URL}/{fname}",
            "sha256": sha256_file(full_path),
            "size": os.path.getsize(full_path),
            "changes": changes
        })

    manifest = {
        "schema": 1,
        "pack_version": pack_ver,
        "game_version": game_ver,
        "launcher": {
            "version": LAUNCHER_VERSION,
            "url": f"{REPO_BASE_URL}/WotModLauncher.exe",
            "sha256": sha256_file(launcher_exe)
        },
        "mods": mods_entries
    }

    manifest_path = os.path.join(assets_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


    if os.path.isfile("WoT_Modpack_by_Niedvin.zip"):
        shutil.copy2("WoT_Modpack_by_Niedvin.zip", os.path.join(assets_dir, "WoT_Modpack_by_Niedvin.zip"))

    setup_exe = "WoT_Modpack_by_Niedvin_Setup.exe"
    if os.path.isfile(setup_exe):
        shutil.copy2(setup_exe, os.path.join(assets_dir, setup_exe))

    print(f"Prepared {len(mods_entries)} mod packages + manifest in {assets_dir}")

if __name__ == "__main__":
    main()
