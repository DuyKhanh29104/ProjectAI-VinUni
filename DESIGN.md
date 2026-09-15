---
name: Label Guardian
description: Data-centric perception QA design system
colors:
  primary: "#56c9bf"
  primary-strong: "#2b7973"
  primary-hover: "#348b84"
  primary-soft: "rgba(86, 201, 191, 0.11)"
  primary-line: "rgba(86, 201, 191, 0.28)"
  neutral-bg: "#090d10"
  neutral-bg-subtle: "#0d1418"
  surface-1: "#121b20"
  surface-2: "#172329"
  surface-3: "#1c2b31"
  surface-hover: "#203138"
  line: "rgba(205, 235, 235, 0.1)"
  line-strong: "rgba(205, 235, 235, 0.18)"
  text-strong: "#edf5f5"
  text: "#c4d1d3"
  text-muted: "#8fa3a8"
  text-faint: "#62777d"
  success: "#63b78f"
  success-soft: "rgba(99, 183, 143, 0.11)"
  warning: "#d2a35d"
  warning-soft: "rgba(210, 163, 93, 0.11)"
  danger: "#d9707a"
  danger-soft: "rgba(217, 112, 122, 0.11)"
  info: "#73a8ce"
  info-soft: "rgba(115, 168, 206, 0.11)"
typography:
  display:
    fontFamily: '"Aptos", "Segoe UI Variable", -apple-system, sans-serif'
    fontSize: "2rem"
    fontWeight: 660
    lineHeight: 1.12
  body:
    fontFamily: '"Aptos", "Segoe UI Variable", -apple-system, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.55
  mono:
    fontFamily: '"SFMono-Regular", "Cascadia Code", Consolas, monospace'
    fontSize: "0.6875rem"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-bg}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.text-strong}"
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "34px"
  card:
    backgroundColor: "{colors.surface-1}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: Label Guardian

## Overview

**Creative North Star: "The Perception Sanctuary"**

Label Guardian is a quiet, dark tech workspace optimized for perception data auditing (3D bounding boxes, YOLO annotations, nuScenes/KITTI frames). The design recedes into the background so that label data and bounding box annotations remain the focus of the reviewer's cognitive load.

### Key Characteristics:
- **Low Ambient Light**: High-contrast, dark-gray surfaces and pure charcoal canvas.
- **Single Source of Color**: Teal (#56c9bf) is the only brand color, reserved for positive user actions, brand identity, and focus.
- **Tabular Data Focus**: Layouts are highly structured grids using monospace type for numbers and coordinates.
- **Hardware-Accelerated Motion**: Transitions use `transform` and `opacity` to eliminate layout thrashing.

## Colors

The color system uses a restraint-first color strategy to prevent screen elements from competing with multi-color 3D annotation frames.

### Primary
- **Brand Action Teal** (#56c9bf): Used for links, primary buttons, logo indicators, active sidebar navigation highlights, and text focus.

### Neutral
- **Canvas BG** (#090d10): Background of the page layout.
- **Surface 1** (#121b20): Secondary panel backgrounds (cards, layout blocks).
- **Surface 2** (#172329): Interactive controls (buttons, inputs, select dropdowns).
- **Surface 3** (#1c2b31): Deep active states, highlights, scrollbar tracks.
- **Text Strong** (#edf5f5): Primary text, headings, strong tags.
- **Text Body** (#c4d1d3): Standard body text.
- **Text Muted** (#8fa3a8): Meta info, details, supporting text.
- **Text Faint** (#62777d): Placeholders, disabled states, labels.

### Named Rules
**The Rarity of Brand Color Rule.** The Teal accent is never decorative. It should cover less than 5% of any screen, indicating focus, active path, or major action.

## Typography

**Display Font:** Aptos (with fallback Segoe UI, -apple-system, sans-serif)
**Body Font:** Aptos (with fallback Segoe UI, -apple-system, sans-serif)
**Label/Mono Font:** SFMono-Regular (with fallback Cascadia Code, Consolas, monospace)

### Hierarchy
- **Display** (660, 2rem (32px), 1.12): Page headings, main viewport title.
- **Headline** (660, 1.25rem (20px), 1.2): Section headings, card titles.
- **Title** (680, 0.875rem (14px), 1.3): Field labels, action buttons, table headers.
- **Body** (400, 0.75rem (12px), 1.55): Body descriptions, explanations.
- **Label** (400, 0.6875rem (11px), 1.2): Point tags, statistics, small indicators.

### Named Rules
**The Tabular Number Rule.** All dataset counters, timestamps, risk values, and bounding box coordinates use monospace text (`var(--font-mono)`) with tabular-nums enabled.

## Layout

Layouts are strictly structured using a grid-aligned scale of 4px increments (4px, 8px, 12px, 16px, 20px, 24px, 32px, 40px).

## Elevation & Depth

No ambient drop shadows. Depth is conveyed strictly by tonal layering of surfaces (Canvas #090d10 → Surface 1 #121b20 → Surface 2 #172329).

### Named Rules
**The Flat Canvas Rule.** Shadows are restricted to floating popovers (`box-shadow: 0 16px 44px rgba(0,0,0,0.32)`). Workspace cards and dashboard panels have zero shadows and are demarcated by thin borders (`border: 1px solid var(--color-line)`).

## Shapes

Shapes are geometric and subtle.
- **Cards and Panels**: Rounded corners at `8px` (`var(--radius-lg)`).
- **Controls & Buttons**: Rounded corners at `6px` (`var(--radius-md)`).
- **Badges**: Rounded corners at `4px` (`var(--radius-sm)`).

## Components

### Buttons
- **Shape**: Rounded md (6px).
- **Primary**: Background Teal (`var(--color-brand)`), Text Charcoal (`var(--color-canvas)`), height (34px).
- **Secondary**: Border `rgba(205,235,235,0.18)` (`var(--color-line-strong)`), Background `var(--color-surface-2)`, Text `var(--color-text)`.

### Cards
- **Corner Style**: Rounded lg (8px).
- **Background**: `var(--color-surface-1)`.
- **Border**: Thin line `var(--color-line)`.

### Inputs / Fields
- **Style**: Background `var(--color-surface-2)`, border `var(--color-line-strong)`.
- **Focus**: Outline Teal border (`var(--color-brand)`) with focus shadow (`var(--shadow-focus)`).

### Navigation (Sidebar)
- **Style**: Fixed width (68px) that expands to (220px) on hover.
- **Transitions**: The width change expands instantly; content labels fade in via `opacity` transition (no `width` or `max-width` layout transitions).
- **Active State**: Active items have background Teal Soft (`var(--color-brand-soft)`) and border Teal Line (`var(--color-brand-line)`).

## Do's and Don'ts

### Do:
- **Do** align all layouts to the 4px grid increments (`var(--space-1)` to `var(--space-10)`).
- **Do** use monospace typography for frame indices, sequence numbers, and coordinate readings.
- **Do** preserve the dark Canvas color (#090d10) for page bodies to reduce visual fatigue.

### Don't:
- **Don't** use decorative hairline grid backgrounds on text-rich pages or layouts.
- **Don't** use thick colored accent stripes (side-tabs) on card borders.
- **Don't** animate width, padding, or margin properties during state transitions.
