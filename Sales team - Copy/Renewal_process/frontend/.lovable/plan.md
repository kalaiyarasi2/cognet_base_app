## Objective
Rearrange the two upload cards so they appear side by side horizontally, with **Census on the left** and **Invoice on the right**, instead of the current vertical stack.

## Changes
1. **`src/routes/index.tsx`**
   - Reorder the `<UploadCard>` components so Census renders before Invoice.
   - Wrap the two `<UploadCard>` components in a two-column responsive grid (e.g. `grid-cols-2` on `md` and up, single column on mobile) inside the left panel, replacing their current stacked layout.
   - Update `step` numbers if necessary (Census = 1, Invoice = 2).

## Out of scope
- No changes to PipelineProgress, ResultsPanel, Header, or processing logic.
- No backend or functional changes.