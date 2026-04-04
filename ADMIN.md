# Admin Guide

Day-to-day reference for managing Propared Calendar Displays. For initial installation see [SETUP.md](SETUP.md).

---

## Table of Contents

1. [Admin Panel Overview](#1-admin-panel-overview)
2. [Rooms](#2-rooms)
3. [Tag Colors](#3-tag-colors)
4. [Clients (Pi Displays)](#4-clients-pi-displays)
5. [Global Calendars](#5-global-calendars)
6. [Office Dashboard](#6-office-dashboard)
7. [Slideshow](#7-slideshow)
8. [Backup & Restore](#8-backup--restore)
9. [Print Calendar](#9-print-calendar)
10. [Print Admin — Productions & Location Rules](#10-print-admin--productions--location-rules)
11. [Notice Board](#11-notice-board)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Admin Panel Overview

Open `http://YOUR_SERVER_IP/admin` in any browser.

The page is divided into collapsible sections. Click any section header to expand or collapse it. The system remembers which sections you left open or closed.

**Sections that start collapsed** (set-once settings you rarely change):
- Global Calendars
- Office Dashboard
- Slideshow
- Backup & Restore

**Sections that start expanded** (things you use regularly):
- Rooms
- Tag Colors
- Clients

Navigation buttons at the top right link to Print Calendar, Print Admin, and the Notice Board.

---

## 2. Rooms

Each room corresponds to one physical display screen. Rooms pull from a Propared iCal feed.

### Adding a room

1. In the **Rooms** section, click the **+** card (or click **Add Room**)
2. Fill in the form:
   - **Display Title** — what appears as the header on the screen (e.g. "Rehearsal Hall A")
   - **Propared iCal URL** — the webcal or iCal feed URL from your Propared production. In Propared, go to the production's settings and copy the iCal/webcal feed link
   - **Refresh Interval** — how often (in minutes) the server checks for new events. 5 minutes is recommended
   - **Start / End Hour** — the display only shows the calendar during these hours. Outside these hours the screen goes to a minimal state
   - **Rotate to photo slideshow** — if checked, the display alternates between the calendar and images from the shared server media library
   - **Logo** — optional image shown in the top-right corner of the display

### Editing a room

Click **Edit** on the room card. All fields can be changed, including replacing or removing the logo.

### Deleting a room

Click **Delete** on the room card. You will be asked to confirm. This removes the room from all displays — any Pi assigned to this room will show the "waiting for assignment" screen until reassigned.

### Opening a display

Click **Open** on the room card to preview the display in a new browser tab. This is the same URL the Pi shows in kiosk mode.

---

## 3. Tag Colors

Tags are short labels added to Propared event titles in square brackets, e.g. `Tech Rehearsal [THTR]`.

The tag system lets you:
- Assign a color to each tag so events are color-coded on the display
- Map a short tag key to a full name shown in the legend (e.g. `THTR` → "Theatre Production")

### Managing tags

1. In the **Tag Color & Name Mapping** section, each row is one tag
2. Click the colored square to change the color (uses Propared's color palette)
3. Edit the **Tag Key** (must match exactly what's in the event title brackets)
4. Edit the **Full Name** — this is what appears in the legend at the bottom of the display
5. Click **+ Add Tag** to add a new one
6. Click **×** to remove a tag
7. Click **Save Tag Colors** when done

> Changes take effect on displays at the next refresh cycle (within 5 minutes by default).

---

## 4. Clients (Pi Displays)

Each Raspberry Pi registers itself with the server when the client installer runs. The Clients section shows all registered Pis and lets you assign them to rooms.

### What the columns mean

| Field | Description |
|---|---|
| **Hostname** | The Pi's network name (set during OS install) |
| **IP** | The Pi's local IP address |
| **Room** | Which room this Pi is currently displaying |
| **Last seen** | How long ago the Pi last checked in (green = online, red = offline) |

### Assigning a room

1. Click **Edit** next to the Pi
2. Select a room from the **Room** dropdown
3. Optionally enable a **Screen Schedule** — the display will turn itself on and off at the specified times
4. Click **Save**

The Pi picks up the new assignment within 60 seconds.

### Screen schedule

When enabled, the Pi will turn off its screen outside the scheduled hours and turn it back on automatically. This is separate from the room's *Display Hours* setting — the schedule controls the physical screen power, while Display Hours controls what the calendar shows.

---

## 5. Global Calendars

Global calendars are iCal feeds that appear on **every room display** (but not the dashboard). Use these for university-wide dates — holidays, important deadlines, building closures — that apply to all rooms.

Up to 3 global calendars can be added. Each gets its own color on the calendar grid and does **not** appear in the event sidebar.

### Adding a global calendar

1. Expand the **Global Calendars** section
2. Click **+ Add Calendar**
3. Enter the iCal URL and a label
4. Click **Save Global Calendars**

---

## 6. Office Dashboard

The dashboard (`/dashboard`) is a combined view designed for a lobby or office screen. It shows:
- A grid of all selected rooms with their current/upcoming events
- An embedded calendar iframe on the right side (any embeddable calendar URL)
- The same photo slideshow used by room displays

### Configuring the dashboard

Expand the **Office Dashboard** section in Admin:

- **Calendar Iframe URL** — any embeddable calendar URL. For example, in Google Calendar go to Settings → your calendar → *Embed code* and paste the URL from the `src=` attribute. This iframe is separate from Propared and can show any calendar you choose
- **Rooms to Show** — check which rooms appear on the dashboard. Drag the handles to reorder them
- **Timing** — how many seconds to show the calendar iframe before switching to the slideshow, and how long each photo shows

Click **Save Dashboard Settings** to apply. Click **Preview** to open the dashboard in a new tab.

---

## 7. Slideshow

The slideshow rotates photos between calendar views on room displays and the dashboard.

### Timing settings

- **Show Calendar (sec)** — how long the calendar is shown before switching to a photo
- **Show Photo (sec)** — how long each photo is shown

Click **Save Timing** after changing these.

### Media Library

Slideshow images are uploaded directly to the server through the **Media Library** page at `/media-admin`.

The Media Library uses the same shared password as the Notice page, so you can give someone limited slideshow access without giving them full Admin access.

Each media item can be:

- always available
- scheduled with a start date
- scheduled with an end date
- scheduled with both a start and end date
- disabled without being deleted

### Shared password

The first time you open `/media-admin`, you can set the shared Notice/Media password if it has not already been created through the Notice page.

After that:

- `/notice` and `/media-admin` use the same password
- `/admin` still uses its own separate admin password

---

## 8. Backup & Restore

Backups capture everything: rooms, tag colors, settings, logos, slideshow media, productions, location rules, and the shared Notice/Media password.

### Creating a backup

1. Expand **Backup & Restore**
2. Click **Download Backup**
3. A `.zip` file downloads to your computer. A copy is also saved on the server

**It's a good idea to download a backup before making major changes to rooms or settings.**

### Restoring a backup

1. Click **Restore**, choose the `.zip` file from your computer
2. Confirm the prompt — this will overwrite all current rooms, tags, and settings
3. The page will reload when the restore is complete

### Backups saved on the server

The **Saved on Server** section lists recent backups stored on the server itself. These are useful if you need to roll back without a local copy. Click **Refresh** to update the list.

---

## 9. Print Calendar

The print calendar tool at `/print-calendar` generates formatted PDFs from either:

- configured **productions** from Print Admin
- configured **rooms** from the main Admin page

The page only works with one source type at a time, so you choose either productions or rooms for each PDF.

### Generating a calendar

1. **Calendar Source** — choose **Productions** or **Rooms**
2. **Select item(s)** — check one or more productions or rooms. Drag to reorder if you want a specific order in a combined calendar title
3. **Calendar Type** — choose Monthly (one page per month) or Weekly (one page per week)
4. **Date Range** — set the start and end month/year (monthly) or specific dates (weekly)
5. **Calendar Options**:
   - **Calendar Subtitle** — shown in the header of every page (e.g. "Rehearsal Performance Calendar")
   - **Updated By** — your initials, shown in the header
   - **Apply location rules** — when checked, location names are substituted using the rules defined in Print Admin. Uncheck to show the raw original location from Propared
6. Click **Generate PDF** — the file downloads automatically and a preview appears below

### Production vs room behavior

| Mode | What it uses | Color behavior | Tag behavior |
|---|---|---|---|
| **Productions — Monthly** | Print Admin productions and their iCal feeds | Black-and-white friendly monthly layout | Production tags are handled the same way as before |
| **Productions — Weekly** | Print Admin productions and their iCal feeds | Colored event blocks using tag mappings | Multi-production weekly calendars can show tag prefixes/legends |
| **Rooms — Monthly** | Room feeds from the main Admin page | Black-and-white friendly monthly layout | Room tags stay visible as bracketed labels, but monthly output does not use color fills |
| **Rooms — Weekly** | Room feeds from the main Admin page | Colored event blocks using the same tag colors configured in Admin | Room tags stay visible so you can tell event types apart by both label and color |

### Default date behavior

- **Monthly calendars** default to the current month
- The default **end month** is two months after the current month
- **Weekly calendars** default to the current week through four weeks out

---

## 10. Print Admin — Productions & Location Rules

Open `/print-admin` to manage the data that feeds the Print Calendar.

### Productions

Each production is a named show with one or more Propared iCal feeds attached to it.

**Adding a production:**
1. Click **+ Add Production**
2. Fill in:
   - **Title** — full show name (e.g. "Vanya and Sonia and Masha and Spike")
   - **Short Title** — shown in the selector on the Print Calendar page
   - **Season** — optional (e.g. "REP 25-26 Season")
   - **Short Tag** — if your events don't have `[TAG]` brackets, this prefix is added automatically
   - **Propared iCal Feeds** — add one or more webcal/iCal URLs from Propared. Give each feed a label (e.g. "Main", "Crew")
3. Click **Save Production**

**Editing / deleting** a production: use the **Edit** or **Delete** buttons on the production card.

### Location Rules

Location rules automatically clean up and shorten verbose location strings from Propared. For example, "Memorial Hall 100 — Theatre and Dance Building" can be replaced with "Memorial Hall 100."

Rules are checked in order — the first matching rule wins.

**Adding a rule:**
1. Click **+ Add Rule**
2. Enter one or more **trigger keywords** (comma-separated, case-insensitive) — the rule fires if the event's location contains any of these words
3. Enter the **replacement text** — what the location will be changed to
4. Click **Save Rules**

**Example:**

| If location contains… | Replace with |
|---|---|
| `memorial hall` | `Memorial Hall 100` |
| `studio theatre, experimental` | `Studio Theatre` |
| `dance studio` | `Dance Studio` |

> You can toggle location rules on and off per PDF using the checkbox on the Print Calendar page — useful when you need to see the original location text.

---

## 11. Notice Board

The notice board at `/notice` posts an emergency or informational banner across **all room displays** immediately.

### Posting a notice

1. Open `/notice` (or click **Notice** in the top nav)
2. Enter your message
3. Optionally set a **Start** and **End** time — the notice will only display during this window
4. Check **Active — show on all displays now**
5. Click **Save & Post**
6. Click **Push to Displays** to force an immediate update without waiting for the next refresh

The notice banner appears in red at the top of every room display. Displays pick it up within 30 seconds automatically even without pushing.

### Clearing a notice

Click **Clear Notice** — this removes the message and unchecks the Active toggle.

---

## 12. Troubleshooting

### A Pi isn't showing the right room

- Check **Clients** in the Admin panel — confirm the room assignment is correct
- The Pi updates within 60 seconds. If it's been longer, SSH into the Pi and run `kiosk-restart`

### A Pi shows "Waiting for room assignment"

- The Pi is online but hasn't been assigned a room yet — go to **Clients** in Admin and assign it

### A Pi is offline in the Clients panel

- Check that the Pi is powered on and connected to Wi-Fi
- SSH in and run `kiosk-logs` to see what the watchdog is reporting
- Run `kiosk-restart` to restart the kiosk

### Events aren't updating on a display

- Check the room's **Refresh Interval** in Admin — iCal feeds are cached and update on a timer
- Verify the iCal URL is still valid: paste it into a browser. If it returns an error or empty data, check the feed settings in Propared

### The admin page is not loading

- SSH into the server and run `display-status` to check if the service is running
- Run `display-logs` to see recent errors
- If the service is stopped: `display-restart`

### The PDF calendar generates but locations look wrong

- Check **Location Rules** in Print Admin — make sure keywords match what's actually in your Propared locations
- On the Print Calendar page, uncheck **Apply location rules** to see the raw location text and identify what keywords to use
