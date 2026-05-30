---
name: pencil-design
description: Design UIs in Pencil (.pen files) and generate production code from them. Use when working with .pen files, designing screens or components in Pencil, or generating code from Pencil designs. Triggers on tasks involving Pencil, .pen files, design-to-code workflows, or UI design with the Pencil MCP tools.
metadata:
  author: Nyasha Chiroro
  version: "1.0"
---

# Pencil Design Skill

Design production-quality UIs in Pencil and generate clean, maintainable code from them. This skill enforces best practices for design system reuse, variable usage, layout correctness, visual verification, and design-to-code workflows.

## When to Use This Skill

- Designing screens, pages, or components in a `.pen` file
- Generating code (React, Next.js, Vue, Svelte, HTML/CSS) from Pencil designs
- Building or extending a design system in Pencil
- Syncing design tokens between Pencil and code (Tailwind v4 `@theme`, shadcn/ui tokens)
- Importing existing code into Pencil designs
- Working with any Pencil MCP tools (`pencil_batch_design`, `pencil_batch_get`, etc.)

## Critical Rules

These rules address the most common agent mistakes. Violating them produces designs that are inconsistent, hard to maintain, and generate poor code.

### Rule 1: Always Reuse Design System Components

**NEVER recreate a component from scratch when one already exists in the design file.**

Before inserting any element, you MUST:
1. Call `pencil_batch_get` with `patterns: [{ reusable: true }]` to list all available reusable components
2. Search the results for a component that matches what you need (button, card, input, nav, etc.)
3. If a match exists, insert it as a `ref` instance using `I(parent, { type: "ref", ref: "<componentId>" })`
4. Customize the instance by updating its descendants with `U(instanceId + "/childId", { ... })`
5. Only create a new component from scratch if no suitable reusable component exists

See [references/design-system-components.md](references/design-system-components.md) for detailed workflow.

### Rule 2: Always Use Variables Instead of Hardcoded Values

**NEVER hardcode colors, border radius, spacing, or typography values when variables exist.**

Before applying any style value, you MUST:
1. Call `pencil_get_variables` to read all defined design tokens
2. Map your intended values to existing variables (e.g., use `primary` not `#3b82f6`, use `radius-md` not `6`)
3. Apply values using variable references, not raw values
4. When generating code, use Tailwind v4 semantic utility classes (e.g., `bg-primary`, `text-foreground`, `rounded-md`). NEVER use arbitrary value syntax (`bg-[#3b82f6]`, `text-[var(--primary)]`, `rounded-[6px]`)

See [references/variables-and-tokens.md](references/variables-and-tokens.md) for detailed workflow.

### Rule 3: Prevent Text and Content Overflow

**NEVER allow text or child elements to overflow their parent or the artboard.**

For every text element and container:
1. Set appropriate text wrapping and truncation
2. Constrain widths to parent bounds, especially on mobile screens (typically 375px wide)
3. Use `"fill_container"` for width on text elements inside auto-layout frames
4. After inserting content, call `pencil_snapshot_layout` with `problemsOnly: true` to detect clipping/overflow
5. Fix any reported issues before proceeding

See [references/layout-and-text-overflow.md](references/layout-and-text-overflow.md) for detailed workflow.

### Rule 4: Keep Artboards Intentionally Sized and Aligned on the Canvas

**NEVER leave top-level artboards with accidental size drift or messy canvas placement.**

When a `.pen` file contains multiple screens, pages, modal states, or route variants, you MUST:
1. Inspect the current top-level artboards first with `pencil_get_editor_state`, `pencil_batch_get(..., readDepth: 1)`, or `pencil_snapshot_layout(maxDepth: 0)`
2. Identify the baseline size for each screen family before editing:
   - same desktop page family -> default to the same width
   - same state family (for example right-collapsed / right-expanded) -> default to the same outer canvas size
   - modal artboards may use different heights, but should still share a clear width baseline when they represent the same device class
3. Only keep a different width or height when the difference is intentional and semantically justified, not because of accidental drift
4. Place top-level artboards in a clean grid with consistent gaps and aligned row tops; do not leave one frame slightly offset or floating between rows
5. If one outlier screen genuinely needs a different size, give it its own row or otherwise preserve visual order instead of breaking the grid
6. After moving or resizing artboards, re-run `pencil_snapshot_layout(maxDepth: 0)` to confirm positions are orderly and screens do not overlap

Typical default:
- desktop artboards in the same product area should share one width baseline unless a wider home/landing screen is deliberately separated
- different heights are acceptable for page vs modal vs long-content states, but they still need to look intentionally arranged on the canvas

### Rule 5: Use Annotation Layers and State Artboards Intentionally

**NEVER hide important page meaning or interaction changes only in chat context. Put them into the `.pen` file in a clean way.**

