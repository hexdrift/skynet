# Skynet Brand Guidelines

## Brand Identity

- **Name:** Skynet
- **Tagline:** מערכת אופטימיזציית פרומפטים מבוססת DSPy
- **Language:** Hebrew (RTL)
- **Locale:** he_IL

## Color Palette

### Light Mode
| Token | Hex | Usage |
|-------|-----|-------|
| Background | `#FFFFFF` | Page background |
| Foreground | `#0a0a0a` | Primary text |
| Surface 1 | `#FFFFFF` | Cards, elevated surfaces |
| Surface 2 | `#fafafa` | Page bg, subtle backgrounds |
| Surface 3 | `#f5f5f5` | Muted backgrounds |
| Border | `#e5e5e5` | Borders, dividers |
| Border Subtle | `#ebebeb` | Very subtle dividers |
| Text Secondary | `#525252` | Secondary text |
| Text Muted | `#a3a3a3` | Muted labels |
| Blue | `#2563eb` | Links, accents |
| Danger | `#DC2626` | Errors, destructive |
| Success | `#16a34a` | Success states |
| Warning | `#ca8a04` | Warnings |

### Dark Mode
| Token | Hex | Usage |
|-------|-----|-------|
| Background | `#0a0a0a` | Page background |
| Foreground | `#ededed` | Primary text |
| Card | `#111111` | Cards (with `rgba(17,17,17,0.8)` + blur) |
| Surface 2 | `#171717` | Secondary surfaces |
| Surface 3 | `#1f1f1f` | Tertiary surfaces |
| Border | `#262626` | Borders |
| Text Muted | `#a3a3a3` | Muted labels |
| Blue | `#3b82f6` | Links, accents |

### Accent Colors (Orbs & Gradients)
| Color | Light `rgba` | Dark `rgba` | Usage |
|-------|-------------|-------------|-------|
| Cyan | `rgba(56, 189, 248, 0.1)` | `rgba(56, 189, 248, 0.08)` | Primary orb, glow effects |
| Purple | `rgba(139, 92, 246, 0.08)` | `rgba(139, 92, 246, 0.1)` | Secondary orb, gradient text |
| Teal | `rgba(20, 184, 166, 0.07)` | `rgba(20, 184, 166, 0.07)` | Tertiary orb |
| Pink | `rgba(244, 114, 182, 0.05)` | `rgba(244, 114, 182, 0.06)` | Quaternary orb |

### Chart Colors (Dark Mode)
`#f472b6` (pink), `#34d399` (emerald), `#60a5fa` (blue), `#fbbf24` (amber), `#a78bfa` (violet)

## Typography

| Role | Font | Weight | Usage |
|------|------|--------|-------|
| Body | Heebo Variable | 400 | Hebrew body text, UI labels |
| Headings | Inter Variable | 700 | Display headings, titles |
| Code | JetBrains Mono Variable | 400 | Code blocks, monospace elements |

### Heading Gradients
- **Light:** `linear-gradient(135deg, #0a0a0a 0%, #1e40af 60%, #7c3aed 100%)`
- **Dark:** `linear-gradient(135deg, #ffffff 0%, #38bdf8 50%, #a78bfa 100%)`

## Design Tokens

| Token | Value |
|-------|-------|
| Border radius | `0.5rem` (base) |
| Duration fast | `120ms` |
| Duration base | `160ms` |
| Ease snappy | `cubic-bezier(0.2, 0.8, 0.2, 1)` |
| Card transition | `300ms` |
| Button hover scale | `1.02` |
| Touch active scale | `0.97` |
| Min touch target | `44px` |

## Logo

- File: `public/skynet_logo.svg`
- Favicon: `public/favicon.svg`
- Theme: Navy/Steel/Cyan (T-800 inspired)

## Button Glow Effects

- **Light hover:** `0 0 20px rgba(99, 102, 241, 0.3), 0 0 40px rgba(99, 102, 241, 0.1)`
- **Dark hover:** `0 0 20px rgba(56, 189, 248, 0.25), 0 0 40px rgba(139, 92, 246, 0.15)`

## Scroll Progress Bar

Gradient: `linear-gradient(90deg, #38bdf8, #8b5cf6, #ec4899)` — 2px height, fixed top.
