# Frontend / UI Design Criteria

> Evaluator type: AI agent | Scoring: 1-10 per dimension
> Weighting: Design Quality and Originality are weighted **2x** relative to Craft and Functionality.

**Evaluator instructions:** Be skeptical — do not default to praising the work. Every score must cite specific evidence from the UI. If you are unsure whether something meets a threshold, score it lower and explain why.

## Dimensions

### 1. Design Quality (Weight: 2x)

Does the design feel like a coherent whole? Colors, typography, layout, and imagery should combine to establish a distinct mood and visual identity — not just "clean" or "modern" but something with a clear point of view.

| Score | Description |
|-------|-------------|
| 9-10  | Striking, cohesive visual identity. Every element reinforces a clear design direction. Could pass as a professionally designed product. |
| 7-8   | Strong visual identity with minor inconsistencies. The overall direction is clear and intentional. |
| 5-6   | Competent but generic. Looks like a well-executed template without a distinct personality. |
| 3-4   | Inconsistent — some elements feel considered, others feel like defaults. No unified direction. |
| 1-2   | Visually incoherent. Clashing styles, no discernible design intent. |

### 2. Originality (Weight: 2x)

Evidence of custom decisions rather than template layouts or library defaults. Penalize telltale signs of AI generation and "AI slop": purple gradients over white cards, generic hero sections with stock copy, cookie-cutter card grids, glassmorphism/frosted-glass defaults, overly symmetrical layouts with no visual tension, gradient-heavy CTAs, and placeholder-quality microcopy ("Welcome to [App]", "Get started today").

| Score | Description |
|-------|-------------|
| 9-10  | Genuinely distinctive. Layout, color choices, and interactions feel custom and surprising. |
| 7-8   | Mostly original with a few conventional fallbacks. Clear creative intent throughout. |
| 5-6   | Some custom touches but largely follows common patterns. Would blend in among similar apps. |
| 3-4   | Template-driven. Standard card grid, default component library styling, predictable layout. |
| 1-2   | Pure defaults. Indistinguishable from a scaffolded starter project. |

### 3. Craft (Weight: 1x)

Technical execution of visual design: typography hierarchy, spacing consistency, color harmony, contrast ratios, alignment, responsive behavior.

> **Note:** This is a competence check, not a creativity check. Most implementations score 5+ here by default. A low score indicates serious technical problems, not a lack of ambition.

| Score | Description |
|-------|-------------|
| 9-10  | Pixel-perfect execution. Flawless type scale, consistent spacing system, perfect alignment. |
| 7-8   | Minor imperfections that don't disrupt the experience. Solid attention to detail. |
| 5-6   | Adequate. No glaring issues but inconsistencies are noticeable on close inspection. |
| 3-4   | Sloppy spacing, inconsistent type sizes, misaligned elements. Feels unfinished. |
| 1-2   | No attention to detail. Broken layouts, overlapping elements, unreadable text. |

### 4. Functionality (Weight: 1x)

Usability independent of aesthetics. Can a user understand the interface, locate primary actions, and complete tasks intuitively?

| Score | Description |
|-------|-------------|
| 9-10  | Instantly intuitive. Clear information hierarchy, obvious CTAs, zero confusion. |
| 7-8   | Easy to use with minimal friction. One or two areas could be clearer. |
| 5-6   | Usable but requires some guessing. Important actions aren't immediately obvious. |
| 3-4   | Confusing navigation or layout. Users would struggle to complete basic tasks. |
| 1-2   | Unusable. Critical actions hidden, misleading affordances, broken interaction flows. |

## Scoring Formula

```
Weighted Score = ((Design Quality * 2) + (Originality * 2) + Craft + Functionality) / 6
```

## Hard Threshold

Any single dimension scoring **3 or below** triggers a fail regardless of the weighted score. The evaluator should provide specific feedback on what to fix.
