# Modal design QA

final result: passed

Source visual: `/Users/tttol/.codex/generated_images/01a195ca-b522-77d1-bb1c-bee6908a85a8/exec-28a70069-697b-4d1c-aadf-897ee208879b.png` (first displayed ideation result).

State: daily necessities modal, September/October 2026, exact synthetic rows from the selected mockup; no private CSVs used for visual comparison.

Viewport: 1280 × 960 CSS px, implementation capture 1280 × 960 pixels. Source 1448 × 1086 pixels normalized uniformly to 1280 × 960. No browser chrome; density 1× for comparison.

## Pass 1

Combined source/implementation evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-comparison-1.png`.

- [P2] Typography and hierarchy were too small. Source uses larger month labels, merchant names, yen amounts, and totals; the initial implementation made the ledger feel sparse despite retaining the correct rows. Increase heading 32→40px, month 36→44px, row text 18→24px, amount 19→25px, total 28→34px.
- [P2] Date/name alignment and vertical rhythm were too compressed. Widen date tracks 55→80px, adjust row padding and heading spacing to restore the mockup's reading rhythm.

Both corrections were applied and rechecked in pass 2.

## Pass 2

Implementation: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-pass-2.png`.

Combined full-view evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-comparison-2.png`.

Focused first-three-row comparison: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-focused-comparison.png`. Source crop (115,285)–(1165,495), implementation crop (118,265)–(1168,475), same 1050×210 region size. This verifies typography, amount alignment, the blank supermarket occurrence, and the following matched row.

The pass-1 typography and rhythm findings are resolved. There are no remaining actionable P0/P1/P2 issues.

### Required fidelity surfaces

- Fonts/typography: system Japanese sans, navy headings, muted dates/year, tabular right-aligned amounts; updated scale follows the chosen target.
- Spacing/layout: one white modal; no merchant boxes or repeated merchant headers; two continuous columns, center hairline, shared row heights, header/footer rules. The extra supermarket entry leaves a blank left cell; different unmatched descriptions share a plain row as requested.
- Colors/tokens: white modal, navy text, cool gray secondary text, thin neutral separators, softly dimmed backdrop. No colored summary card remains in the modal.
- Asset fidelity: the only new icon is the official Bootstrap Icons close SVG, served locally with its license. No raster artwork or illustration is required by the target.
- Copy/content: all 13 sample transactions and exact totals (7,270 / 7,450 yen) match the selected image. Source date strings display compactly, with full dates retained in semantic labels. Optional subcategory/memo text remains available for real rows without creating cards.

### Responsive and interaction checks

Mobile evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-mobile.png`, 390×844 CSS/pixel capture. Both month columns remain visible, all row cell tops align, no document or modal horizontal overflow. Names move to a second line at narrow widths, an intentional responsive adaptation absent from the desktop mock.

Verified chart activation, keyboard Space activation, Esc dismissal, focus return, and scroll unlocking. Browser console error log was empty. Native dialog close/backdrop behavior is retained from the existing interaction code.

### Acceptable differences and follow-up polish

- [P3] Browser/system font rasterization and the close icon's optical weight differ slightly from the generated reference.
- [P3] The real modal centers naturally in its viewport; the generated frame's vertical placement is slightly asymmetric. This does not affect the ledger layout.
- The existing app remains visible behind the backdrop; it is not replaced with an image of the mock background.
- A small secondary footer hint explains full-name expansion. Esc dismissal remains supported.

## Real-data check and pass 3

- [P2] Long product descriptions wrapped into many lines and reduced the comparison list to only a couple of visible rows. Keep names on one line by default with ellipsis and a native disclosure to read the full description on demand. Preserve the complete text in the DOM and tooltip. Recheck the sample and real-data views before final handoff.
- Replace the secondary footer hint with the description-expansion affordance; Esc dismissal remains functional.

Pass 3 resolved the long-name finding. Final combined evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-final-comparison.png`, with focused row evidence in `ledger-final-focused.png` in the same directory. Final sample capture `ledger-final-sample.png` is 1280×960 and uses exactly the selected reference's synthetic transactions. The native disclosure introduces no visual change for short names; long real names can be expanded with click or Enter and collapsed again. All paired cells retain their common row height during expansion.

Real-data evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-real-final.png`. All 32 daily-necessity transactions remain present; long names are compact initially, and there is no horizontal overflow. Verified one long product description expands and collapses without losing content or breaking row alignment.

Final mobile evidence: `/Users/tttol/Documents/Codex/2026-11-01/re-design-my-blog-ui/design-qa/ledger-mobile-final.png` (390×844). Both month columns and the extra supermarket blank cell remain aligned; document width is 390px, with no horizontal overflow. Desktop and mobile viewport overrides were reset after verification.

All real transactions in every category were reconciled as multisets against the parsed source data; none were dropped or duplicated. Category totals and both PNG exports remain unchanged. The final 69-test suite passed. There are no remaining actionable P0/P1/P2 findings.

## Implementation checklist

- [x] Preserve individual transactions and align repeated names with blank opposite cells.
- [x] Pair otherwise unmatched rows without claiming that their descriptions match.
- [x] Match the selected minimal white presentation and check the combined visual evidence.
- [x] Verify responsive layout and keyboard interaction.
- [x] Run the 69 behavioral tests; no dependency changes.
