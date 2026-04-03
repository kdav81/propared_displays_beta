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

## Repository Layout

| Path | What it is actually for |
|---|---|
| `server.py` | Main Flask application: admin routes, room display APIs, print-calendar routes, notice system, client check-ins, backups |
| `print_calendar_pdf.py` | ReportLab PDF renderer for production and room calendars, both monthly and weekly |
| `templates/` | Jinja templates for admin, room displays, dashboard, notice page, and print-calendar tools |
| `static/admin/` | Shared admin CSS and JavaScript used by the admin and print pages |
| `install-server.sh` | Production server installer for the live `main` branch deployment |
| `install-server-testing.sh` | Testing/sandbox server installer for the `testing` branch deployment |
| `install-client.sh` | Raspberry Pi kiosk installer for room display clients |
| `ADMIN.md` | Day-to-day operational guide for admin tasks |
| `SETUP.md` | Full installation and deployment guide |
| `README.md` | Project overview, branch purpose, URLs, and repository map |
| `requirements.txt` | Python dependencies for the server and PDF generation |
| `.gitignore` | Ignores generated data, secrets, caches, and local-only files |
| `.gitattributes` | Normalizes line endings for cross-platform editing and deployment |

### Runtime data files

These are created or maintained on the server and are not the main source code:

| Path | Purpose |
|---|---|
| `rooms.json` | Room definitions and room display settings |
| `clients.json` | Registered Raspberry Pi clients and their assignments |
| `tag_colors.json` | Tag color and full-name mappings used by displays and weekly print calendars |
| `settings.json` | Global display, dashboard, and Dropbox settings |
| `print_shows.json` | Production definitions and iCal feeds for print calendars |
| `location_rules.json` | Location cleanup rules used by print calendar generation |
| `notice.json` | Current notice-board message state |
| `admin_password.txt` / `notice_password.txt` / `secret_key.txt` | Local secrets and auth data |

---

## Pages at a glance

| URL | Who uses it |
|---|---|
| `/admin` | Admin — manage rooms, clients, settings |
| `/print-calendar` | Admin — generate PDF production calendars or room schedules |
| `/print-admin` | Admin — manage productions and location rules |
| `/notice` | Admin — post a notice banner to all displays |
| `/dashboard` | Lobby/office screen |
| `/display?room=ROOM_ID` | Pi kiosks (set automatically) |
