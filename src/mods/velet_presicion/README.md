# Velet Presicion 1.0.6

Smooths the client gun marker during manual aiming, artillery aiming and target lock. Built for the installed World of Tanks EU 2.4.1.1 client.

The vanilla rotator ticks at 10 Hz: the marker is recomputed ten times per second and glides to each new point. This mod keeps the same shot point but drives the local tick from the frame clock, so the marker is refreshed every frame (120 Hz target, 240 Hz ceiling) while the server still receives tracking points at the vanilla `SERVER_TICK_LENGTH`.

- **Every-frame tick** — `VehicleGunRotator.__onTick` gets `__ROTATION_TICK_LENGTH` equal to the measured frame interval and `__INSUFFICIENT_TIME_DIFF` lowered, so the rotation step, the turret matrix and the marker all advance with the frame instead of every 100 ms. The next callback is scheduled at half of that interval, so the tick locks to one frame on any refresh rate instead of beating between 60/120/144 Hz.
- **Screen-space display marker** — `DefaultGunMarkerComponent._setupDataProvider` is wrapped to hand the crosshair a `GUI.WGGunMarkerDataProvider` driven by the mod. Its source point is projected through the camera and placed at a fixed depth, so a hit point that jumps in 3D while barely moving on screen no longer sweeps the marker across the world.
- **Smooth size changes** — `_DefaultGunMarkerController.update` feeds the display provider the current size and offset, so the dispersion circle grows and shrinks with the stock relax instead of snapping.
- **Artillery** — `strategic` and `arty` retain frame-based aiming. The game blends the dots between dispersion updates, with 100 ms between regular updates so its renderer can finish processing the ring.
- **Target lock** — the predicted lock point is recomputed every frame, so the marker follows the target without the 100 ms staircase. Server tracking stays at 10 Hz.
- **Fine mouse** — with `fine_mouse` on, `ArcadeCamera.update` and `SniperCamera.update` scale small mouse deltas by a pixel-derived gain: the first counts move the camera at ≈0.65 screen pixel each, blending back to the stock sensitivity over 10 counts. Large flicks keep the stock feel.
- **Vanilla elsewhere** — replays, observer mode, hull aiming, `clientMode == False`, `fixedShotAngles` and armed shot positions keep the stock 10 Hz tick and the stock two-keyframe animation.

`mods/configs/velet_presicion/config.json` sets `enabled`, `artillery` and `target_lock` to `true` by default and `fine_mouse` to `false`.

```json
{
  "enabled": true,
  "artillery": true,
  "target_lock": true,
  "fine_mouse": false
}
```

## Package

`ua.velet_presicion_1.0.6.wotmod` is a standalone `ZIP_STORED` package containing `meta.xml` and Python 2.7 bytecode at `res/scripts/client/gui/mods/mod_velet_presicion.pyc`.

## Verification

```powershell
py27_dist\python.exe -B src/mods/velet_presicion/test_velet_presicion.py src/mods/velet_presicion/mod_velet_presicion.py
```

The suite loads `__onTick`, `__getTimeDiff` and `_updateMatrixProvider` from `res/packages/scripts.pkg` and runs them against a simulated frame clock. It checks normal and dual-accuracy display smoothing, completion of the artillery dot queue during frame-based aiming, server cadence, replay and observer timing, fine-mouse gain, and config switches.

Frame-rate check used during development (ticks per second at a fixed frame clock): 60 fps to 60, 120 to 120, 144 to 144, 180 to 180, 240 to 240.
