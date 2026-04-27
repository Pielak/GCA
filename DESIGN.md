# GCA — Design System Technical

> **Gestão de Codificação Assistida**: Meta-plataforma de orquestração, governança e geração assistida de software com rastreabilidade total.

---

## 1. Visual Theme & Atmosphere

**Design Philosophy**: Terminal-futuristic × Governance Authority

GCA is positioned as **technical infrastructure for code orchestration**. The visual identity communicates:
- **Precision**: Every pixel intentional, zero decoration
- **Terminal-native**: Monospace hierarchy, block-based layout (inspired by VoltAgent, Ollama, Warp)
- **Governance weight**: Dark, authoritative surfaces with emerald accent for code authority
- **Future-ready**: Void-black canvas with cinematic depth (inspired by xAI, SpaceX, Shopify dark)

**Mood**: 
- Professional yet approachable (not sterile)
- Technical yet readable (not overwhelming)
- Dark and dramatic (void-black) yet with emergent emerald glow (code coming to life)
- Minimal motion (intentional, not decorative)

---

## 2. Color Palette & Roles

### Primary Palette

| Name | Hex | RGB | Role | Usage |
|------|-----|-----|------|-------|
| **Void** | #0a0a0a | 10,10,10 | Base canvas | Page background, dark surfaces |
| **Dark Gray** | #1a1a1a | 26,26,26 | Elevated surface | Cards, panels, section background |
| **Medium Gray** | #2d2d2d | 45,45,45 | Tertiary surface | Borders, dividers, subtle elevation |
| **Light Gray** | #e5e5e5 | 229,229,229 | Text primary | Body text, readable content |
| **Muted Gray** | #9ca3af | 156,163,175 | Text secondary | Labels, hints, disabled states |

### Accent Colors

| Name | Hex | RGB | Role | Usage |
|------|-----|-----|------|-------|
| **Emerald** | #10b981 | 16,185,129 | Primary accent | Active states, code elements, success, CTAs |
| **Emerald Light** | #6ee7b7 | 110,231,183 | Accent hover | Hover states, highlights, glow effects |
| **Violet** | #8b5cf6 | 139,92,246 | Secondary accent | Governance, processes, personas, info |
| **Violet Light** | #d8b4fe | 216,180,254 | Accent hover | Hover states, soft emphasis |
| **Orange** | #f97316 | 249,115,22 | Alert accent | Warnings, degraded status, requires action |
| **Red** | #ef4444 | 239,68,68 | Destructive | Errors, delete actions, critical states |
| **Cyan** | #06b6d4 | 6,182,212 | Tertiary accent | Infrastructure, DevOps, integrations |

### Semantic Colors

| Semantic | Hex | Usage |
|----------|-----|-------|
| `success` | #10b981 | Approvals, completed phases, passing tests |
| `warning` | #f97316 | Pending approval, degraded service, attention needed |
| `error` | #ef4444 | Failed validation, broken pipeline, critical issue |
| `info` | #8b5cf6 | Information, status updates, governance notes |
| `pending` | #06b6d4 | In-progress, awaiting action, provisioning |

### Color Contrast
- All text on background must meet WCAG AA (4.5:1 for body, 3:1 for large text)
- Void + Light Gray: 16.5:1 ✓
- Void + Muted Gray: 8.2:1 ✓
- Dark Gray + Light Gray: 12.3:1 ✓

---

## 3. Typography Rules

### Font Stack (Hierarchy)

```css
/* Display / Headlines (h1-h2) */
font-family: 'JetBrains Mono', 'SF Mono', monospace;
font-size: 2rem - 3rem;
font-weight: 600;
letter-spacing: -0.02em;
line-height: 1.2;

/* Heading level 3+ (h3-h6) */
font-family: 'Inter', -apple-system, system-ui, sans-serif;
font-size: 1rem - 1.5rem;
font-weight: 600;
letter-spacing: 0;
line-height: 1.4;

/* Body text */
font-family: 'Inter', -apple-system, system-ui, sans-serif;
font-size: 0.875rem - 1rem;
font-weight: 400;
letter-spacing: 0.01em;
line-height: 1.6;

/* Code / Technical */
font-family: 'JetBrains Mono', 'Fira Code', monospace;
font-size: 0.875rem;
font-weight: 400;
letter-spacing: 0;
line-height: 1.5;

/* Label / UI */
font-family: 'Inter', -apple-system, system-ui, sans-serif;
font-size: 0.75rem;
font-weight: 500;
letter-spacing: 0.05em;
text-transform: uppercase;
```

