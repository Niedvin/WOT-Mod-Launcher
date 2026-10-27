# Research button design QA

Date: 2026-10-27
Scope: research carousel action component, version 1.2.0.

## Native visual target

The target is the existing World of Tanks vehicle module action: `gui/maps/icons/vehicle_hub/modules/small/default.png` (56 x 56) and `hover.png` (74 x 74). These original client assets are read from its package archives at build time. The glyph is a filled ivory research branch with a dark edge and muted khaki endpoint, generated from the native references and fitted to a transparent 64 x 64 PNG. No tank silhouette, custom SVG, fake CSS frame or hand-drawn shadow is used.

The button uses 24 rem, glyph 20 rem and left inset 4 rem. The hover artwork preserves the original 74:56 size ratio. Native rem units follow the game interface scale; the action remains centered on the left edge of actual vehicle cards.

## Comparison and fixes

The Codex in-app browser comparison displayed the native source control, research default, research hover and 200% interface scale side by side on the supplied game-card crop. The first pass identified 2 preview defects: narrow-window overflow and an unscaled 200% inset. Both were corrected. The second screenshot showed all states within the viewport and the correct scaled inset. Source backplates, warm icon color, border weight, glyph legibility and spacing were compared directly. No unresolved P0, P1 or P2 component defect remains.

The preview is at `http://127.0.0.1:8765/` during this session. Production uses the native React vehicle-card component rather than the preview page. The button is injected after the real-vehicle guard and sends the vehicle descriptor directly, without delayed selection or polling. Empty, purchase and recovery tiles do not receive it.

## Evidence and limits

JavaScript syntax, Python 2.7 compilation, package integrity and embedded resource hashes passed. Direct module navigation and the empty-tile guard were already observed in the native client before the artwork replacement. This visual pass validates the final component against native assets; the final artwork has not been captured from a running game. Spectator post-death behavior is outside this visual component pass.

final result: passed
