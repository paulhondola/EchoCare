# 07 · DAS Web Dashboard & Google Stitch Design System

Part of the [Sentinela specification](README.md). This specification defines the visual design system, information architecture, component specifications, and ready-to-copy **Google Stitch** prompt packages for the DAS (Direcția de Asistență Socială) Emergency Dispatch Web Dashboard (MVP §G15, UC-04, UC-07, UC-11, UC-12, UC-14, 04 §1).

The visual language and ergonomics are modeled directly after the **GitHub Projects (v2 Memex)** board and high-density telemetry consoles: dark tactical surfaces, compact bordered item cards, label pills, tabular monospace data, view switching (`Board` vs `Table`), and seamless right-side slide-over inspection drawers.

---

## 1. Executive Summary & Design Principles

| Dimension | Specification |
|---|---|
| **Aesthetic Paradigm** | **GitHub Dark Dimmed / Tactical Ops Console** (`#0d1117` / `#161b22`). Designed for 8–12 hour dispatch shifts with zero eyestrain and high-contrast emergency signals. |
| **Ergonomic Model** | **GitHub Project Kanban Board** with dual-mode parity: `Board view` (Incident triage & rapid dispatch) and `Table view` (Seniors health monitoring registry). |
| **Inspection Pattern** | **Slide-Over Drawer** (540px width from right edge). Operators never lose board context or scroll position while inspecting call transcripts, addresses, or medical notes. |
| **Emergency Signalling** | Audio siren with browser opt-in ("Pornește alertele sonore") paired with a flashing sticky alert banner on new open Code Red incidents (UC-11). |
| **Language & Text** | Interface labels and actions in Romanian; code, comments, tokens, and technical documentation in English. |

---

## 2. Design System Tokens (Tailwind v4 / CSS Variables)

### 2.1 Color Matrix (GitHub Dark Dimmed Tactical Theme)

```css
:root {
  /* Canvas & Structural Layers */
  --color-canvas-default:    #0d1117; /* Root workspace background */
  --color-canvas-subtle:     #161b22; /* Column canvas, navigation sidebar */
  --color-canvas-card:       #21262d; /* Card surfaces, table rows */
  --color-canvas-card-hover: #292e36; /* Card hover, active list item */
  --color-canvas-inset:      #010409; /* Deep input backgrounds, terminal logs */

  /* Strokes & Dividers */
  --color-border-default:    #30363d; /* Card borders, column dividers */
  --color-border-subtle:     #21262d; /* Subtle table row dividers */
  --color-border-strong:     #6e7681; /* Focused inputs, active tabs */

  /* Text & Typography */
  --color-fg-default:        #f0f6fc; /* Primary titles, numbers, active labels */
  --color-fg-muted:          #8b949e; /* Column counters, descriptions, timestamps */
  --color-fg-subtle:         #484f58; /* Placeholders, inactive icons */

  /* Primary Accent & Brand */
  --color-accent-fg:         #58a6ff; /* GitHub Blue/Cyan interactive buttons, links */
  --color-accent-subtle:     rgba(56, 139, 253, 0.15); /* Accent chip background */

  /* Mission-Critical Emergency Signals (Status Model §3) */
  --color-danger-fg:         #f85149; /* Cod Roșu: Active emergency incident */
  --color-danger-emphasis:   #da3633; /* Crimson badge background, siren border */
  --color-danger-subtle:     rgba(248, 81, 73, 0.15); /* Alert banner tint */
  --color-danger-glow:       rgba(248, 81, 73, 0.35);

  --color-attention-fg:      #d29922; /* Cod Galben: Warning, unanswered call */
  --color-attention-emphasis:#bb8009; /* Amber badge fill */
  --color-attention-subtle:  rgba(210, 153, 34, 0.15);

  --color-success-fg:        #3fb950; /* Cod Verde: Senior OK, resolved, System Healthy */
  --color-success-emphasis:  #238636; /* Emerald badge fill */
  --color-success-subtle:    rgba(63, 185, 80, 0.15);

  --color-neutral-fg:        #8b949e; /* Inactive, disconnected devices */
  --color-neutral-emphasis:  #6e7681;
}
```

