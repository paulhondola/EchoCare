---
name: EchoCare DAS
description: The DAS dispatch dashboard, a dark board where colour means status and nothing else.
colors:
  canvas: "#0d1117"
  subtle: "#161b22"
  card: "#21262d"
  inset: "#010409"
  line: "#30363d"
  line-strong: "#6e7681"
  fg: "#f0f6fc"
  fg-soft: "#c9d1d9"
  fg-muted: "#8b949e"
  fg-subtle: "#6e7681"
  off: "#484f58"
  link: "#58a6ff"
  rosu: "#f85149"
  rosu-strong: "#da3633"
  rosu-hover: "#e5534b"
  rosu-fg: "#ff7b72"
  galben: "#d29922"
  galben-fg: "#e3b341"
  verde: "#3fb950"
  verde-strong: "#238636"
  verde-hover: "#2ea043"
  verde-fg: "#56d364"
typography:
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.08em"
  data:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "11.5px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  none: "0px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
components:
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  button-danger:
    backgroundColor: "{colors.rosu-strong}"
    textColor: "#ffffff"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  button-danger-hover:
    backgroundColor: "{colors.rosu-hover}"
  button-success:
    backgroundColor: "{colors.verde-strong}"
    textColor: "#ffffff"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  button-success-hover:
    backgroundColor: "{colors.verde-hover}"
  button-link:
    backgroundColor: "{colors.card}"
    textColor: "{colors.link}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  input:
    backgroundColor: "{colors.inset}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    height: "32px"
  card-incident:
    backgroundColor: "{colors.card}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "10px 12px 12px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.fg-soft}"
    rounded: "{rounded.none}"
    padding: "8px 10px"
  nav-item-active:
    backgroundColor: "{colors.card}"
    textColor: "{colors.fg}"
  table-header:
    backgroundColor: "{colors.subtle}"
    textColor: "{colors.fg-muted}"
    typography: "{typography.label}"
    padding: "9px 12px"
  form-panel:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.fg}"
    padding: "16px 20px 20px"
    width: "360px"
  sign-in-card:
    backgroundColor: "{colors.subtle}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "24px"
    width: "384px"
  slide-over:
    backgroundColor: "{colors.subtle}"
    textColor: "{colors.fg}"
    width: "540px"
---

# Design System: EchoCare DAS

## Overview

**Creative North Star: "The Signal Board"**

The dashboard is a board of cards and bars where colour means status and nothing else. Everything structural is graphite: near-black canvas, grey rules, grey type. Red, amber and green are the three codes, Cod Roșu, Cod Galben and Cod Verde, and the same three meanings everywhere else: alarm, caution, clear. A dispatcher scanning the board at hour ten reads colour as information, never as decoration. Blue is the one colour outside that scale; it marks what can be clicked, focused or chosen, and an enrollment still under way.

The structure is Modernist and compact: square corners everywhere, 2px rules between regions, 1px borders around things, flush-left heavy button labels, small 13px body text, and monospace for every id, time and count. Density is high on purpose: the board, the table and the dossier hold a whole shift's worth of incidents without scrolling hunts. The palette is GitHub's dark theme (spec 07 §2.1) on that square structure.

One theme only: dark. There is no light mode and no rounded variant.

**Key Characteristics:**
- Colour is reserved for status: red alarm, amber caution, green clear; blue is the only other accent.
- Square corners (0px) on every element.
- 2px rules divide regions; 1px borders outline items.
- Archivo for the interface, JetBrains Mono for ids, times and numbers.
- Flat: depth comes from tonal layers, with one shadow for the slide-over.
- Compact and exact: 13px body, tight padding, tabular figures.

## Colors

A graphite ramp for structure plus three code colours and one signal blue, each code with a fill, a strong fill and a light text tint.

### Primary
- **Signal Blue** (link): links, the link button, the active tab underline, the focus ring (2px outline, 2px offset), text selection at 30%, hovered card borders, the selected option in a segmented control or outcome list (12–15% wash), the 3px bar on an enrollment request, the agent's speaker label in a transcript. It means "you can act or choose here". Its one status use is an enrollment still in progress (Cerere trimisă, Acceptat, the În înrolare tab dot): a step under way, never an alarm, caution or all-clear.

