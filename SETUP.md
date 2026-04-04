# Setup Guide

This guide covers everything from creating your server to installing Raspberry Pi display clients. For day-to-day administration see [ADMIN.md](ADMIN.md).

---

## Table of Contents

1. [What You Need](#1-what-you-need)
2. [Option A — Oracle Cloud Server (Recommended)](#2-option-a--oracle-cloud-server-recommended)
3. [Option B — Raspberry Pi as the Server (Local Network)](#3-option-b--raspberry-pi-as-the-server-local-network)
4. [Installing the Server Software](#4-installing-the-server-software)
5. [First-Time Configuration](#5-first-time-configuration)
6. [Setting Up Raspberry Pi Display Clients](#6-setting-up-raspberry-pi-display-clients)
7. [Assigning Rooms to Displays](#7-assigning-rooms-to-displays)
8. [Updating the Server](#8-updating-the-server)
9. [Useful Commands](#9-useful-commands)
10. [Testing Branch Workflow](#10-testing-branch-workflow)

---

## 1. What You Need

### Server options
Choose one:
- **Oracle Cloud Free Tier VM** — runs in the cloud, accessible from anywhere, recommended for most installs
- **Raspberry Pi 4 or 5** — runs locally on your network, no cloud account needed, good for a single building with no remote access requirement

### Display clients (one per room)
- Raspberry Pi Zero W2, Pi 4, or Pi 5
- MicroSD card (16 GB or larger, Class 10)
- HDMI display + appropriate cable (micro HDMI for Pi Zero W2 and Pi 4, mini HDMI for Pi 5)
- USB power supply (5V/2.5A minimum for Zero W2, 5V/3A for Pi 4/5)
- Wi-Fi access in each room, or a wired ethernet adapter

### Your computer (for setup)
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installed
- An SSH client — Terminal (Mac/Linux) or PuTTY / Windows Terminal (Windows)

---

## 2. Option A — Oracle Cloud Server (Recommended)

Oracle Cloud Free Tier gives you a VM that runs 24/7 at no cost. It is reachable over the internet so you can manage displays from anywhere.

### 2a. Create a free Oracle Cloud account

1. Go to [cloud.oracle.com](https://cloud.oracle.com) and click **Start for free**
2. Complete the sign-up — a credit card is required for verification but the free tier is not charged
3. Choose a **Home Region** closest to you (e.g. US East - Ashburn). **You cannot change this later**

### 2b. Create the VM instance

1. From the Oracle Cloud console, click the hamburger menu → **Compute → Instances → Create Instance**
2. Give it a name (e.g. `propared-display-server`)
3. Under **Image and shape**, click **Change image** and select:
   - **Ubuntu 22.04** (Canonical Ubuntu)
4. Under **Shape**, the default `VM.Standard.E2.1.Micro` (1 OCPU, 1 GB RAM) is fine for up to ~10 displays. For larger installs use `VM.Standard.A1.Flex` (ARM, also free tier eligible, up to 4 OCPUs / 24 GB RAM)
5. Under **Add SSH keys** — this is how you connect to the server:
   - If you already have an SSH key pair: select **Upload public key file** and upload your `.pub` file
   - If you don't have one: select **Generate a key pair for me**, download both files, and keep the private key safe
6. Leave everything else as default and click **Create**

The instance will take about 2 minutes to start. You'll see it listed as **Running** when ready.

### 2c. Find your public IP address

On the instance detail page, look for **Public IP address** — this is the address you'll use for everything. Write it down.

### 2d. Open port 80 in the Oracle Cloud firewall

Oracle Cloud has its own firewall (called a Security List) on top of the Linux firewall. You must open port 80 here or the displays won't be able to reach the server.

1. On the instance detail page, scroll to **Primary VNIC** and click the **Subnet** link
2. Click **Default Security List**
3. Click **Add Ingress Rules** and fill in:

   | Field | Value |
   |---|---|
   | Source Type | CIDR |
   | Source CIDR | `0.0.0.0/0` |
   | IP Protocol | TCP |
   | Destination Port Range | `80` |

4. Click **Add Ingress Rules** to save

> If you ever add HTTPS, repeat with port `443`.

### 2e. Connect to your VM

Open a terminal and connect:

```bash
ssh -i /path/to/your/private-key.pem ubuntu@YOUR_PUBLIC_IP
```

On Windows with PuTTY: enter `ubuntu@YOUR_PUBLIC_IP` as the host and load your `.ppk` private key under Connection → SSH → Auth.

If you get a permissions error on the key file (Mac/Linux):
```bash
chmod 400 /path/to/your/private-key.pem
```

Once you're connected, continue to [Section 4 — Installing the Server Software](#4-installing-the-server-software).

---

## 3. Option B — Raspberry Pi as the Server (Local Network)

Use this option if you want to run everything on your local network without a cloud account. The server Pi must be **always on** and connected to your network.

**Recommended hardware:** Raspberry Pi 4 (4 GB RAM) or Pi 5. The Pi Zero W2 does not have enough RAM to act as a server reliably.

### 3a. Flash the server Pi

1. Open **Raspberry Pi Imager**
2. Click **Choose Device** and select your Pi model
3. Click **Choose OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (64-bit)**
4. Click **Choose Storage** and select your SD card
5. Click the **gear icon** (or press Ctrl+Shift+X) to open advanced settings:
   - **Set hostname** — e.g. `propared-server`
   - **Enable SSH** — check this box
   - **Set username and password** — note these down
   - **Configure Wi-Fi** — enter your network name and password
   - Set your **locale and timezone**
6. Click **Save**, then **Write**

Insert the SD card, connect the Pi to power, and wait about 90 seconds for first boot.

### 3b. Find the Pi on your network

From your computer:
```bash
ssh pi@propared-server.local
```

If `.local` doesn't work, log into your router's admin page and look for the Pi's IP address in the connected devices list. Then use:
```bash
ssh pi@192.168.x.x
```

### 3c. Set a static IP address (strongly recommended)

A static IP ensures displays always know where to find the server. The easiest way is to assign a **DHCP reservation** (sometimes called a "static lease") in your router's admin panel using the Pi's MAC address. This keeps the IP fixed without configuring anything on the Pi itself.

Alternatively, on the Pi:
```bash
sudo nmcli con mod "$(nmcli -g NAME con show --active | head -1)" ipv4.method manual ipv4.addresses 192.168.1.50/24 ipv4.gateway 192.168.1.1 ipv4.dns 8.8.8.8
sudo nmcli con up "$(nmcli -g NAME con show --active | head -1)"
```

Replace the IP, gateway, and DNS with your network's values.

### 3d. Notes for local Pi server

- Displays must be on the **same network** as the server Pi, or on a network that can reach it
- The Admin panel and display URLs will use the Pi's local IP (e.g. `http://192.168.1.50/admin`)
- The server Pi must remain powered on whenever displays are in use
- Propared iCal feeds still require internet access — make sure the Pi has a working internet connection

Once you can SSH in, continue to [Section 4](#4-installing-the-server-software).

---

## 4. Installing the Server Software

Run this on whichever machine will be your server (Oracle Cloud VM or local Pi), after connecting via SSH.

### Installer script quick reference

| Script | Use it for |
|---|---|
| `install-server.sh` | Production installs and updates from the `main` branch |
| `install-server-testing.sh` | Sandbox/testing installs and updates from the `testing` branch |
| `install-client.sh` | Raspberry Pi room display clients |

The repo now keeps only these current installers, so older one-file legacy installers are no longer part of the normal setup path.

### Fresh install — production branch

```bash
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/main/install-server.sh
bash install-server.sh
```

### Fresh install — testing branch (sandbox VM only)

```bash
curl -O https://raw.githubusercontent.com/kdav81/propared_displays_beta/testing/install-server-testing.sh
bash install-server-testing.sh
```

### What the installer does

The script runs through these steps automatically:

1. **System packages** — installs Python 3, git, and authbind (lets the server run on port 80 without root)
2. **Timezone** — sets the server clock to `America/New_York`
3. **Downloads the app** — clones the GitHub repository to `~/propared-display/`
4. **Python environment** — creates a virtual environment and installs all dependencies
5. **Firewall** — opens ports 80 and 443 in the Linux firewall (iptables). Note: on Oracle Cloud you also need the Security List rule from Section 2d
6. **Systemd service** — creates `propared-display.service` so the server starts automatically on boot and restarts if it crashes
7. **Nightly restart** — schedules an automatic restart at 3 AM to keep things fresh
8. **Shell aliases** — adds convenience commands to your terminal (see Section 9)

When it finishes you'll see your server's IP and the Admin panel URL. Visit `http://YOUR_SERVER_IP/admin` — you should see the Admin panel.

> **If the page doesn't load on Oracle Cloud:** double-check that you added the Security List ingress rule for port 80 (Section 2d). The Linux firewall is handled by the installer but the Oracle cloud firewall is separate.

---

## 5. First-Time Configuration

Do these steps in the Admin panel before setting up any display clients.

### Add rooms

1. Open `http://YOUR_SERVER_IP/admin`
2. In the **Rooms** section, click the **+** card
3. Fill in:
   - **Display Title** — what appears as the room name on screen (e.g. "Rehearsal Hall A")
   - **Propared iCal URL** — the webcal or iCal feed URL from your Propared production. In Propared, go to the production's settings and copy the iCal feed link
   - **Refresh Interval** — how often the server checks for updated events (5 minutes recommended)
   - **Display Hours** — start and end hour; the display shows the calendar only during these hours
   - **Rotate to photo slideshow** — enable if this screen should alternate between the calendar and photos
4. Click **Create Room**

Repeat for each room.

### Configure tag colors (optional)

If your Propared events use `[TAG]` labels in their titles (e.g. `Tech Rehearsal [THTR]`), assign colors and full names to each tag in the **Tag Color & Name Mapping** section. These appear as a color-coded legend on every display. See [ADMIN.md](ADMIN.md#3-tag-colors) for details.

### Set up the slideshow media library (optional)

If you want room displays to show rotating photos between calendar views:

1. Open `/media-admin`
2. Set the shared Notice/Media password if prompted
3. Upload images directly to the server
4. Optionally set start and end dates for scheduled display

See [ADMIN.md](ADMIN.md#7-slideshow) for details.

---

## 6. Setting Up Raspberry Pi Display Clients

Do this for each Pi that will be a display. Each Pi becomes one room's kiosk.

### 6a. What you'll need per Pi

- Raspberry Pi Zero W2, Pi 4, or Pi 5
- MicroSD card (16 GB+, Class 10 or faster)
- Power supply
- HDMI display and cable
- Keyboard for initial setup (or SSH access if you configure Wi-Fi in the imager)

### 6b. Flash Raspberry Pi OS

1. Open **Raspberry Pi Imager** on your computer
2. Click **Choose Device** and select your Pi model
3. Click **Choose OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (64-bit)**

   > Use **Lite** — the full desktop version wastes resources and is not needed for a kiosk

4. Click **Choose Storage** and select your SD card
5. Click the **gear icon** (or Ctrl+Shift+X) to open advanced settings — **do this before writing**:
   - **Hostname** — give each Pi a unique name (e.g. `hallway-pi`, `studio-pi`, `lobby-pi`). This is how you'll identify them
   - **Enable SSH** — check this so you can manage the Pi remotely later
   - **Username and password** — set a username (default is `pi`) and a secure password
   - **Configure Wi-Fi** — enter your building's Wi-Fi network name and password. Make sure this is the same network the server is on (or can reach it)
   - **Locale** — set your timezone and keyboard layout
6. Click **Save** → **Write** → confirm the erase warning

Writing takes 2–5 minutes depending on your SD card speed.

### 6c. First boot

1. Insert the SD card into the Pi
2. Connect the HDMI display and power supply (connect display **before** power)
3. The Pi will boot — first boot takes about 60–90 seconds
4. Once booted, find the Pi on your network using its hostname:

```bash
# From your computer
ssh pi@hallway-pi.local
```

If `.local` doesn't resolve, check your router's device list for the Pi's IP and SSH to that directly:
```bash
ssh pi@192.168.1.x
```

### 6d. Run the client installer

Once SSH'd into the Pi:

```bash
curl -O http://YOUR_SERVER_IP/install-client.sh
bash install-client.sh
```

The installer will ask for your server's IP address, test the connection, and then run through setup automatically.

**What the installer does:**

1. **Detects your Pi model** — Pi 4/5 (with existing display manager) vs Pi Zero W2 (bare OS, installs minimal graphics stack)
2. **Prompts for server address** — enter your server's IP or hostname. The script verifies it can reach the server before continuing
3. **Registers the Pi** — assigns this Pi a permanent Client ID that appears in the Admin panel
4. **Installs packages** — Chromium browser, unclutter (hides the mouse cursor), and any missing graphics drivers
5. **Creates the kiosk launcher** — a script that starts Chromium in fullscreen mode pointing at the server
6. **Configures LightDM** — the display manager that starts automatically on boot and launches the kiosk session
7. **Installs the watchdog** — a background service that checks in with the server every 60 seconds and automatically restarts Chromium if it crashes
8. **Applies Pi-specific fixes** — GPU flags for Pi Zero W2, page size fix for Pi 5, disables screen blanking
9. **Adds shell aliases** — convenience commands for managing the kiosk
10. **Restarts LightDM** — Chromium launches immediately

When the installer finishes, Chromium should appear fullscreen on the connected display showing a **"Waiting for room assignment"** screen. This is correct — the Pi is registered and waiting to be assigned.

> **Safe to re-run:** if you need to reinstall or change the server address, just run the installer again. It reads your existing config and offers to keep or replace it.

### 6e. Pi Zero W2 — additional notes

The Pi Zero W2 is the smallest and cheapest Pi that can run a kiosk display. It works well but has some limitations:

- **First boot is slow** — allow 2–3 minutes before expecting SSH to respond
- **`--disable-gpu` flag** — the installer detects this automatically and sets it in Chromium. Do not remove it or Chromium will crash on the Zero W2
- **Wi-Fi only** — no ethernet port. Make sure Wi-Fi credentials are set in the imager before flashing
- **Power** — use a quality 5V/2.5A power supply. Underpowered Pis randomly freeze or corrupt the SD card

### 6f. Pi 5 — additional notes

- Needs the **mini HDMI** adapter (not micro HDMI like the Zero W2 / Pi 4)
- Uses a **USB-C power supply, 5V/3A minimum**
- The installer automatically applies a Chromium flag fix specific to Pi 5's 16K page size — this is normal

---

## 7. Assigning Rooms to Displays

Once a Pi has run the installer, it appears in the Admin panel.

1. Open `http://YOUR_SERVER_IP/admin`
2. Scroll to the **Clients** section
3. Find the Pi by hostname
4. Click **Edit**:
   - Select a **Room** from the dropdown
   - Optionally enable a **Screen Schedule** (the display powers off and on at set times)
5. Click **Save**

The Pi picks up its new room assignment within 60 seconds and switches from the waiting screen to that room's live calendar.

---

## 8. Updating the Server

When code changes are pushed to GitHub, update without reinstalling using:

```bash
display-update
```

*(If the alias isn't available yet: `source ~/.bashrc` first, or run `bash ~/propared-display/install-server.sh --update`)*

This will:
- Pull the latest code from GitHub
- Update Python packages if needed
- Restart the server service
- Leave all rooms, settings, and data files untouched

---

## 9. Useful Commands

### Server commands

| Command | What it does |
|---|---|
| `display-update` | Pull latest code from GitHub and restart |
| `display-restart` | Restart the server service |
| `display-stop` | Stop the server |
| `display-status` | Show whether the service is running |
| `display-logs` | Stream live server logs (Ctrl+C to stop) |

### Display client (Pi) commands

| Command | What it does |
|---|---|
| `kiosk-restart` | Restart the kiosk (restart LightDM) |
| `kiosk-logs` | Stream watchdog logs |
| `kiosk-stop` | Stop the kiosk display |
| `kiosk-status` | Check if LightDM is running |
| `screen-on` | Turn the physical display on |
| `screen-off` | Turn the physical display off |
| `client-log` | Show the last kiosk session log |
| `client-id` | Show this Pi's Client ID |
| `client-config` | Show the saved server URL and client config |
| `watchdog-run` | Manually run one watchdog cycle |

> These aliases are added to `~/.bashrc` by the installer. Run `source ~/.bashrc` or open a new terminal session after install if they're not available yet.

---

## 10. Testing Branch Workflow

The `testing` branch is used to safely test changes before pushing to production displays.

### Setup

Install on a separate sandbox VM or Pi using the testing installer:

```bash
bash install-server-testing.sh
```

The testing server works identically to production but is clearly labeled with a yellow banner in the installer summary.

### Workflow

1. Make changes on the `testing` branch
2. Deploy to the sandbox with `display-update`
3. Test thoroughly
4. When ready, open a pull request on GitHub to merge `testing` → `main`
5. After merging, update the production server:

```bash
# On the production server
display-update
```

### Promoting to production manually

```bash
# On your local machine
git checkout main
git merge testing
git push origin main

# Then on the production server
display-update
```
