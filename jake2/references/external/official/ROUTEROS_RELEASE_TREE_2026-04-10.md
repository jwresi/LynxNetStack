# RouterOS Release Tree Notes

- Source URLs:
  - https://mikrotik.com/download/changelogs/current-release-tree
  - https://mikrotik.com/download/changelogs/changelogs.html
- Source type: official MikroTik release/changelog pages
- Intake date: 2026-04-10
- Use for: upgrade planning, release-channel context, current-vs-old stable tree reasoning

## High-signal points for Jake

1. MikroTik publishes release history by channel:
- stable
- long-term
- testing

2. The release tree is moving operational truth.
- this should stay in RAG/reference, not be fine-tuned into weights
- Jake should use it to frame upgrade risk and version recency, not memorize one "current" version forever

3. Operator implication:
- when Jake reviews an upgrade target, he should prefer current vendor release context over stale internal memory
- release-tree context belongs beside live device state and current hardware/platform risk checks

## Jake operator read

Use this to support:

- `review_live_upgrade_risk`
- `generate_upgrade_preflight_plan`
- `render_upgrade_change_explanation`

Do not use this as a substitute for:

- live package state from the device
- current platform-specific risk checks
- your own maintenance-window policy

## Why this belongs in RAG

Release trees and changelogs are changing reference material. They should be retrieved fresh, not trained into the model.