### Status colours
- **Alarm Red** (rosu): Cod Roșu and anything that needs a person now. The 3px bar on an open incident card, the banner's 2px bottom rule and dot, the open-count badge in the sidebar, the "Nimeni de serviciu" chip and the no-one-on-duty bar on Personal, failed-load notices. **Alarm Red Strong** (rosu-strong) fills the danger button (Preiau, Încheie) and the alarm bar wash at 20%; **Alarm Red Hover** (rosu-hover) is its hover. **Alarm Red Text** (rosu-fg) is red text on dark: the COD ROȘU and ATENȚIE labels, an open incident's reason, error messages.
- **Caution Amber** (galben): Cod Galben, in-progress incidents, enrollment problems (refused, wrong number, unreachable), and notices that the data shown is stale because the last re-read failed. **Caution Amber Text** (galben-fg) for amber text and chip labels.
- **All-Clear Green** (verde): Cod Verde, resolved incidents, De serviciu, an active campaign, the healthy system dot, the sound switch when on, success notices. **All-Clear Green Strong** (verde-strong) fills the confirming button (Acceptă, Adaugă, Lansează, Confirmă, Finalizează); **All-Clear Green Hover** (verde-hover) is its hover; **All-Clear Green Text** (verde-fg) for chip labels and success text.

### Neutral
- **Night Canvas** (canvas): the root background behind everything.
- **Panel Graphite** (subtle): the sidebar, board columns, table header, slide-over.
- **Card Graphite** (card): cards, the default button, the active nav item, avatar squares.
- **Deep Inset** (inset): search fields, note fields and other inputs, sunk below the page.
- **Rule Grey** (line): every border and rule, and the neutral count badge.
- **Strong Rule** (line-strong): outline-button borders. The same value as **Faint Text** (fg-subtle), which is for shapes only (the health dot while "Se verifică…"): at 3.8–4.1:1 it is too faint for text.
- **Paper White** (fg): primary text, titles, numbers.
- **Soft Text** (fg-soft): secondary text such as inactive nav labels and table cells.
- **Muted Text** (fg-muted): timestamps, counters, labels, placeholders, inactive icons.
- **Off Grey** (off): the sound switch track when off.

### Named Rules
**The Colour Is Status Rule.** Red means alarm or failure, amber means caution, green means clear or done, on every page, in that order of urgency. The three codes are the main case; incident states, notices, duty and actions follow the same meanings. Never use them for brand, emphasis or decoration.

**The Tint, Not Fill Rule.** Chips and notices use the status colour at 10–15% behind its light text tint (e.g. Alarm Red at 15% under Alarm Red Text). Solid fills are kept for buttons, the 3px state bar, the 6–10px dots and the sidebar's open-incident count.

**The Name Beside The Colour Rule.** Every status colour carries its word: "COD ROȘU", "Preluat", "Rezolvat", "De serviciu", "Activă". Colour alone never carries a state.

**The Readable Grey Rule.** Text is never dimmer than Muted Text. Faint Text and Strong Rule are for borders, dots and icons only.

## Typography

**Display Font:** Archivo (with system-ui, sans-serif)
**Body Font:** Archivo (with system-ui, sans-serif)
**Label/Mono Font:** JetBrains Mono (with ui-monospace, monospace)

**Character:** Archivo at heavy weights gives titles and button labels a blunt, poster-like weight at small sizes; JetBrains Mono makes every id, time and count line up and read as data. Both are self-hosted variable fonts, cut to Latin and Romanian.

### Hierarchy
- **Brand** (800, 19px, line-height 1, -0.015em, uppercase): the ECHOCARE wordmark only.
- **Headline** (800, 22px, 1.1, -0.015em): the page title in the page header and on the sign-in card. A dossier's senior name takes the same style at 24px.
- **Title** (600, 15px, 1.25): the senior's name on an incident or enrollment card. Section headings beside a list or form are 800 at 15px; board column headers are 800 at 14px; names in tables and lists are 600 at 13.5–14px.
- **Body** (400, 13px, 1.45): everything else. Buttons are 800 at 13px.
- **Label** (600, 11px, 0.08em, uppercase): field labels and table column headers, in Muted Text.
- **Data** (JetBrains Mono 400, 11.5px, tabular): incident ids, times, phone numbers; counts are 600 at 11px.

### Named Rules
**The Mono Means Data Rule.** Ids, times, phone numbers and counts are set in JetBrains Mono; words are never set in it.

**The Heavy Label Rule.** Actions and titles carry weight through 800, not through size. The type scale stays small (11–22px).

## Layout