### Type Scale (Modular 1.125)

```
12px (xs)
13px (sm)
14px (base)
16px (md)
18px (lg)
20px (xl)
23px (2xl)
26px (3xl)
29px (4xl)
33px (5xl)
37px (6xl)
42px (7xl)
```

### Typography Roles

| Component | Size | Weight | Color | Usage |
|-----------|------|--------|-------|-------|
| **Page Title** | 42px | 600 | Light Gray | Main heading, top-level section |
| **Section Title** | 26px | 600 | Light Gray | Subsection header |
| **Card Title** | 18px | 600 | Light Gray | Panel/component heading |
| **Body Copy** | 14px | 400 | Light Gray | Main content, readable text |
| **Label** | 12px | 500 | Muted Gray | Form labels, UI labels (uppercase) |
| **Hint/Caption** | 12px | 400 | Muted Gray | Placeholder, helper text |
| **Code Snippet** | 14px | 400 | Emerald Light | Inline code, monospace snippets |
| **UI Button Text** | 14px | 600 | Void or Light Gray | Button labels |

---

## 4. Component Stylings

### Buttons

**Primary Button (CTA)**
```
Background: Emerald (#10b981)
Text: Void (#0a0a0a), weight 600
Padding: 12px 20px (40px height)
Border: none
Border-radius: 8px
Transition: all 200ms ease-out

States:
  - default: emerald bg, void text
  - hover: emerald-light bg, void text, shadow-lg, scale-105
  - active: emerald-dark bg (deeper), void text
  - disabled: medium-gray bg, muted-gray text, no hover
  - focus: outline: 2px solid emerald-light, offset: 2px
```

**Secondary Button (Alternative)**
```
Background: Dark Gray (#1a1a1a)
Border: 1px solid Muted Gray (#9ca3af)
Text: Light Gray (#e5e5e5), weight 600
Padding: 12px 20px
Border-radius: 8px
Transition: all 200ms ease-out

States:
  - default: dark gray bg, light gray border, light gray text
  - hover: medium-gray bg, emerald border, emerald text
  - active: medium-gray bg, emerald border, emerald-light text
  - disabled: dark gray bg, muted-gray border, muted-gray text
  - focus: outline: 2px solid violet-light, offset: 2px
```

**Tertiary Button (Ghost)**
```
Background: transparent
Border: none
Text: Emerald (#10b981), weight 500
Padding: 12px 8px
Border-radius: 6px

States:
  - default: emerald text, transparent bg
  - hover: emerald-light text, dark-gray bg (subtle)
  - active: emerald text, dark-gray bg
  - disabled: muted-gray text, transparent bg
```

**Destructive Button (Delete/Remove)**
```
Background: Red (#ef4444)
Text: Light Gray (#e5e5e5), weight 600
Padding: 12px 20px
Border-radius: 8px

States:
  - default: red bg, light gray text
  - hover: red-dark bg, light gray text, shadow-lg
  - active: red-darker bg
  - disabled: medium-gray bg, muted-gray text
```

### Cards & Panels

```css
/* Card Surface */
background: #1a1a1a;
border: 1px solid rgba(255, 255, 255, 0.05);
border-radius: 12px;
padding: 24px;
box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.08);
backdrop-filter: blur(12px);
transition: all 200ms ease-out;

/* On Hover */
&:hover {
  border: 1px solid rgba(16, 185, 129, 0.2);
  box-shadow: 0 8px 40px rgba(16, 185, 129, 0.1),
              inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

/* Card Header */
border-bottom: 1px solid rgba(255, 255, 255, 0.05);
margin-bottom: 16px;
padding-bottom: 16px;
```

### Inputs & Forms

```css
/* Text Input */
background: rgba(255, 255, 255, 0.05);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: 8px;
color: #e5e5e5;
padding: 12px 16px;
font-family: 'Inter', system-ui;
font-size: 14px;
line-height: 1.5;
transition: all 200ms ease-out;

/* Placeholder */
&::placeholder {
  color: #9ca3af;
}

/* Focus State */
&:focus {
  outline: none;
  border: 1px solid #10b981;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
}

/* Error State */
&[data-error="true"] {
  border: 1px solid #ef4444;
  background: rgba(239, 68, 68, 0.05);
}
```