### 2.2 Typography Scale
- **Primary Interface Font**: `Inter`, `Geist Sans`, or `-apple-system` for labels, buttons, headers.
- **Telemetry & Monospace Font**: `JetBrains Mono` or `SF Mono` with `font-variant-numeric: tabular-nums` for timestamps, GPS coordinates, vital stats, and incident IDs (`#INC-104`).
- **Scale**:
  - `Header Title`: `1.25rem` (20px), font-semibold, letter-spacing `-0.015em`.
  - `Column Header`: `0.875rem` (14px), font-semibold.
  - `Card Title`: `0.9375rem` (15px), font-semibold.
  - `Card Body / Meta`: `0.8125rem` (13px), font-normal.
  - `Badge / Pill / Micro-label`: `0.75rem` (12px), font-mono, font-medium.

### 2.3 Borders & Elevation
- **Corner Radii**:
  - Cards & Modals: `rounded-md` (6px) — strict, compact GitHub aesthetic.
  - Pills & Badges: `rounded-full` (9999px).
  - Buttons: `rounded-md` (6px).
- **Elevation**: Flat 1px border strokes (`border border-[#30363d]`). Drop shadows are reserved exclusively for the overlaying Slide-Over Drawer (`shadow-2xl`).

---

## 3. Information Architecture & Navigation

The dashboard is structured into a persistent left navigation sidebar and a full-height command workspace:

```
┌─────────────────┬──────────────────────────────────────────────────────────────────┐
│ AppSidebar      │ TopNav: EmergencyAlertBar (sticky if Cod Roșu open)              │
│ (240px fixed)   ├──────────────────────────────────────────────────────────────────┤
│                 │ Workspace Header: Title, View Switcher [Board | Table], Search   │
│ • SENTINELA DAS ├──────────────────────────────────────────────────────────────────┤
│                 │                                                                  │
│ [🚨 Incidente 3]│  [ GitHub-style Kanban Columns / Telemetry Table ]               │
│ [👥 Seniori 48] │                                                                  │
│ [📋 Înrolări 2] │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│ [👨‍⚕️ Personal 4] │  │ Deschise (2) │ │ În lucru (1) │ │Rezolvate(14)│              │
│ [📡 Campanii]   │  ├──────────────┤ ├──────────────┤ ├──────────────┤              │
│                 │  │ [Card Red]   │ │ [Card Amber] │ │ [Card Green] │ ┌──────────┐ │
│ ─────────────── │  │              │ │              │ │              │ │SlideOver │ │
│ • Sistem OK 3ms │  │ [Card Red]   │ │              │ │              │ │Drawer    │ │
│ • Alerte: [ON]  │  └──────────────┘ └──────────────┘ └──────────────┘ │ (540px)   │ │
│ • Dispecer Pop  │                                                     │ Dossier    │ │
│ • [Ieșire]      │                                                     └──────────┘ │
└─────────────────┴──────────────────────────────────────────────────────────────────┴─┘
```

---

## 4. Component Library Specifications

### 4.1 Component: `EmergencyAlertBar` (Sticky Alert Banner)
- **Trigger**: Visible whenever any incident in `fetchIncidents` has `status === "open"`.
- **Styling**: `bg-[#da3633]/20 border-b border-[#f85149] px-4 py-2.5 flex items-center justify-between animate-pulse`.
- **Content**:
  - Left: Audio Siren icon (`BellRing`) + `🚨 COD ROȘU: [Senior Name] — [Trigger Reason] (deschis acum [X] min)`.
  - Right: Quick Action button `[⚡ Preiau Cazul]` + `[Vezi Dosar]`.
- **Audio Cue**: Plays repeating acoustic warning chime until dispatcher claims the incident (UC-11).