Desktop only. The dashboard is designed for desktop browser windows 1280px and wider, and must still hold at 1024px (a half-width window or a small laptop). Phones and tablets are not a target: dispatchers away from the desk use the Android app. The code stacks the sidebar above the page below the `md` breakpoint (768px); that is a fallback, not a supported layout, and needs no design work.

A fixed 240px sidebar beside a full-height workspace (`240px | 1fr`). The page header has 20px side padding, the 22px title and the on-duty chip on one row, then the page's tabs and search over a 2px rule. The incident board is three equal columns with 12px gaps inside 16px padding, each column scrolling on its own. The slide-over dossier is 540px wide from the right edge, so the board stays in place behind it.

Spacing steps by 4px: 4, 8, 12, 16, 20. Inside a card, 5px between lines and 10–12px padding; between cards, 8px. List rows are 12px tall in padding with 20px sides, divided by 1px rules.

### Page patterns
- **Board (Dispecerat Incidente, `/`):** Panou and Tabel underline tabs with a search field on the header's rule; three columns (Deschise, În lucru, Rezolvate) of incident cards, or one table of the same incidents.
- **Table (Monitorizare Seniori, `/seniors`):** enrollment filter tabs with a dot and mono count each (Toți, Activi, În înrolare, Necesită atenție), search, Exportă CSV and a square refresh button in the header; a full-width table; a footer bar over a 2px rule with "Afișez N din M seniori" and the last update time in mono.
- **Queue (Cereri de înrolare, `/enrollments`):** one column of request cards, at most 896px wide, oldest first, each expanding in place to the registration details.
- **List and form (Personal `/staff`, Campanii meteo `/campaigns`):** a scrolling list on the left and a fixed 360px form on the right, split by a 2px rule.
- **Sign-in:** one 384px panel centred on Night Canvas, Panel Graphite with a 2px Rule Grey border and 24px padding: the brand, a 2px rule, the headline, then one field and one button per step.
- **Dossiers:** the incident dossier and the senior dossier are both 540px slide-overs.

### Named Rules
**The Never Leave The Board Rule.** Details open in the slide-over above the current page; a dispatcher never navigates away from incidents to see one.

## Elevation & Depth

Flat. Depth is tonal: Night Canvas, then Panel Graphite, then Card Graphite rise in steps of lightness, and inputs sink to Deep Inset. Borders and 2px rules do the separating that shadows would do elsewhere.

### Shadow Vocabulary
- **Slide-over cast** (`box-shadow: -24px 0 48px rgba(1,4,9,.55)`): the dossier panel only, cast to the left over the page.
- **Health glow** (`box-shadow: 0 0 8px rgba(63,185,80,.7)`): the 8px green system-health dot when the API is up.

### Named Rules
**The One Shadow Rule.** Only the slide-over casts a shadow. Cards, buttons, menus and banners stay flat.

## Shapes

Square everywhere: cards, buttons, inputs, chips, badges, avatars, the sound switch and its knob, the status dots (0px radius, DaisyUI's radii set to 0 too). Borders are 1px Rule Grey around items and 2px Rule Grey between regions (sidebar edge, header base, section dividers, the slide-over's left edge). The one recurring silhouette is the incident card's 3px vertical state bar on its left edge.

## Components

### Buttons
Compact and exact: small, bordered, heavy, label flush left.
- **Shape:** square (0px), 1px Rule Grey border, 6px × 12px padding, 6px gap to an icon, 800 at 13px, no wrapping.
- **Default:** Card Graphite with Paper White text; hover lifts the border to Muted Text.
- **Danger (Preiau, Preiau cazul):** Alarm Red Strong fill, Alarm Red border, white text, zap icon; hover moves to Alarm Red Hover.
- **Success:** All-Clear Green Strong fill, All-Clear Green border, white text; hover to All-Clear Green Hover.
- **Link (Rezolvă cazul, Apelează):** Signal Blue text on Card Graphite; hover takes a Signal Blue border and a 15% blue wash.
- **Outline (Vezi dosar):** transparent with a Strong Rule border; hover turns the border Paper White.
- **Disabled:** 45% opacity, not-allowed cursor.
- **Focus:** the global 2px Signal Blue outline at 2px offset.
- **Sizes:** 30px tall in the page header (12.5px label), 26–28px in table rows and copy rows (12px), 34px for a dossier's call actions, 36px for a form's submit, 40px full width for Finalizează și arhivează incidentul. A square 30px button holds a lone icon (refresh, close, sign out) with an aria-label.
- **Copy button:** a default button in 600 Soft Text with a copy icon; its border and text turn Signal Blue and Paper White on hover; the label changes to "Copiat", or "Nu s-a copiat" in Alarm Red Text.