### Badge / Tag

```css
/* Status Badge */
display: inline-flex;
align-items: center;
gap: 6px;
padding: 4px 12px;
border-radius: 20px;
font-size: 12px;
font-weight: 500;
letter-spacing: 0.05em;
text-transform: uppercase;

/* Variants */
/* success */
background: rgba(16, 185, 129, 0.15);
color: #6ee7b7;
border: 1px solid rgba(16, 185, 129, 0.3);

/* warning */
background: rgba(249, 115, 22, 0.15);
color: #fdba74;
border: 1px solid rgba(249, 115, 22, 0.3);

/* error */
background: rgba(239, 68, 68, 0.15);
color: #fca5a5;
border: 1px solid rgba(239, 68, 68, 0.3);

/* info */
background: rgba(139, 92, 246, 0.15);
color: #d8b4fe;
border: 1px solid rgba(139, 92, 246, 0.3);
```

### Navigation / Sidebar

```css
/* Sidebar */
background: #1a1a1a;
border-right: 1px solid rgba(255, 255, 255, 0.05);
width: 260px;
padding: 24px 0;
position: sticky;
top: 0;
height: 100vh;
overflow-y: auto;

/* Nav Item */
padding: 12px 16px;
margin: 0 8px;
border-radius: 6px;
font-size: 14px;
color: #9ca3af;
cursor: pointer;
transition: all 200ms ease-out;

/* Nav Item Hover */
&:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e5e5e5;
}

/* Nav Item Active */
&[data-active="true"] {
  background: rgba(16, 185, 129, 0.15);
  border-left: 3px solid #10b981;
  color: #10b981;
  font-weight: 500;
}
```

---

## 5. Layout Principles

### Spacing Scale (8px base unit)

```
4px   (0.5x)
8px   (1x)
12px  (1.5x)
16px  (2x)
20px  (2.5x)
24px  (3x)
32px  (4x)
40px  (5x)
48px  (6x)
64px  (8x)
80px  (10x)
96px  (12x)
```

### Grid System

- **Base unit**: 8px
- **Container width**: 1440px (max) with 24px horizontal padding
- **Columns**: 12-column grid (120px col + 16px gutter on desktop)
- **Responsive breakpoints**:
  - `xs`: 0px (mobile)
  - `sm`: 640px (tablet)
  - `md`: 1024px (laptop)
  - `lg`: 1440px (desktop)

### Whitespace Philosophy

**GCA follows "modular sparsity"**: 
- Generous whitespace between sections (40-64px vertical)
- Tight whitespace within components (8-16px)
- Breathing room around text (12-16px padding in cards)

```
┌────────────────────────────────────────┐
│                                        │
│         SECTION HEADER                 │
│         (64px below)                   │
│                                        │
├────────────────────────────────────────┤
│                                        │
│  Card 1    Card 2    Card 3            │ (40px between cards)
│                                        │
├────────────────────────────────────────┤
│                                        │
│         NEXT SECTION                   │
│         (64px above)                   │
│                                        │
└────────────────────────────────────────┘
```

### Sections & Pages

- **Page margin**: 24px (mobile) → 40px (desktop)
- **Section max-width**: 1440px
- **Card padding**: 24px
- **List item padding**: 16px
- **Sidebar width**: 260px (desktop), collapsed to icon on mobile

---

## 6. Depth & Elevation System

GCA uses a **shadow hierarchy** to communicate elevation and interaction.

### Shadow Scale

```css
/* Elevation 0 (Flat, no shadow) */
box-shadow: none;

/* Elevation 1 (Subtle hover/focus) */
box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12),
            0 1px 2px rgba(0, 0, 0, 0.08);

/* Elevation 2 (Card default) */
box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15),
            0 2px 4px rgba(0, 0, 0, 0.1);

/* Elevation 3 (Card hover / Panel) */
box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2),
            0 4px 8px rgba(0, 0, 0, 0.12);

/* Elevation 4 (Modal / Dropdown) */
box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25),
            0 6px 12px rgba(0, 0, 0, 0.15);

/* Elevation 5 (Floating action / Top priority) */
box-shadow: 0 20px 48px rgba(0, 0, 0, 0.3),
            0 8px 16px rgba(0, 0, 0, 0.2);
```