When a design needs explanation, navigation mapping, or click-result clarification, you MUST:
1. Use dedicated `note`, `context`, or separate spec frames to explain what a screen represents
2. Keep annotation content outside the user-visible UI area, or place it on a dedicated `Spec / Notes` artboard
3. Represent interactive changes such as collapsed / expanded / modal open / empty / loaded as separate artboards or clearly separated state frames
4. Prefer paired state naming such as `Default`, `Expanded`, `Collapsed`, `Open`, `Empty`, `Loaded`
5. Do not rely on a single static screen plus a sentence like “clicking here expands”; show the resulting state explicitly
6. For public landing pages or document-like long pages, provide both a viewport artboard and a full-scroll artboard when the page meaning depends on scroll depth

Typical default:
- app-route screens -> one shared viewport baseline
- modal states -> same outer viewport, different inner modal sizes
- long public pages -> `Viewport` + `Full Scroll`
- interaction-heavy areas -> state pairs or state groups instead of one overloaded artboard

### Rule 6: Visually Verify Every Section

**NEVER skip visual verification after building a section or screen.**

After completing each logical section (header, hero, sidebar, form, card grid, etc.):
1. Call `pencil_get_screenshot` on the section or full screen node
2. Analyze the screenshot for: alignment issues, spacing inconsistencies, text overflow, visual glitches, missing content
3. Call `pencil_snapshot_layout` with `problemsOnly: true` to catch clipping and overlap
4. Fix any issues found before moving to the next section
5. Take a final full-screen screenshot when the entire design is complete

See [references/visual-verification.md](references/visual-verification.md) for detailed workflow.

### Rule 7: Reuse Existing Assets (Logos, Icons, Images)

**NEVER generate a new logo or duplicate asset when one already exists in the document.**

Before generating any image or logo:
1. Call `pencil_batch_get` and search for existing image/logo nodes by name pattern (e.g., `patterns: [{ name: "logo|brand|icon" }]`)
2. If a matching asset exists elsewhere in the document (another artboard/screen), copy it using the `C()` (Copy) operation
3. Only use the `G()` (Generate) operation for genuinely new images that don't exist anywhere in the document
4. For logos specifically: always copy from an existing instance, never regenerate

See [references/asset-reuse.md](references/asset-reuse.md) for detailed workflow.

### Rule 8: Always Load the `frontend-design` Skill

**NEVER design in Pencil or generate code from Pencil without first loading the `frontend-design` skill.**

The `frontend-design` skill provides the aesthetic direction and design quality standards that prevent generic, cookie-cutter UI. You MUST:
1. Load the `frontend-design` skill at the start of any Pencil design or code generation task
2. Follow its design thinking process: understand purpose, commit to a bold aesthetic direction, consider differentiation
3. Apply its guidelines on typography, color, motion, spatial composition, and visual details — both when designing in Pencil and when generating code from Pencil designs
4. Never produce generic AI aesthetics (overused fonts, cliched color schemes, predictable layouts)

This applies to both directions:
- **Pencil design tasks**: Use the skill's aesthetic guidelines to inform layout, typography, color, and composition choices in the .pen file
- **Code generation from Pencil**: Use the skill's guidelines to ensure the generated code includes distinctive typography, intentional color themes, motion/animations, and polished visual details — not just a mechanical translation of the design tree

## Design Workflow

### Starting a New Design

```
0. Load `frontend-design` skill   -> Get aesthetic direction and design quality standards
1. pencil_get_editor_state        -> Understand file state, get schema
2. pencil_snapshot_layout         -> Check top-level artboard positions (`maxDepth: 0`)
3. Decide screen families         -> Route / Modal / Interaction / Spec / Long Scroll
4. pencil_batch_get (reusable)    -> Discover design system components
5. pencil_get_variables           -> Read design tokens
6. pencil_get_guidelines          -> Get relevant design rules
7. pencil_get_style_guide_tags    -> (optional) Get style inspiration
8. pencil_get_style_guide         -> (optional) Apply style direction
9. pencil_find_empty_space_on_canvas -> Find space for new screen
10. pencil_batch_design           -> Build the design (section by section)
11. pencil_get_screenshot         -> Verify each section visually
12. pencil_snapshot_layout        -> Check for layout problems
```

### Building Section by Section

For each section of a screen (header, content area, footer, sidebar, etc.):

1. **Plan** - Identify which design system components to reuse
2. **Build** - Insert components as `ref` instances, apply variables for styles
3. **Verify** - Screenshot the section + check layout for problems
4. **Fix** - Address any overflow, alignment, or spacing issues
5. **Proceed** - Move to the next section only after verification passes

### Design-to-Code Workflow

