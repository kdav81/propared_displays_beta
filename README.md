# Propared Calendar Displays

A web-based room display system for the University of Delaware's Department of Theatre and Dance. Raspberry Pi screens mounted outside rooms show live calendar information pulled from Propared iCal feeds. A companion print tool generates formatted PDF calendars from the same data.

---

## What it does

| Component | Description |
|---|---|
| **Room Displays** | Raspberry Pi kiosks running Chromium show a live calendar for one room — current event, upcoming events, and an optional photo slideshow |
| **Admin Panel** | Web interface to manage rooms, clients, global calendars, slideshow settings, and backups |
| **Print Calendar** | Generates printable PDF calendars from Propared iCal feeds |
| **Notice Board** | Posts an emergency/info banner across all room displays instantly |
| **Office Dashboard** | A combined view of all rooms plus an embedded calendar, for a lobby or office screen |

---

## Architecture

```
                  ┌─────────────────────────────────┐
                  │   Oracle Cloud VM (Ubuntu 22.04) │
                  │   Flask/Waitress on port 80      │
                  │   ~/propared-display/            │
                  └──────────────┬──────────────────┘
                                 │ HTTP
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
   ┌──────▼──────┐       ┌───────▼──────┐      ┌───────▼──────┐
   │  Pi Zero W2 │       │    Pi 4/5    │  ...  │   Browser    │
   │  Room kiosk │       │  Room kiosk  │       │  Admin/Print │
   └─────────────┘       └─────────────┘        └─────────────┘
```

- **Server** — single Python file (`server.py`) running as a systemd service, pulling iCal data in the background
- **Clients** — Raspberry Pis running Chromium in kiosk mode via LightDM, auto-starting on boot
- **Data** — stored as JSON files on the server; no database required

---

## Branches

| Branch | Purpose |
|---|---|
| `main` | Production — what the live displays run |
| `testing` | Sandbox — test changes on a separate VM before promoting |

---

## Quick links

- **[SETUP.md](SETUP.md)** — Install the server and set up Raspberry Pi clients
- **[ADMIN.md](ADMIN.md)** — Day-to-day guide: managing rooms, productions, backups, notices

---

## Pages at a glance

| URL | Who uses it |
|---|---|
| `/admin` | Admin — manage rooms, clients, settings |
| `/print-calendar` | Admin — generate PDF rehearsal calendars |
| `/print-admin` | Admin — manage productions and location rules |
| `/notice` | Admin — post a notice banner to all displays |
| `/dashboard` | Lobby/office screen |
| `/display?room=ROOM_ID` | Pi kiosks (set automatically) |