### Surface Hierarchy

| Surface | Background | Border | Shadow | Usage |
|---------|-----------|--------|--------|-------|
| **Canvas** | #0a0a0a | none | none | Page background |
| **Surface 1** | #1a1a1a | 1px white/5% | elev-2 | Cards, panels, sections |
| **Surface 2** | #2d2d2d | 1px white/10% | elev-3 | Nested cards, hovered sections |
| **Surface 3** | #1a1a1a + overlay | 1px white/15% | elev-4 | Modals, dropdowns, floating UI |
| **Accent Surface** | rgba(16,185,129,0.1) | 1px emerald/30% | elev-2 | Active states, highlights |

### Glow Effects (Accent-colored)

Used for:
- Active navigation items
- Emergent code elements
- Governance-related highlights
- Micro-interactions (hover, focus)

```css
/* Emerald glow */
box-shadow: 0 0 16px rgba(16, 185, 129, 0.25),
            0 0 32px rgba(16, 185, 129, 0.1);

/* Violet glow (governance) */
box-shadow: 0 0 16px rgba(139, 92, 246, 0.25),
            0 0 32px rgba(139, 92, 246, 0.1);
```

---

## 7. Micro-Interactions & Animations

### Transition Speeds

```css
/* Quick (UI feedback) */
transition: all 100ms ease-out;

/* Standard (hover, state change) */
transition: all 200ms ease-out;

/* Deliberate (modal, expand/collapse) */
transition: all 300ms ease-out;

/* Slow (entrance, complex motion) */
transition: all 400ms ease-out;
```

### Common Patterns

**Hover Scale (Buttons, Cards)**
```css
transform: scale(1.02);
transition: all 200ms ease-out;
```

**Hover Color Shift (Links, Badge)**
```css
color: #6ee7b7; /* emerald-light */
transition: color 200ms ease-out;
```

**Focus Glow (Inputs, Interactive)**
```css
box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1),
            0 0 0 1px #10b981;
transition: all 200ms ease-out;
```

**Entrance Fade (Page load)**
```css
animation: fadeIn 400ms ease-out;

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

**Status Pulse (Alert, pending)**
```css
animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

**Governance Glow (Active workflow, consolidation)**
```css
animation: glow 3s ease-in-out infinite;

@keyframes glow {
  0%, 100% { 
    box-shadow: 0 0 16px rgba(16, 185, 129, 0.2),
                inset 0 0 16px rgba(16, 185, 129, 0.05); 
  }
  50% { 
    box-shadow: 0 0 32px rgba(16, 185, 129, 0.4),
                inset 0 0 24px rgba(16, 185, 129, 0.1); 
  }
}
```

---

## 8. Responsive Behavior

### Mobile-First Strategy

| Breakpoint | Device | Sidebar | Grid | Font | Padding |
|------------|--------|---------|------|------|---------|
| **xs** (0–639px) | Mobile phone | Collapsed (icon) | 1 column | -1 size | 16px |
| **sm** (640–1023px) | Tablet | Collapsed (icon) | 2 columns | base | 20px |
| **md** (1024–1439px) | Laptop | Visible (260px) | 3-4 columns | +0 size | 24px |
| **lg** (1440px+) | Desktop | Visible (260px) | 4-6 columns | +1 size | 40px |

### Touch Targets (Mobile)

- **Minimum**: 44×44px (WCAG recommended)
- **Comfortable**: 56×56px (buttons, interactive)
- **Spacing**: 8px minimum between touch targets

### Responsive Type Scaling

```css
/* Mobile */
@media (max-width: 639px) {
  h1 { font-size: 26px; line-height: 1.2; }
  h2 { font-size: 20px; }
  body { font-size: 14px; }
}

/* Tablet + Desktop */
@media (min-width: 1024px) {
  h1 { font-size: 42px; }
  h2 { font-size: 26px; }
  body { font-size: 14px; }
}
```

### Collapsing Strategy

**Mobile (xs–sm)**:
- Hide sidebar (show hamburger menu icon)
- Single-column layout
- Collapsed cards, stacked sections
- Simplified data tables (horizontal scroll or simplified view)

