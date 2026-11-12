# Velet Presicion 1.0.2

Smooths the client gun marker during manual aiming, artillery aiming and target lock. Built for the installed World of Tanks EU 2.4.1.1 client.

The vanilla rotator ticks at 10 Hz: the marker is recomputed ten times per second and glides to each new point. This mod keeps the same shot point but drives the local tick from the frame clock, so the marker is refreshed every frame (120 Hz target, 240 Hz ceiling) while the server still receives tracking points at the vanilla `SERVER_TICK_LENGTH`.

- **Every-frame tick** — `VehicleGunRotator.__onTick` gets `__ROTATION_TICK_LENGTH` equal to the measured frame interval and `__INSUFFICIENT_TIME_DIFF` lowered, so the rotation step, the turret matrix and the marker all advance with the frame instead of every 100 ms. The next callback is scheduled at half of that interval, so the tick locks to one frame on any refresh rate instead of beating between 60/120/144 Hz.
- **Velocity-carrying interpolation** — the marker animation is rebuilt as 8 keyframes along the projected path. The first sub-step starts at the screen speed of the previous segment (monotone cubic Hermite, capped at 3x, no overshoot), so consecutive segments join without a visible corner. Segment length is measured perpendicular to the camera axis and divided by depth, i.e. in screen space.
- **Depth jumps in screen space** — when the ray crosses a crest or a wall the hit point jumps in 3D while barely moving on screen. Keyframe positions use perspective-correct weights, so the marker keeps a straight, even path on screen instead of sweeping through the world.
- **Artillery** — `strategic` and `arty` control modes use the same tick and the same keyframes through `_SPGGunMarkerController`, which inherits `_GunMarkerController._updateMatrixProvider`, so the circle is fed fresh gun angles every frame. The GUI conic dispersion keeps its engine relax time; only the update rate changes.
- **Target lock** — the predicted lock point is recomputed every frame, so the marker follows the target without the 100 ms staircase. Server tracking stays at 10 Hz.
- **Vanilla elsewhere** — replays, observer mode, hull aiming, `clientMode == False`, `fixedShotAngles` and armed shot positions keep the stock 10 Hz tick and the stock two-keyframe animation.

Config: `mods/configs/velet_presicion/config.json`. `enabled` turns the whole mod off; `artillery` and `target_lock` turn off only those two modes. A missing file or missing key means `true`.

```json
{
  "enabled": true,
  "artillery": true,
  "target_lock": true
}
```

## Package

`ua.velet_presicion_1.0.2.wotmod` is a standalone `ZIP_STORED` package containing `meta.xml` and Python 2.7 bytecode at `res/scripts/client/gui/mods/mod_velet_presicion.pyc`.

## Verification

```powershell
py27_dist\python.exe -B src/mods/velet_presicion/test_velet_presicion.py src/mods/velet_presicion/mod_velet_presicion.py
```

The suite loads `__onTick`, `__getTimeDiff` and `_updateMatrixProvider` straight from `res/packages/scripts.pkg`, runs the real tick against a simulated frame clock and checks: tick rate above the vanilla 10 Hz for arcade, sniper, strategic, arty and target lock, adaptive interval under 20 ms, server cadence unchanged at 10 Hz everywhere, vanilla timing for replay/server/postmortem modes, per-mode config switches, screen-linear depth crossing, velocity continuity between segments, monotone keyframes without overshoot, and the disabled-config fallback.

Frame-rate check used during development (ticks per second at a fixed frame clock): 60 fps to 60, 120 to 120, 144 to 144, 180 to 180, 240 to 240.
