# CLI component rendering: open-source options

## Decision

Use a layered renderer rather than converting every response into a component tree:

1. Keep the existing Markdown renderer for narrative, code blocks, and ordinary tables.
2. Expand the existing `beautiful-mermaid` adapter to its supported diagram families.
3. Add a *separate, opt-in* structured-output lane with `@json-render/ink` for model-produced cards, key/value views, status, progress, charts, and structured tables.

The structured lane must accept only a validated `ui_spec` and a whitelisted catalog. It must not treat arbitrary Markdown or tool output as executable component specifications.

## Shortlist

| Candidate | Fit | Recommendation |
| --- | --- | --- |
| [vercel-labs/json-render](https://github.com/vercel-labs/json-render/tree/main/packages/ink) (`@json-render/ink`) | Native Ink renderer. Its documented peer range includes Ink 6+ and React 19; standard components include Table, Card, KeyValue, Markdown, status/progress and bar-chart views, and it supports streamed specs. | **P0: small opt-in proof of concept.** Start with `Card`, `KeyValue`, `Table`, `StatusLine`, and `ProgressBar`; validate the catalog/spec before rendering. |
| [lukilabs/beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) (already installed) | Terminal-friendly ASCII/Unicode Mermaid renderer; documents flowchart, state, sequence, class, ER, and XY charts. | **P0: extend the existing adapter; no dependency needed.** |
| [maticzav/ink-table](https://github.com/maticzav/ink-table) | Simple standalone Ink table with custom header/cell hooks. Last listed release is from 2023. | **P2: do not make it foundational.** Only smoke-test it if Markdown tables and the structured renderer table prove insufficient. |
| [endernoke/ink-picture](https://github.com/endernoke/ink-picture) | A real JSX Ink `<Image />` component with terminal capability detection and Kitty/iTerm2/Sixel/text fallbacks. | **P3: optional capability-gated image renderer.** Preserve alt text/link fallback for SSH, CI, and terminal emulators without reliable graphics support. |

## Suggested streaming contract

```text
assistant event
  ├─ Markdown text / code / table  -> current Markdown renderer
  ├─ Mermaid fenced block          -> beautiful-mermaid
  └─ validated ui_spec             -> @json-render/ink catalog
```

This avoids fragile automatic detection: prose stays prose, while UI artifacts are explicitly declared and schema-validated.

## Explicit non-recommendations

- Do not replace Ink with a different terminal UI framework: the Shell already uses an Ink/React component tree.
- Do not introduce a second generic Mermaid-to-ASCII package: the installed renderer already covers the relevant diagram families.
- Do not use a DOM-oriented React chart/JSON viewer in the CLI.
- Do not insert ANSI-string image packages directly into the live Ink transcript; use an Ink component for this lane.
