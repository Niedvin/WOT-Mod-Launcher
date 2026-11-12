# Launcher design verification

final result: passed

Scope: native launcher UI rendered with Mono WinForms on an isolated Xvfb display. This is not Windows runtime certification or a published release. The installer remains a separate executable.

## Evidence

- Selected target: `docs/design/launcher-reference.jpg`, 1487 × 1056 px.
- Native desktop capture: `docs/design/launcher-desktop.png`, 1440 × 1000 client px at 96 DPI.
- Small-window capture: `docs/design/launcher-minimum-risk.png`, 1092 × 653 client px inside a 1100 × 680 window.
- Empty and launcher-only states: `docs/design/launcher-empty.png`, `docs/design/launcher-self-update.png`.
- Local combined comparison: `docs/design/launcher-comparison.png`; focused row/control comparison: `docs/design/launcher-controls-comparison.png`.
- Comparison normalization removes the target's 54 px mock title bar and resizes its remaining client area to 1440 × 1000. Native OS title-bar chrome is excluded. This introduces minor vertical scale differences; no pixel-exact claim is made.
- Desktop comparison uses Smart Server selected, 4 checked mods, 4 available updates and 2 new mods. The target shows a hovered decline button; the desktop capture shows its resting state.

## Findings and fixes

1. Initial native capture used small list/body text and narrow checkbox hit targets. Increased row titles to 17 pt, summaries to 14 pt and reading text to 16 pt; replaced the small native checkbox glyph with licensed 24 px icons inside 36 px checkbox controls. Final captures show readable text and aligned row actions.
2. The original metadata flow supplied only change notes. Staging now supplies a short summary from existing feature copy, and all manifest paths preserve summary, full description and author separately from change notes. The UI does not invent descriptions for legacy manifests.
3. The selected-row background initially produced an amber edge on both sides. Final rendering retains only the left accent and a subtle selected surface.
4. Empty and launcher-only states initially invited selecting an unavailable mod. Final rendering shows the empty state and hides the inactive reading content.

No actionable P0/P1/P2 findings remain in the verified Mono UI.

## Fidelity surfaces

- Typography: Segoe UI, distinct title/body hierarchy, wrapped reading text, ellipsis only in list summaries and narrow titles, full text available in the reading pane or tooltips.
- Layout: 62% mod selection / 38% description; one scrollable list with both groups; fixed primary actions; independently scrolling long descriptions. Buttons remain within the client rectangle at 1100, 1280 and 1440 window widths.
- Colors: existing navy, amber, green and muted rose semantics preserved. Selected rows, versions and declined-mod actions remain distinct.
- Assets: licensed Lucide circle-slash, square and square-check icons; embedded PNGs preserve single-source compiler builds. No decorative imagery or tank artwork was introduced.
- Copy: actual repository metadata replaces invented purposes and versions. Risk flags and risk notes remain available. Installation tabs are absent because this executable only updates and launches.

## Behavior verification

`bash tests/run_launcher_tests.sh` passes 48 UI/update assertions and 2 Python tests with 6 metadata/staging subcases. Tests cover independent reading and checkbox selection, both bulk selection actions, cancelling and confirming a per-row decline, preserving other checked mods, persisted declined IDs, empty states, launcher-only updates, legacy manifests, the no-mods action, real local package updates with backups, and rejecting an invalid hash before replacing any installed file. Persistence and package tests use isolated temporary directories; no game or public release is launched or changed.

## Remaining verification

Windows rendering, Windows DPI scaling and real-client launch integration have not been run in this Linux environment. Native Windows form borders and scrollbars may differ from Mono. The installer and Windows signing/packaging require their existing game installation, payloads and certificate and are outside this launcher change. Minor native-control styling differences from the generated target remain P3 polish.
