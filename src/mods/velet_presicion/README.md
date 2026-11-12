# Velet Presicion 1.0.1

Smooths the client gun marker during manual aiming in arcade and sniper view. Built for the installed World of Tanks EU 2.4.1.1 client.

The vanilla rotator ticks at 10 Hz: the marker is recomputed ten times per second and glides to each new point. This mod keeps the same shot point but drives the local tick from the frame clock, so the marker is refreshed every frame (120 Hz target, 240 Hz ceiling) while the server still receives tracking points at the vanilla `SERVER_TICK_LENGTH`.

- **Every-frame tick** — `VehicleGunRotator.__onTick` gets `__ROTATION_TICK_LENGTH` equal to the measured frame interval and `__INSUFFICIENT_TIME_DIFF` lowered, so the rotation step, the turret matrix and the marker all advance with the frame instead of every 100 ms. The next callback is scheduled at half of that interval, so the tick locks to one frame on any refresh rate instead of beating between 60/120/144 Hz.
- **Velocity-carrying interpolation** — the marker animation is rebuilt as 8 keyframes along the projected path. The first sub-step starts at the screen speed of the previous segment (monotone cubic Hermite, capped at 3x, no overshoot), so consecutive segments join without a visible corner. Segment length is measured perpendicular to the camera axis and divided by depth, i.e. in screen space.
- **Depth jumps in screen space** — when the ray crosses a crest or a wall the hit point jumps in 3D while barely moving on screen. Keyframe positions use perspective-correct weights, so the marker keeps a straight, even path on screen instead of sweeping through the world.
- **Vanilla elsewhere** — artillery/strategic view, replays, observer mode, target lock, hull aiming and `clientMode == False` keep the stock 10 Hz tick. Server tracking updates stay throttled to `SERVER_TICK_LENGTH`; only the local marker is accelerated.

Config: `mods/configs/velet_presicion/config.json`, `{"enabled": false}` disables the mod without removing the package. A missing file means enabled.

## Package

`ua.velet_presicion_1.0.1.wotmod` is a standalone `ZIP_STORED` package containing `meta.xml` and Python 2.7 bytecode at `res/scripts/client/gui/mods/mod_velet_presicion.pyc`.

## Verification

```powershell
py27_dist\python.exe -B src/mods/velet_presicion/test_velet_presicion.py src/mods/velet_presicion/mod_velet_presicion.py
```

The suite loads `__onTick`, `__getTimeDiff` and `_updateMatrixProvider` straight from `res/packages/scripts.pkg`, runs the real tick against a simulated frame clock and checks: tick rate above the vanilla 10 Hz, adaptive interval under 20 ms, server cadence unchanged at 10 Hz, vanilla timing for replay/artillery/target-lock/server modes, screen-linear depth crossing, velocity continuity between segments, monotone keyframes without overshoot, and the disabled-config fallback.

Frame-rate check used during development (ticks per second at a fixed frame clock): 60 fps to 60, 120 to 120, 144 to 144, 180 to 180, 240 to 240.
