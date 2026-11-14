# Velet Presicion 1.0.5

Smooths the client gun marker during manual aiming, artillery aiming and target lock. Built for the installed World of Tanks EU 2.4.1.1 client.

The vanilla rotator ticks at 10 Hz: the marker is recomputed ten times per second and glides to each new point. This mod keeps the same shot point but drives the local tick from the frame clock, so the marker is refreshed every frame (120 Hz target, 240 Hz ceiling) while the server still receives tracking points at the vanilla `SERVER_TICK_LENGTH`.

- **Every-frame tick** — `VehicleGunRotator.__onTick` gets `__ROTATION_TICK_LENGTH` equal to the measured frame interval and `__INSUFFICIENT_TIME_DIFF` lowered, so the rotation step, the turret matrix and the marker all advance with the frame instead of every 100 ms. The next callback is scheduled at half of that interval, so the tick locks to one frame on any refresh rate instead of beating between 60/120/144 Hz.
- **Screen-space display marker** — `DefaultGunMarkerComponent._setupDataProvider` is wrapped to hand the crosshair a `GUI.WGGunMarkerDataProvider` driven by the mod. Its source point is projected through the camera and placed at a fixed depth, so a hit point that jumps in 3D while barely moving on screen no longer sweeps the marker across the world.
- **Smooth size changes** — `_DefaultGunMarkerController.update` feeds the display provider the current size and offset, so the dispersion circle grows and shrinks with the stock relax instead of snapping.
- **Velocity-carrying interpolation** — the artillery marker animation is rebuilt as 8 keyframes along the projected path. The first sub-step starts at the screen speed of the previous segment (monotone cubic Hermite, capped at 3x, no overshoot), so consecutive segments join without a visible corner. Segment length is measured perpendicular to the camera axis and divided by depth, i.e. in screen space.
- **Artillery** — `strategic` and `arty` control modes use the same tick and the same keyframes through `_SPGGunMarkerController`, which inherits `_GunMarkerController._updateMatrixProvider`, so the circle is fed fresh gun angles every frame.
- **Artillery without the drag** — `WGSPGGunMarkerDataProvider.setRelaxTime` is lowered to the measured frame interval on every client SPG update, so the cone snaps to the gun instead of chasing it for 100 ms. `_SPGGunMarkerController.disable` is wrapped to put `SERVER_TICK_LENGTH` back before the vanilla bookkeeping reads the value, which keeps replay and re-entry paths on the stock number.
- **Target lock** — the predicted lock point is recomputed every frame, so the marker follows the target without the 100 ms staircase. Server tracking stays at 10 Hz.
- **Fine mouse** — with `fine_mouse` on, `ArcadeCamera.update` and `SniperCamera.update` scale small mouse deltas by a pixel-derived gain: the first counts move the camera at ≈0.65 screen pixel each, blending back to the stock sensitivity over 10 counts. Large flicks keep the stock feel.
- **Vanilla elsewhere** — replays, observer mode, hull aiming, `clientMode == False`, `fixedShotAngles` and armed shot positions keep the stock 10 Hz tick and the stock two-keyframe animation.

Config: `mods/configs/velet_presicion/config.json`. `enabled` turns the whole mod off; `artillery` and `target_lock` turn off only those two modes; `fine_mouse` turns off only the fine aiming. A missing file or missing key means the stock default (`false` for `fine_mouse`, `true` for the rest).

```json
{
  "enabled": true,
  "artillery": true,
  "target_lock": true,
  "fine_mouse": false
}
```

## Package

`ua.velet_presicion_1.0.5.wotmod` is a standalone `ZIP_STORED` package containing `meta.xml` and Python 2.7 bytecode at `res/scripts/client/gui/mods/mod_velet_presicion.pyc`.

## Verification

```powershell
py27_dist\python.exe -B src/mods/velet_presicion/test_velet_presicion.py src/mods/velet_presicion/mod_velet_presicion.py
```

The suite loads `__onTick`, `__getTimeDiff` and `_updateMatrixProvider` straight from `res/packages/scripts.pkg`, runs the real tick against a simulated frame clock and checks: tick rate above the vanilla 10 Hz for arcade, sniper, strategic, arty and target lock, adaptive interval under 20 ms, server cadence unchanged at 10 Hz everywhere, vanilla timing for replay/server/postmortem modes, per-mode config switches, the SPG cone relax following the frame on the client and staying at `SERVER_TICK_LENGTH` on the server marker and after `disable`, screen-linear depth crossing, velocity continuity between segments, monotone keyframes without overshoot, the display provider replacing and releasing the stock one, marker size relax, fine-mouse gain at small and large deltas, and the disabled-config fallback.

Frame-rate check used during development (ticks per second at a fixed frame clock): 60 fps to 60, 120 to 120, 144 to 144, 180 to 180, 240 to 240.