### 4.2 Component: `IncidentBoard` (GitHub Projects Kanban)
- **Columns**:
  1. **Deschise (`open`)**:
     - Header: Circle dot icon (red), title `Deschise`, count pill `2`, crimson accent border.
     - Actions: Each card contains prominent `[Preiau]` button.
  2. **În lucru (`in_progress`)**:
     - Header: Gear / Clock icon (amber), title `În lucru`, count pill `1`, amber accent border.
     - Content: Shows which dispatcher took it (`Preluat de Ion Popescu`).
     - Actions: Quick resolution form trigger `[Rezolvă Cazul]`.
  3. **Rezolvate (`resolved`)**:
     - Header: CheckCircle icon (green), title `Rezolvate`, count pill `14`, green accent border.
     - Content: Displays outcome chip (`Senior OK`, `Echipaj trimis`, `112 apelat`) and resolver note.

### 4.3 Component: `IncidentCard` (GitHub Item Card)
- **Layout**:
  ```
  ┌────────────────────────────────────────────────────────┐
  │ #INC-104 · acum 3 min                     [Transferat] │
  │ Maria Ionescu (doamna Maria)                           │
  │ Puls ridicat în repaus (128 bpm)                       │
  │ "Mă simt amețită și îmi bate inima foarte repede..."   │
  ├────────────────────────────────────────────────────────┤
  │ 📍 Str. Florilor 12, Sc. A, Ap. 4, Interfon 04         │
  │ [⚡ Preiau]                             [👤 Ion Popescu]│
  └────────────────────────────────────────────────────────┘
  ```
- **Styling**: `bg-[#161b22] border border-[#30363d] hover:border-[#58a6ff] rounded-md p-3 mb-2.5 shadow-sm transition-all`.
- **Severity Stripe**: 3px solid vertical left border (`#f85149` for open, `#d29922` for in-progress, `#3fb950` for resolved).

### 4.4 Component: `SeniorsTable` (GitHub Projects Table View)
- **Features**:
  - Filter Tabs: `Toți (48)` | `Cod Roșu (2)` | `Cod Galben (5)` | `Cod Verde (41)`.
  - Omni-Search Bar: Search by name, phone (+40…), address, or family doctor.
  - Columns:
    1. **Senior**: Name, form of address, phone number (fix/mobil chip).
    2. **Stare & Cod**: Status pill (`Cod Roșu`, `Cod Galben`, `Cod Verde`) with reason.
    3. **Ultimul Contact**: Relative timestamp + call result badge.
    4. **Dispozitive**: Watch status & battery, Home Node temperature (`22.4°C`).
    5. **Adresă**: Street, number, landmark, intercom code.
    6. **Acțiuni**: `[Dosar]` button opens Slide-Over Drawer.

### 4.5 Component: `SlideOverDrawer` (Inspection Dossier)
- **Width**: `540px`, slides in from right with backdrop overlay.
- **Sections**:
  1. **Header**: Senior name, code badge, address, quick-copy buttons for Address, GPS coordinates, and Intercom code.
  2. **Contacte de Urgență**: Caregivers directory with 1-click `tel:` buttons, family doctor info.
  3. **Istoric Apeluri & Transcrieri**: Expandable call accordion. For each call: duration, audio turns, AI quote citations, final severity.
  4. **Formular Rezolvare**: (If `in_progress`) Outcome dropdown (`senior_ok`, `team_sent`, `called_112`, `not_reached`, `false_alarm`) + mandatory note field + `[Finalizează Incident]`.

### 4.6 Component: `DutyConsole` (Staff & Duty Roster)
- Interactive toggle switch `De serviciu (on_duty)` per DAS dispatcher.
- Persistent warning banner if active on-duty count is `0`: `⚠️ Nimeni de serviciu. Apelurile de urgență nu vor putea fi transferate.` (06 §operations).

