# Moses catalog and map design QA

final result: passed

## Comparison target and evidence

Source visual truth: `/Users/sptkl/.codex/generated_images/01a14aaa-6dae-7c62-988a-1ca8aeee7d75/exec-908a956a-210c-4cea-9ccd-0159fdc7ae11.png`.
Implementation: `http://127.0.0.1:8765/`, accepted landmarks version, Data → Map,
offline background, inspector open, no selected feature.

Source pixels: 1487 × 1058. Desktop CSS viewport and implementation pixels:
1488 × 1056, effective density 1. The source was resampled by less than 0.2%
to the implementation size for combined comparisons. No browser frame is included.

- First implementation: `.moses/catalog-map-first.jpg`.
- First combined comparison: `.moses/design-compare-first.jpg`.
- Final implementation: `.moses/catalog-map-final.jpg`.
- Final combined comparison: `.moses/design-compare-final.jpg`.
- Focused combined regions: `.moses/design-compare-header.jpg` and
  `.moses/design-compare-inspector.jpg` (source left, implementation right).
- Table evidence: `.moses/catalog-table-final.jpg`.
- Responsive evidence: `.moses/catalog-map-mobile-final.jpg`, 390 × 844 CSS/pixels.

Both full-view and focused combined images were opened and visually reviewed.

## Findings and comparison history

The first pass was blocked by fixable control clarity and responsive issues:

- [P2, fixed] Feature options showed ambiguous numeric labels such as `1. 0`.
  Options now use an actual key/name property, with an explicit source-row fallback.
- [P2, fixed] Fit was only an icon rather than the source's visible instruction.
  The control now includes “Fit features”.
- [P2, fixed] The omission message called unmapped rows “mapped features”.
  It now says rows omitted and lists geometry/property omission reasons.
- [P2, fixed] External basemap disclosure appeared only after selection.
  A compact disclosure is now visible before enabling OpenStreetMap.
- [P2, fixed] A long opaque resource ID competed with the dataset title.
  The exact catalog name now appears below a readable heading; the resource ID
  remains in Technical details.
- [P2, fixed] At 390px, the version selector extended to 450px because the inherited
  zero flex basis overrode its full-width intent. The narrow rule now uses
  `flex: 1 0 100%`. Final DOM widths are 390px client and 390px scroll width;
  the mobile screenshot shows the selector on its own row.

The final combined desktop comparison and post-fix mobile capture show no
remaining actionable P0/P1/P2 issue. Feature deselection also resets map styling.

## Required fidelity surfaces

- **Fonts/typography:** Locally served Inter 400/600/700 provides the source's
  sans-serif hierarchy. Heading, labels, table type and supporting copy are
  legible; the implementation uses slightly denser 14px body text than the
  generated source. This is acceptable for the operational catalog. Exact names
  remain available and the version control has its full label in the select.
- **Spacing/layout:** The 36px utility bar, 72px header, wide main region and
  390px right inspector preserve the source composition. Tabs, segmented view
  control, version selector and download action follow the same hierarchy.
  Keyboard feature selection and omission disclosure add a compact toolbar/footer.
  On mobile, the inspector follows the workspace and the table scrolls internally.
- **Colors/tokens:** Charcoal #1A202C/#2D3748, orange #D96B27, white surfaces and
  cool gray borders match the approved direction. Active states and focus outlines
  are visible. Moses is the sole product branding; no prohibited agency assets or
  planning references occur in the interface.
- **Image/asset quality:** Real vendored Feather icons and local Leaflet rendering
  are crisp. There are no fabricated raster map features or decorative logos.
  The mock's illustrated coastline and polygon distribution are intentionally
  replaced by real accepted point geometry. Offline means a genuinely blank map;
  online tiles require explicit selection and have attribution.
- **Copy/content:** Actual schema count is 30, not the mock's illustrative 24.
  The 100-row accepted snapshot contains 98 mappable points and two null geometries.
  Counts, source CRS, exact-version details and incomplete-source-coverage language
  replace illustrative claims. These are intentional correctness deviations.

## Interaction and accessibility evidence

Browser checks covered search, selected dataset, Table/Map switching, nonspatial
422 fallback to a usable table, feature selection and clearing, zoom/fit, optional
OSM imagery (visually verified after the referrer fix below, with attribution), Fields, History, one-version Compare
empty state, and inspector close/reopen. Controls have labels and visible focus;
the feature selector supports keyboard access without relying on map hit targets.
At 390px persistent controls remain within the viewport. Error/warning console
inspection returned no entries during the final desktop map checks.

Historical exact-version mapping, auth/Host/Origin and CRS/error limits are covered
by Python integration tests. The existing synthetic-browser baseline covered
historical download/comparison; the redesigned real catalog has only one accepted
version per dataset, so this pass does not claim a new visual multi-version study.

## Validation and limits

104 Python tests passed; one optional integration test skipped. Nine client-state
checks passed, including stale map responses after sign-out/version changes.
Wheel/sdist builds pass and the wheel contains all 28 public static routes plus
the map backend and dependency licenses. This is local developer verification,
not a usability study, full-city scale test, or hard process-memory isolation.

## Implementation checklist

- [x] Approved Moses-only theme and wide workspace/right inspector.
- [x] Real single-version map, feature properties and explicit omission counts.
- [x] Offline default and disclosed optional external basemap.
- [x] Fixed desktop clarity and mobile overflow findings; recaptured evidence.
- [x] Browser diagnostics, regression suites and packaged assets checked.

### Additional online-basemap iteration

A final visual inspection caught provider 403 warning images in otherwise
successfully loaded tile elements (`.moses/catalog-map-online.jpg`). This was a
P1 blocker that element load counts and empty browser logs did not reveal.
The page-wide `no-referrer` policy conflicted with the provider's published
requirement. Leaflet now applies `referrerPolicy: "origin"` only to opted-in
tile images. The global policy remains unchanged; no token or catalog identifiers
are sent. The disclosure includes the page origin and viewport tile requests.

After reload, DOM inspection confirmed the tile policy and a new screenshot
`.moses/catalog-map-online-final.jpg` (1280 × 720, default viewport, density 1)
was opened and visibly shows real road/coast imagery with orange features and
attribution. The online screenshot is an additional functional state; the
matched offline design comparison remains the fidelity baseline. Source policy:
https://operations.osmfoundation.org/policies/tiles/ .

No blocking visual follow-up remains. SQL, multiple layers and saved workspaces
are outside this implementation and remain roadmap work. Work is local/unmerged.

## Requested ribbon removal (2026-10-17)

The user approved the design and explicitly requested removal of the top black
ribbon before commit/push. Removed the utility-bar markup/styles and adjusted
workspace height offsets from 108/99px to 72/63px. This is an approved change to
the visual target, not an unintended fidelity mismatch.

Post-change evidence: `.moses/catalog-no-ribbon.jpg`, 855 × 765 default viewport.
Opened and visually reviewed: the white Moses header begins at y=0, no utility
bar remains, the workspace follows the 72px header, and document client/scroll
widths both equal 855px. Existing table and inspector remain usable. The narrow
layout keeps its dedicated version-selector row. No new functional test was
added for this markup/CSS-only adjustment.

final result: passed

Commit-boundary verification: the exact staged foundation snapshot passed 76
Python tests with one optional skip. The complete staged GUI snapshot passed
103 with one skip; the separate, pre-existing PLUTO case-study test was excluded
from this delivery, explaining the difference from the earlier 104-test working
tree run. All nine client-state tests still pass. Vendored Leaflet CRLF bytes
were preserved; whitespace validation uses `core.whitespace=cr-at-eol`.