### Tabs
- **Underline tabs:** 600 labels with a 14px icon or a status dot and a mono count, 8px × 12px padding, sitting on the header's 2px rule; the active tab takes a 2px Signal Blue underline and Paper White, the rest are Muted Text. Used for Panou/Tabel, the seniors' enrollment filter and the dossier's sections (each with a mono number in Muted Text).

### Segmented Control
- **Style:** a row of equal options inside one 1px Rule Grey border, split by 1px rules, 7px × 12px padding, 13px. The chosen option takes a 15% Signal Blue wash and 600 Paper White; the rest are Soft Text with a Card Graphite hover. A native radio hides inside each, so focus shows as the 2px Signal Blue outline on the option. Used for Medic/DAS on Personal and heat/cold and yellow/red on Campanii.

### Outcome List
- **Style:** a vertical radio list in one 1px border, rows split by 1px rules, 9px × 12px padding: a 14px square marker (2px Strong Rule border, filled Signal Blue when chosen), the Romanian label, and the API value right-aligned in 11px mono Muted Text. The chosen row takes a 12% Signal Blue wash. Used for the incident outcome in the resolve form.

### Chips
- **Style:** square, 15% code colour behind its text tint, 11–12px at 600, 2–3px × 7–9px padding. Muted chips use Rule Grey behind Soft Text.
- **State:** incident state chips (Nepreluat, Transferat la DAS, Preluat, Rezolvat), code chips (Cod roșu, Cod galben, Cod verde), enrollment chips (Cerere trimisă, Activ, Nu răspunde…), duty chips (De serviciu, Liber) and campaign chips (Activă, Încheiată). Code, enrollment and duty chips lead with a 6–7px square dot in the solid colour; duty and campaign chips are uppercase at 0.06em.
- **Count chips:** campaign progress shows one chip per bucket, the number in mono before its word (12 verde, 3 galben, 1 roșu, waiting and cancelled in muted).
- **Tags:** neutral facts such as role (Medic, DAS) sit on Rule Grey in Soft Text; the line type (FIX, MOBIL) is a 9.5–10px uppercase tag, outlined in 1px Rule Grey on the seniors table and bare in Muted Text beside a phone number elsewhere.

### Cards / Containers
- **Corner Style:** square (0px).
- **Background:** Card Graphite on a Panel Graphite column.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px Rule Grey; Signal Blue on hover.
- **Internal Padding:** 10px top, 12px sides and bottom; a 1px rule above the action row.
- **Enrollment request card:** the same card with a Signal Blue state bar, the name and form of address with the number in mono, Vezi cererea (link) and Acceptă (success) on the right. Opening it adds a 1px rule and two columns: label/value rows on a 130px label column, and the caregivers list.
- **Framed panel:** a 1px Rule Grey box on Night Canvas with 16px padding holds the take action in the dossier's resolve tab. The archived result sits in a 1px All-Clear Green box on a 10% green wash.

### Tables and Lists
- **Header row:** sticky, Panel Graphite, the uppercase Label style, 9px × 12px cells, a 2px Rule Grey rule under it.
- **Rows:** 1px Rule Grey between rows, 8–10px × 12px cells, cells divided by 1px Card Graphite lines; the row fills Panel Graphite on hover. Ids and phone numbers in mono, names 600 over the form of address in Muted Text, the action last (Vezi dosar, link button).
- **List rows (Personal, Campanii):** full-width rows with 12px × 20px padding over 1px rules. A staff row is a 34px square initials avatar on Rule Grey, the name over the mono phone and role tags, and the duty chip on the right. A campaign row is the kind and level, the Activă/Încheiată chip and Încheie (danger) on the right, a line of who started it and until when in mono, then the progress count chips.
- **Label/value rows (dossiers, requests):** a 150px uppercase label column, the value beside it, 14px vertical padding, 1px rules between.
- **Transcript:** each call opens with a 2px-ruled line of mono time and duration and a summary in Soft Text, then turns on a 70px mono timestamp column with the speaker in the Label style (senior in Muted Text, agent in Signal Blue). A rule match breaks out as a full-width Card Graphite strip with its severity label in the status colour, the quote in Romanian quotation marks, and the reason in Soft Text.