### 4.7 Component: `CampaignConsole` (Weather Simulation & Dialing)
- Emergency trigger buttons: `[Lansează Campanie Caniculă]` / `[Lansează Campanie Ger]`.
- Batch progress bar showing dialed seniors, connected, and yellow/red escalations.
- System Telemetry gauges: Twilio SIP status, active calls counter, AI turn latency.

---

## 5. Google Stitch Sendoff Prompt Package

Use the following ready-to-copy prompts in **Google Stitch** to generate the design system and high-fidelity screen prototypes.

### Prompt 1: Design System Foundations & Tokens
```text
Project: Sentinela DAS Emergency Dispatch Dashboard
Role: UI/UX Design System Designer
Task: Create the Design System Token Manifest and Atomic UI Components in Google Stitch.

Visual Aesthetic: GitHub Projects (v2 Memex) Dark Tactical Theme.
Theme Palette:
- Canvas Default: #0d1117
- Canvas Subtle: #161b22
- Canvas Card: #21262d
- Canvas Card Hover: #292e36
- Border Default: #30363d
- Border Strong: #6e7681
- Text Primary: #f0f6fc
- Text Muted: #8b949e
- Accent Cyan/Blue: #58a6ff (Glow: rgba(88, 166, 255, 0.2))
- Emergency Danger (Cod Roșu): #f85149 (Background: #da3633, Glow: rgba(248, 81, 73, 0.35))
- Warning Attention (Cod Galben): #d29922 (Background: #bb8009)
- Success (Cod Verde): #3fb950 (Background: #238636)

Typography:
- Primary Sans: Inter / Geist Sans
- Tabular Monospace: JetBrains Mono / SF Mono for IDs (#INC-104), GPS coordinates, clock, timers, and phone numbers.

Components to generate:
1. Navigation Sidebar (w-60, dark charcoal #161b22, bordered item pills with live badge counters).
2. GitHub-style Kanban Column (Header with icon, title, item count chip, 3 columns: Deschise, În lucru, Rezolvate).
3. GitHub-style Item Card (3px left severity stripe, issue #ID, relative timestamp, Romanian tags, quick actions).
4. Telemetry Status Chips (Cod Roșu, Cod Galben, Cod Verde, Inactiv).
5. Sticky Emergency Alert Bar with audio siren pulse.
6. Slide-Over Inspection Drawer (540px right drawer with tabs for Dossier, Call Transcripts, and Resolution Form).
```

### Prompt 2: Screen 1 — Incidente (GitHub Project Kanban Board)
```text
Project: Sentinela DAS Emergency Dispatch Dashboard
Screen: Incidente (Emergency Incident Kanban Board)

Layout Specification:
- Fixed Left Sidebar (240px):
  - Brand: "SENTINELA DAS" with glowing green indicator "SISTEM ACTIV (2.1ms)".
  - Menu Items: Incidente (badge: 2 red), Monitorizare Seniori (48), Cereri Înrolare (2), Personal (4), Campanii Meteo.
  - Footer: Audio alert toggle button "Alerte Sonore: Active", logged-in user "Dispecer: Elena Vasilescu", Logout button.

- Top Sticky Alert Banner:
  - Background: dark red tint with red pulsing border.
  - Content: "🚨 COD ROȘU ACTIV: Maria Ionescu — Puls ridicat în repaus (128 bpm) · deschis acum 3 min" + [⚡ Preiau Cazul].

- Workspace Header:
  - Title: "Dispecerat Incidente"
  - View Switcher tabs: [▦ Board (Kanban)] [☵ Table]
  - Search/Filter Input: "Filtrează incidente: is:open ..."
  - Status Indicators: "1 Dispecer de serviciu" (green pill).

- Kanban Columns (3 columns, GitHub Project v2 style):
  1. Column "Deschise (2)":
     - Card 1 (#INC-104): Maria Ionescu, 78 ani. "Puls ridicat în repaus (128 bpm)". Quote: "Mă simt foarte amețită". Badge: [Transferat la DAS]. Adresă: Str. Florilor 12, Ap. 4. Action: Primary red button [Preiau].
     - Card 2 (#INC-105): Gheorghe Dumitru, 82 ani. "Buton SOS acționat". Badge: [Nepreluat]. Adresă: Bd. Unirii 45. Action: [Preiau].
  2. Column "În lucru (1)":
     - Card 3 (#INC-102): Elena Popa. "Cădere detectată de ceas". Preluat de: Ion Popescu (acum 8 min). Action: Button [Rezolvă].
  3. Column "Rezolvate (14)":
     - Card 4 (#INC-101): Vasile Radu. Rezultat: [🟢 Senior OK - Alarmă falsă]. Notă: "S-a verificat telefonic, seniorul a confirmat că a apăsat din greșeală."
```