**Tablet (md)**:
- Show sidebar as icon-only
- 2–3 column grid
- Readable cards

**Desktop (lg)**:
- Full sidebar with labels
- 4–6 column grid
- Rich detail panels

---

## 9. Do's and Don'ts

### ✅ DO

- ✅ **Use the color palette**. Never hardcode custom colors — use semantic tokens.
- ✅ **Maintain hierarchy**. Font sizes, weights, and colors communicate importance.
- ✅ **Respect whitespace**. Generous spacing makes information scannable.
- ✅ **Animate purposefully**. Micro-interactions should clarify state, not distract.
- ✅ **Dark theme only**. No light mode (GCA is terminal-native infrastructure).
- ✅ **Accessible contrast**. All text ≥ 4.5:1 WCAG AA.
- ✅ **Code-first development**. Use Tailwind tokens, not design tools.
- ✅ **Test on real devices**. Mobile, tablet, desktop viewport testing mandatory.

### ❌ DON'T

- ❌ **Don't use custom colors**. Not approved by design system.
- ❌ **Don't ignore whitespace**. Cramped layouts are cognitive overload.
- ❌ **Don't animate indiscriminately**. Respect user's `prefers-reduced-motion`.
- ❌ **Don't skip focus states**. Keyboard accessibility is non-negotiable.
- ❌ **Don't mix fonts**. Stick to Inter (UI) and JetBrains Mono (code/display).
- ❌ **Don't use light backgrounds**. GCA is dark-themed infrastructure.
- ❌ **Don't violate hierarchy**. Every component must have clear visual weight.
- ❌ **Don't assume desktop**. Always design mobile-first.

---

## 10. Agent Prompt Guide

When asking your AI coding agent to build pages following this DESIGN.md:

### Quick Prompt Template

```
Build [COMPONENT/PAGE] following these rules:

1. COLOR PALETTE:
   - Background: Void (#0a0a0a)
   - Primary accent: Emerald (#10b981)
   - Text: Light Gray (#e5e5e5)
   - Borders: white @ 5-10% opacity

2. TYPOGRAPHY:
   - Headers: JetBrains Mono, weight 600, size 26-42px
   - Body: Inter, weight 400, size 14px, line-height 1.6
   - Code: JetBrains Mono, size 14px

3. COMPONENTS:
   - Buttons: Emerald bg on hover, 200ms transition
   - Cards: Dark Gray surface, subtle border, elevation shadow
   - Inputs: Dark bg, Emerald focus ring, 200ms transition
   - Navigation: Active state = Emerald text + left border

4. SPACING:
   - 24px card padding
   - 40px section vertical spacing
   - 16px component gaps

5. INTERACTIONS:
   - Hover: scale(1.02), color shift, glow
   - Focus: emerald ring, 200ms ease-out
   - Disabled: muted-gray text, no hover

Reference: ~/GCA/DESIGN.md (full specification)
```

### Color Reference (Copy-Paste)

```
Primary Colors:
- Void (bg):        #0a0a0a
- Dark Gray (card): #1a1a1a
- Light Gray (text):#e5e5e5
- Muted Gray (hint):#9ca3af

Accent Colors:
- Emerald (active):  #10b981
- Violet (gov):      #8b5cf6
- Orange (warn):     #f97316
- Red (error):       #ef4444
- Cyan (infra):      #06b6d4
```

---

## Implementation Checklist

- [ ] Tailwind config imported (colors, spacing, shadows)
- [ ] Inter font loaded (`fonts.googleapis.com`)
- [ ] JetBrains Mono font loaded (code/display)
- [ ] Dark theme enforced in `tailwind.config.ts`
- [ ] Hover states implemented (scale, color, glow)
- [ ] Focus rings visible (accessibility)
- [ ] Responsive breakpoints tested (xs, sm, md, lg)
- [ ] Mobile touch targets ≥ 44px
- [ ] Animations respect `prefers-reduced-motion`
- [ ] All text contrast ≥ 4.5:1 WCAG AA
- [ ] Components follow card/button/input patterns
- [ ] Navigation hierarchy clear (sidebar, active states)

---

**Version**: 1.0  
**Last Updated**: 2026-04-27  
**Format**: Google Stitch DESIGN.md standard  
**Status**: Production-ready, evolving with feedback