### Notices and Empty States
- **Notices:** a 1px border in the status colour over its 10–15% wash, 8–12px × 16px padding, text in its light tint, with `role="alert"` (or `status` for success). Red when a load failed, amber when the shown data is stale because the last re-read failed, green when an action succeeded.
- **Inline errors and confirmations:** under a form or a card, a bare line in Alarm Red Text or All-Clear Green Text.
- **Loading:** a DaisyUI spinner and a Muted Text line ("Se încarcă…") that only fade in after 150ms of a 200ms delay, so quick loads never flash.
- **Empty:** one Muted Text sentence in the list's own padding ("Nicio cerere în așteptare.", "Niciun rezultat." when a search finds nothing).

### Inputs / Fields
- **Style:** Deep Inset background, 1px Rule Grey border, square, 32px tall for search, mono 12px text, Muted Text placeholder.
- **Focus:** the border turns Signal Blue; no outline ring.

### Navigation
- **Style:** the sidebar list, 13px Archivo with a 15px icon and a mono count badge pushed right.
- **Default:** Soft Text, transparent 1px border, Muted Text icon; hover fills Card Graphite.
- **Active:** Card Graphite fill, Rule Grey border, 600 Paper White text, Signal Blue icon (Alarm Red on Incidente).
- **Count badge:** Rule Grey behind Soft Text; on Incidente with any open incident, Alarm Red Strong behind white.

### Incident Card (signature)
The unit of the board. A 3px state bar on the left (Alarm Red open, Caution Amber in progress, All-Clear Green resolved), then: mono id · relative time and a state chip (the time never breaks: in a narrow column the id shortens with an ellipsis first, then the chip moves to its own line); the senior's name as a 15px title with the form of address in Muted Text; the reason, in Alarm Red Text while open; a 1px rule; the one action for the state (Preiau, Rezolvă cazul, or the Rezolvat chip) and who has it. The whole card opens the dossier.

### Cod Roșu Banner (signature)
Above every page while any incident is open: a 20% Alarm Red Strong wash with a 2px Alarm Red bottom rule, a 10px square red dot that pulses (1.1s, opacity 1 to 0.2) while sound alerts are on, "COD ROȘU" in 800 tracked 0.06em Alarm Red Text, the senior and reason, how long it has been open, and Preiau cazul plus Vezi dosar.

The same bar, with an alert icon in place of the dot and "ATENȚIE:" as its label, tops Personal when nobody is on duty.

### Slide-over Dossier
540px Panel Graphite panel from the right with a 2px Rule Grey left edge and the slide-over cast. The header, over a 2px rule: the mono id, state and code chips and a square close button; the senior's name at 24px with the form of address; for an incident, the COD ROȘU reason in an outlined red chip, then the address with copy buttons for the address, intercom code and GPS, and Preiau cazul and Apelează senior. Underline tabs (Urgență & acces, Transcriere apel, Eveniment, Rezolvare caz) sit on a second 2px rule, and the body scrolls under them with 20px sides. The senior dossier has no tabs: the senior's phone, the caregivers and the family doctor in label/value rows.

### Page Header
The page title (Headline) with the on-duty chip beside it ("1 dispecer de serviciu" in green, "Nimeni de serviciu" in red) and the page's actions pushed right; underneath, the page's tabs and search; a 2px Rule Grey rule closes it. 20px side padding, 18px on top.

### Sidebar Footer
Over a 2px rule: the Alerte sonore switch (a square 30 × 16px track, Off Grey when off and All-Clear Green Strong when on, with a 12px square Paper White knob and the word Active/Oprite in mono), then the dispatcher's initials square, the word Dispecer over their name, and a square sign-out button.

## Do's and Don'ts

### Do:
- **Do** take every colour from the tokens in `dashboard/src/styles.css`; use `rosu`, `galben` and `verde` only for status: alarm, caution, clear.
- **Do** keep every corner square (0px) and every region divider 2px Rule Grey.
- **Do** set ids, times, phone numbers and counts in JetBrains Mono.
- **Do** use `sn-btn` and its variants for buttons, with the label flush left at 800.
- **Do** write a code's name next to its colour wherever it appears.
- **Do** open details in the 540px slide-over over the current page.

### Don't:
- **Don't** round corners, even on pills, badges or avatars.
- **Don't** use red, amber or green for anything that is not a status, and never swap their meanings: green is never a warning, red is never a success.
- **Don't** add shadows outside the slide-over.
- **Don't** add a light theme or a second accent colour.
- **Don't** pulse or flash anything but a red alarm dot: the banner's (only while sound alerts are on) and the system-health dot when the API is down.