### Prompt 3: Screen 2 — Monitorizare Seniori (Telemetry Table View)
```text
Project: Sentinela DAS Emergency Dispatch Dashboard
Screen: Monitorizare Seniori (Senior Registry Telemetry Table)

Layout Specification:
- Retain Fixed Left Sidebar and Header.
- Workspace Subheader:
  - Filter Tabs: [Toți (48)] [🚨 Cod Roșu (2)] [⚠️ Cod Galben (5)] [🟢 Cod Verde (41)]
  - Search Input: "Caută după nume, telefon, adresă, medic de familie..."
  - Export & Refresh controls.

- Data Table (GitHub Projects Table style, dark theme #161b22, borders #30363d):
  - Row 1:
    - Senior: "Maria Ionescu" (doamna Maria), mobil +40 722 111 222
    - Cod Stare: Pill [🚨 Cod Roșu] "Puls ridicat în repaus (128 bpm)"
    - Ultimul Apel: "acum 4 min" · Rezultat: Transferat DAS
    - Dispozitive: Ceas (Activ · 84%), Nod Ambiental (Online · 22.1°C)
    - Adresă & Sector: Str. Florilor 12, Sc. A, Ap. 4, Sector 3
    - Acțiuni: Button [Vezi Dosar]
  - Row 2:
    - Senior: "Ion Popescu" (domnul Ion), fix +40 21 333 4455
    - Cod Stare: Pill [⚠️ Cod Galben] "Apel nepreluat (2 încercări)"
    - Ultimul Apel: "acum 42 min" · Rezultat: Fără răspuns
    - Dispozitive: Fără ceas
    - Adresă: Calea Victoriei 102, Sector 1
    - Acțiuni: Button [Vezi Dosar]
  - Row 3:
    - Senior: "Ana Georgescu" (doamna Ana), mobil +40 733 444 555
    - Cod Stare: Pill [🟢 Cod Verde] "Stare confirmată bună"
    - Ultimul Apel: "azi la 10:15" · Rezultat: Încheiat normal
    - Dispozitive: Ceas (Activ · 92%)
    - Adresă: Str. Mihai Eminescu 8, Sector 2
    - Acțiuni: Button [Vezi Dosar]
```

