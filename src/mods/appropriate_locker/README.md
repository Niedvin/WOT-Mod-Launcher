# Appropriate Locker 1.2.2

Built for the installed World of Tanks EU 2.4.1.1 client.

The mod is off at the start of every battle, so the first lock is always the vanilla one. A single press of `Q` switches it on; pressing `Q` again switches it back off. `Q` is used only for this toggle.

- **Off (`СТАНДАРТНИЙ ПРИЦІЛ`)**: the native `PlayerAvatar.autoAim` runs untouched — vanilla center lock, no surface capture, no sway.
- **On (`ТОЧНИЙ ПРИЦІЛ`)**: the existing target tracking command captures the visible enemy surface under the reticle (`_aimOffset`). The captured point follows that static collision part as the tank translates, turns its hull, rotates its turret or elevates its gun (resolving dynamic wheel/CGF colliders to their parent tank part). It does not choose a weak spot or add lead. When unlocked, standard vanilla magnetic auto-aim delegates normally; while surface tracking is active or within `0.6 s` after an explicit unlock, off-target magnetic prompts are ignored so RMB release never snaps to vehicle center.

Switching off while a surface lock is active hands the same target back to the native center lock instead of dropping it. Switching on while a native lock is active upgrades it to surface tracking when the reticle still hits that tank, otherwise the native lock stays until the next press.

The current mode is shown as a compact line in the battle hint panel, bottom centre above the ammo bar: `ЗАХОПЛЕННЯ ПРИЦІЛУ: ТОЧНЕ` or `ЗАХОПЛЕННЯ ПРИЦІЛУ: СТАНДАРТНЕ`. It appears only after a `Q` press, uses the normal hint style (no key binding, not the large centred message style), stays for `2 s` and then hides itself. It is registered with a lower priority than every native hint, so real battle tips temporarily replace it. Nothing is drawn at battle start before the first press.

Around the tracked surface point, two-tier tangent-plane sway operates perpendicular to the line of sight:
- **Moving (`Tight sway`, `<= 7 cm` / `0.07 m`)**: smooth randomized glides with short pauses (`0.2–0.6 s`) while either the own vehicle or the tracked surface part moves (`> 2 mm` / `2 cm/s`).
- **Stationary (`Micro-drifter`, `<= 1.4 cm` / `0.014 m`)**: once movement stops (`0.25 s` debounce + exponential decay, settling inside `1.4 cm` within `0.5 s`), calm bit-identical holds (`0.8–2.0 s`, skipped by native `__prevSentShotPoint` server packet deduplication) alternate with subtle slow glides.

Press the existing command again on the same target, or use the existing release command, to stop tracking. Arcade, sniper, dualgun and twinGun views are supported. Target departure, death, own death, a change to an unsupported camera, rotator stop or battle exit stops tracking and clears `AIMING_MODE.TARGET_LOCK` across all active and inactive control modes. Firing remains under the existing controls.

## Package

`ua.appropriate_locker_1.2.2.wotmod` is a standalone `ZIP_STORED` package containing `meta.xml` and Python 2.7 bytecode at `res/scripts/client/gui/mods/mod_appropriate_locker.pyc`, installed to `mods/2.4.1.1/ua.appropriate_locker_1.2.2.wotmod` when `--install` is passed to `build.py`.

## Account risk

Wargaming's prohibited-mods policy excludes auto-aim modifications with more functionality than the vanilla aim lock. Following a chosen surface point adds such functionality, and adding randomized sway/micro-drift does not exempt or guarantee protection against Fair Play enforcement. Use on the official service carries account suspension risk.

Primary source: https://worldoftanks.eu/en/content/guide/fair-play/prohibited-mods/

## Verification

Run `python -B scratch/appropriate_locker/build.py --run-tests --install` from the game directory to execute unit tests on source and packaged bytecode, verify all bytecode imports and native aiming/tracking methods against `res/packages/scripts.pkg`, and atomically install the verified `.wotmod` into `mods/2.4.1.1/`.

`validation.json` records exact checksums, counts and install status. `native-validation.json` records verified `scripts.pkg` imports and executed client bytecode hashes.

## Implementation references

Installed `res/packages/scripts.pkg` is the API authority (`TriggersManager.TRIGGER_TYPE`, `constants.AIMING_MODE`, `PlayerAvatar.autoAim`, `VehicleGunRotator.__onTick` / `__updateShotPointOnServer`). The raw `BigWorld.wg_collideDynamicStatic` result retains the collision part index discarded by `ProjectileMover.EntityCollisionData`. `CollisionComponent.getPartTransform` and `getParentPartIndex` supply the selected static part transform.
