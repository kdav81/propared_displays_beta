# Setup Guide

This guide covers installing the server on Oracle Cloud and setting up Raspberry Pi display clients. For day-to-day administration see [ADMIN.md](ADMIN.md).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Oracle Cloud — Security Rules](#2-oracle-cloud--security-rules)
3. [Server Installation](#3-server-installation)
4. [First-Time Configuration](#4-first-time-configuration)
5. [Raspberry Pi Client Setup](#5-raspberry-pi-client-setup)
6. [Assigning Rooms to Displays](#6-assigning-rooms-to-displays)
7. [Updating the Server](#7-updating-the-server)
8. [Useful Server Commands](#8-useful-server-commands)
9. [Testing Branch](#9-testing-branch)

---

## 1. Prerequisites

### Server
- Oracle Cloud Free Tier VM (Ubuntu 22.04)
- SSH access to the VM
- The VM's public IP address

### Raspberry Pi clients
- Raspberry Pi Zero W2, Pi 4, or Pi 5
- Raspberry Pi OS **Lite** (64-bit, Debian Trixie/Bookworm) — a fresh flash is recommended
- A display connected via micro HDMI
- Wi-Fi or ethernet configured and working

---

## 2. Oracle Cloud — Security Rules

Before installing, make sure port 80 is open in the Oracle Cloud console. The install script handles the Linux firewall (`iptables`) automatically, but Oracle's cloud firewall (Security List) must be configured manually.

1. Log into [cloud.oracle.com](https://cloud.oracle.com)
2. Go to **Networking → Virtual Cloud Networks → your VCN → Security Lists**
3. Edit the **Default Security List** and add an **Ingress Rule**:

| Field | Value |
|---|---|
| Source CIDR | `0.0.0.0/0` |
| IP Protocol | TCP |
| Destination Port | `80` |

> If you plan to add HTTPS later, add a second rule for port `443`.

---

## 3. Server Installation

### Fresh install (production)

SSH into your Oracle Cloud VM:

```bash
ssh ubuntu@YOUR_SERVER_IP
```

Download and run the installer:

```bash
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/main/install-server.sh
bash install-server.sh
```

The script will:
- Install Python, git, and authbind
- Set the timezone to `America/New_York`
- Clone the repository to `~/propared-display/`
- Create a Python virtual environment and install dependencies
- Open ports 80 and 443 in the Linux firewall
- Create and start a `systemd` service (`propared-display`)
- Set up a nightly 3 AM restart
- Add convenience shell aliases

When it finishes, visit `http://YOUR_SERVER_IP/admin` — you should see the Admin panel.

### Install from the testing branch

```bash
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/testing/install-server-testing.sh
bash install-server-testing.sh
```

This installs identically but tracks the `testing` branch. Use this on a separate sandbox VM.

---

## 4. First-Time Configuration

After installing, do these steps in the Admin panel before setting up any Pi clients.

### Add rooms

1. Open `http://YOUR_SERVER_IP/admin`
2. In the **Rooms** section, click **+ Add Room**
3. Fill in:
   - **Display Title** — shown on the screen (e.g. "Rehearsal Hall A")
   - **Google Calendar iCal URL** — from Google Calendar Settings → your calendar → *Secret address in iCal format*
   - **Refresh Interval** — how often to check for new events (5 minutes is typical)
   - **Display Hours** — the screen only shows content during these hours
4. Click **Create Room**

Repeat for each room that needs a display.

### Configure tag colors (optional)

If your Propared events use `[TAGS]` in their titles (e.g. `Set Build [CREW]`), you can assign colors and full names to each tag. These appear as a legend on the display. Configure this in the **Tag Color & Name Mapping** section.

### Set up Dropbox slideshow (optional)

If you want photos to rotate between calendar views:

1. Expand the **Slideshow & Dropbox** section in Admin
2. Follow the four-step Dropbox setup wizard on that page
3. Set the **Photo Folder** path in your Dropbox (e.g. `/slideshow`)
4. Enable **Rotate to photo slideshow** on each room that should show photos

---

## 5. Raspberry Pi Client Setup

Do this for each Pi display. You will need a keyboard and monitor (or SSH access) for the initial setup.

### Flash the Pi

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Choose **Raspberry Pi OS Lite (64-bit)**
3. Before writing, use the Imager's settings gear to:
   - Set a hostname (e.g. `hallway-display`)
   - Enable SSH
   - Set your Wi-Fi network and password
4. Flash and boot the Pi

### Run the client installer

SSH into the Pi (or open a terminal):

```bash
ssh pi@hallway-display.local
```

Download and run the client installer:

```bash
curl -O http://YOUR_SERVER_IP/install-client.sh
bash install-client.sh
```

The installer will:
- Ask for your server's IP address and verify it can reach the server
- Detect whether you have a Pi 4/5 (with desktop) or Pi Zero W2 (minimal X install)
- Install Chromium and configure it to run in fullscreen kiosk mode
- Set up LightDM to auto-start the kiosk on boot
- Install a watchdog that sends a heartbeat to the server every 60 seconds and restarts Chromium if it crashes
- Add convenience shell aliases

When the installer finishes, Chromium will launch automatically and show a **"Waiting for room assignment"** screen. The Pi is now registered with the server.

> **Re-running the installer** is safe — it reads your existing config and offers to keep or change the server address.

---

## 6. Assigning Rooms to Displays

Once a Pi has run the installer and checked in, it appears in the **Clients** section of the Admin panel.

1. Open `/admin` → **Clients**
2. Find the Pi by hostname
3. Click **Edit** and select a room from the dropdown
4. Optionally set a screen schedule (on/off times)
5. Click **Save**

The Pi will pick up the new assignment within 60 seconds (next watchdog cycle) and start displaying that room's calendar.

---

## 7. Updating the Server

After code changes are pushed to GitHub, update the running server without a full reinstall:

```bash
display-update
```

*(This alias is added to your shell by the installer. If it's not available yet, run `source ~/.bashrc` first.)*

Or run it directly:

```bash
bash ~/propared-display/install-server.sh --update
```

This pulls the latest code from GitHub, updates Python packages, and restarts the service. All room data, settings, and backups are preserved.

---

## 8. Useful Server Commands

These aliases are added to `~/.bashrc` by the installer:

| Command | What it does |
|---|---|
| `display-logs` | Stream live server logs |
| `display-restart` | Restart the server service |
| `display-stop` | Stop the server |
| `display-status` | Show service status |
| `display-update` | Pull latest code from GitHub and restart |

### Useful Pi commands

| Command | What it does |
|---|---|
| `kiosk-restart` | Restart the kiosk (restart LightDM) |
| `kiosk-logs` | Stream watchdog logs |
| `screen-on` | Turn the display on manually |
| `screen-off` | Turn the display off manually |
| `client-log` | Show the last kiosk session log |
| `client-id` | Print this Pi's Client ID |

---

## 9. Testing Branch

The `testing` branch is an identical copy of `main` used for safely testing changes before pushing to production.

### Workflow

1. Make changes in the `testing` branch
2. Deploy to your sandbox VM using `install-server-testing.sh`
3. Test thoroughly
4. Merge `testing` into `main` via a GitHub pull request
5. Run `display-update` on the production VM

### Promoting to production

```bash
# On your local machine
git checkout main
git merge testing
git push origin main

# Then on the production server
display-update
```