### Prompt 4: Screen 3 — Slide-Over Inspection Drawer
```text
Project: Sentinela DAS Emergency Dispatch Dashboard
Screen: Slide-Over Inspection Drawer (540px right panel overlaid on Kanban Board)

Layout Specification:
- Backdrop Dimmer: rgba(0, 0, 0, 0.6)
- Drawer Container: 540px width, bg #161b22, border-left #30363d, shadow-2xl.
- Drawer Header:
  - Close button [✕] top right.
  - Senior Name: "Maria Ionescu" (78 ani)
  - Code Badge: [🚨 COD ROȘU - Puls ridicat în repaus]
  - Address Bar: "Str. Florilor 12, Sc. A, Et. 2, Ap. 4, Sector 3"
  - Quick Copy Action Row: [📋 Copiază Adresă] [🔑 Interfon: 04B] [🗺️ GPS: 44.4325, 26.1038]

- Tabs: [1. Urgență & Acces] [2. Transcriere Apel] [3. Telemetrie Dispozitive] [4. Rezolvare Caz]

- Tab 1 Content (Urgență):
  - Contact Senior: Telefon mobil: 0722 111 222 [📞 Apelează Senior]
  - Reper orientare: "Lângă farmacia Catena, intrarea prin spate"
  - Deținător cheie de rezervă: "Vecina de la Ap. 3 (Doamna Rodica, 0721 000 111)"
  - Aparținători înregistrați:
    - Andrei Ionescu (Fiul) · 0723 999 888 [📞 Apelează]
    - Elena Ionescu (Fiica) · 0724 777 666 [📞 Apelează]

- Tab 2 Content (Transcriere Apel AI Turn-by-Turn):
  - Apel inițiat la: 14:32:10 (Twilio SIP, durată 2m 14s)
  - Transcriere sincronizată:
    - 14:32:15 Sistem AI: "Bună ziua, doamna Maria. Sentinela vă sună. Cum vă simțiți astăzi?"
    - 14:32:22 Senior: "Nu mă simt deloc bine maică... Îmi bate inima foarte tare și tremur."
    - 14:32:30 Sistem AI: "Înțeleg, doamna Maria. Rămâneți liniștită, vă transfer imediat către dispecerat."
  - Audio Handover Status: [Transferat cu succes la telefonul de serviciu DAS]

- Tab 4 Content (Rezolvare Incident):
  - Dropdown Rezultat: [Selectează: Senior OK / Echipaj trimis / Apelat 112 / Nu a răspuns / Alarmă falsă]
  - Textarea: Notă obligatorie de rezolvare ("Descrieți pe scurt măsurile luate...")
  - Button: Primary green button [Finalizează și Arhivează Incident]
```

### Prompt 5: Screen 4 — Campanii Meteo & Serviciu Dispecerat
```text
Project: Sentinela DAS Emergency Dispatch Dashboard
Screen: Campanii Meteo & Personal de Serviciu (Ops Control)

Layout Specification:
- Section 1: Panou Dispeceri de Serviciu (On-Duty Roster)
  - Card with list of DAS staff members:
    - Dispecer Elena Vasilescu · 0722 123 456 · Switch [ON DUTY: DA]
    - Dispecer Mihai Andrei · 0733 987 654 · Switch [ON DUTY: NU]
  - System Check Warning (conditional if 0 on-duty):
    - Red alert box: "⚠️ ATENȚIE: Niciun dispecer nu este de serviciu! Apelurile de urgență nu pot fi transferate."

- Section 2: Lansator Campanie Avertizare Meteo (UC-05)
  - Description: "Lansează apeluri automate de verificare a stării de bine pentru toți seniorii activi în caz de vreme extremă."
  - Action Buttons:
    - [🔥 Lansează Campanie Caniculă (Cod Portocaliu / Roșu)]
    - [❄️ Lansează Campanie Ger / Viscol]
  - Active Campaign Telemetry Widget:
    - Apeluri programate: 48 seniori
    - Progres apeluri: [████████████░░░░░] 68% (33/48 apeluri finalizate)
    - Rezultate: 30 Verzi (Senior OK) · 2 Galbene (Fără răspuns) · 1 Roșu (Incident deschis)
```

---

## 6. Verification & Implementation Checklist

- [x] Design tokens documented with CSS custom properties matching GitHub Projects dark theme.
- [x] Component interaction patterns specified for all core workflows (Incidents, Registry, Slide-over, Duty, Campaigns).
- [x] High-urgency audio siren and sticky alert banner specified per Sentinela spec UC-11 and 06 §operations.
- [x] Monospace telemetry requirements codified for tabular alignment of biometric and temporal data.
- [x] Ready-to-use Google Stitch multi-prompt generation package compiled in Part 5.
- [x] System Health backend endpoint (`GET /api/system/health`) and frontend status indicator completed and committed.