See [references/design-to-code-workflow.md](references/design-to-code-workflow.md) for the complete workflow.
See [references/tailwind-shadcn-mapping.md](references/tailwind-shadcn-mapping.md) for the full Pencil-to-Tailwind mapping table.
See [references/responsive-breakpoints.md](references/responsive-breakpoints.md) for multi-artboard responsive code generation.

Summary:
1. Load the `frontend-design` skill for aesthetic direction
2. Call `pencil_get_guidelines` with topic `"code"` and `"tailwind"`
3. Call `pencil_get_variables` to map design tokens to Tailwind `@theme` declarations
4. Read the design tree with `pencil_batch_get`
5. Map reusable Pencil components to shadcn/ui components (Button, Card, Input, etc.)
6. Generate code using semantic Tailwind classes (`bg-primary`, `rounded-md`), never arbitrary values
7. Apply `frontend-design` guidelines: distinctive typography, intentional color, motion, spatial composition
8. Use CVA for custom component variants, `cn()` for class merging, Lucide for icons

## MCP Tool Quick Reference

| Tool | When to Use |
|------|-------------|
| `pencil_get_editor_state` | First call - understand file state and get .pen schema |
| `pencil_batch_get` | Read nodes, search for components (`reusable: true`), inspect structure |
| `pencil_batch_design` | Insert, copy, update, replace, move, delete elements; generate images |
| `pencil_get_variables` | Read design tokens (colors, radius, spacing, fonts) |
| `pencil_set_variables` | Create or update design tokens |
| `pencil_get_screenshot` | Visual verification of any node |
| `pencil_snapshot_layout` | Detect clipping, overflow, overlapping elements |
| `pencil_get_guidelines` | Get design rules for: `code`, `table`, `tailwind`, `landing-page`, `design-system` |
| `pencil_find_empty_space_on_canvas` | Find space for new screens/frames |
| `pencil_get_style_guide_tags` | Browse available style directions |
| `pencil_get_style_guide` | Get specific style inspiration |
| `pencil_search_all_unique_properties` | Audit property values across the document |
| `pencil_replace_all_matching_properties` | Bulk update properties (e.g., swap colors) |
| `pencil_open_document` | Open a .pen file or create a new document |

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---------|-----------------|
| Creating a button from scratch | Search for existing button component, insert as `ref` |
| Using `fill: "#3b82f6"` | Use the variable: reference `primary` or the corresponding variable |
| Using `cornerRadius: 8` | Use the variable: reference `radius-md` or the corresponding variable |
| Generating `bg-[#3b82f6]` in code | Use semantic Tailwind class: `bg-primary` |
| Generating `text-[var(--primary)]` in code | Use semantic Tailwind class: `text-primary` |
| Generating `rounded-[6px]` in code | Use semantic Tailwind class: `rounded-md` |
| Using `var(--primary)` in className | Use semantic Tailwind class: `bg-primary` or `text-primary` |
| Not checking for overflow | Call `pencil_snapshot_layout(problemsOnly: true)` after every section |
| Letting top-level artboards drift to random sizes/positions | Inspect `maxDepth: 0`, unify same-family baselines, and align artboards into clean rows with consistent gaps |
| Mixing public home, workspace home, modal states, and click-result states into one artboard | Split them into route artboards, modal artboards, interaction state artboards, and spec notes |
| Writing explanation text directly into the visible UI | Put it in `note` / `context` nodes outside the screen or on a dedicated `Spec / Notes` artboard |
| Showing a long-scroll landing page only as a short viewport | Provide both `Viewport` and `Full Scroll` artboards |
| Skipping screenshots | Call `pencil_get_screenshot` after every section |
| Generating a new logo | Copy existing logo from another artboard with `C()` |
| Building entire screen, then checking | Build and verify section by section |
| Ignoring `pencil_get_guidelines` | Always call it for the relevant topic before starting |
| Using `tailwind.config.ts` | Use CSS `@theme` block (Tailwind v4) |
| Using Material Icons in code | Map to Lucide icons (`<Search />`, `<ArrowRight />`, etc.) |
| Skipping `frontend-design` skill | Always load it before designing in Pencil or generating code |
| Generic AI aesthetics (Inter font, purple gradients) | Follow `frontend-design` guidelines for distinctive, intentional design |

## Resources

- [Pencil Docs](https://docs.pencil.dev)
- [Pencil Prompt Gallery](https://www.pencil.dev/prompts)
- [Design as Code](https://docs.pencil.dev/core-concepts/design-as-code)
- [Variables](https://docs.pencil.dev/core-concepts/variables)
- [Components](https://docs.pencil.dev/core-concepts/components)
- [Design to Code](https://docs.pencil.dev/design-and-code/design-to-code)
- [Styles and UI Kits](https://docs.pencil.dev/design-and-code/styles-and-ui-kits)
