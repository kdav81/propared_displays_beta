# Propared Calendar Displays

A web-based room display system for the University of Delaware's Department of Theatre and Dance. Raspberry Pi screens mounted outside rooms show live calendar information pulled from Propared iCal feeds. A companion print tool generates formatted PDF calendars from the same data.

---

## What it does

| Component | Description |
|---|---|
| **Room Displays** | Raspberry Pi kiosks running Chromium show a live calendar for one room — current event, upcoming events, and an optional photo slideshow |
| **Admin Panel** | Web interface to manage rooms, clients, global calendars, slideshow settings, media access, and backups |
| **Print Calendar** | Generates printable PDF calendars from Propared iCal feeds |
| **Notice Board** | Posts an emergency/info banner across all room displays instantly |
| **Office Dashboard** | A combined view of all rooms plus an embedded calendar, for a lobby or office screen |

---

## Architecture

```
                  ┌─────────────────────────────────┐
                  │   Oracle Cloud VM (Ubuntu 22.04) │
                  │   Flask/Waitress backend         │
                  │   ~/propared-display/            │
                  └──────────────┬──────────────────┘
                                 │ HTTP / HTTPS
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
   ┌──────▼──────┐       ┌───────▼──────┐      ┌───────▼──────┐
   │  Pi Zero W2 │       │    Pi 4/5    │  ...  │   Browser    │
   │  Room kiosk │       │  Room kiosk  │       │  Admin/Print │
   └─────────────┘       └─────────────┘        └─────────────┘
```

- **Server** — Flask app launched from `server.py`, with routes and services split into the `app/` package; Oracle HTTPS installs typically place Nginx in front as a reverse proxy
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

### Client install/update from GitHub

For Raspberry Pi display clients, you can pull the installer directly from GitHub instead of copying it by thumbdrive:

```bash
# Production client installer
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/main/install-client.sh
bash install-client.sh
```

```bash
# Testing/sandbox client installer
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/testing/install-client.sh
bash install-client.sh
```

The script will prompt for the server address or full URL (`http://` or `https://`) and can be safely re-run on an existing Pi to update it, switch it to HTTPS, or repoint it at a different server while keeping the same Client ID.

---

## Repository Layout

| Path | What it is actually for |
|---|---|
| `server.py` | Thin Flask entrypoint that wires together routes, services, and startup |
| `app/routes/` | Route modules for admin, display, media, notice, and print tools |
| `app/services/` | Shared logic for iCal caching, display state, media handling, and backups |
| `app/storage.py` / `app/config.py` / `app/auth.py` | Persistence helpers, path/default settings, and auth decorators |
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

The repo keeps only the current branch-based installers: `install-server.sh`, `install-server-testing.sh`, and `install-client.sh`.

### Runtime data files

These are created or maintained on the server and are not the main source code:

| Path | Purpose |
|---|---|
| `rooms.json` | Room definitions and room display settings |
| `clients.json` | Registered Raspberry Pi clients and their assignments |
| `tag_colors.json` | Tag color and full-name mappings used by displays and weekly print calendars |
| `settings.json` | Global display and dashboard settings |
| `media_library.json` | Slideshow media metadata including scheduling and active state |
| `print_shows.json` | Production definitions and iCal feeds for print calendars |
| `location_rules.json` | Location cleanup rules used by print calendar generation |
| `notice.json` | Current notice-board message state |
| `admin_password.txt` | Admin panel password hash |
| `notice_password.txt` | Shared password hash used by Notice and Media Library |
| `print_admin_password.txt` | Separate password hash used by Print Admin |
| `secret_key.txt` | Persistent Flask secret key so sessions survive restarts |
| `static/site_logo.*` | Optional landing-page logo uploaded from the Media Library |

---

## Pages at a glance

| URL | Who uses it |
|---|---|
| `/admin` | Admin — manage rooms, clients, settings |
| `/admin/setup` | First-run admin password setup |
| `/` | Landing page — front door with links to the main tools |
| `/media-admin` | Shared-password media library for slideshow uploads, scheduling, and landing-page logo updates |
| `/print-calendar` | Users — generate PDF production calendars or room schedules |
| `/print-admin` | Protected page for managing productions and location rules |
| `/print-admin/setup` | First-run Print Admin password setup |
| `/notice` | Shared-password notice board for posting a banner to all room displays |
| `/dashboard` | Lobby/office screen |
| `/display?room=ROOM_ID` | Pi kiosks (set automatically) |
