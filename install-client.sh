#!/usr/bin/env bash
# =============================================================================
# Propared Calendar Displays — Client Install Script
# Raspberry Pi OS Trixie (Debian 13), 64-bit
# Supports:
#   Pi 4/5  — full Raspberry Pi Desktop (rpd-labwc / LightDM already present)
#   Pi Zero W2 — fresh flash, installs minimal X stack + LightDM
#
# Run as your normal user (not root). sudo called internally where needed.
# Safe to re-run — reads existing config and offers to keep or change it.
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERR]${NC}   $*" >&2; exit 1; }
header(){
    echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $*${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════${NC}"
}

CONF_DIR="/etc/propared"
SCREEN_SCHEDULE_ENABLED="no"
SCREEN_ON="08:00"
SCREEN_OFF="22:00"
CONF_FILE="${CONF_DIR}/client.conf"
WATCHDOG_SERVICE="propared-watchdog"
SCREEN_ON_TIMER="propared-screen-on"
SCREEN_OFF_TIMER="propared-screen-off"
KIOSK_USER="${USER}"
KIOSK_DIR="${HOME}/.config/propared-kiosk"

# =============================================================================
# Detect display stack
# =============================================================================
HAS_LIGHTDM=false
dpkg -l lightdm &>/dev/null 2>&1 && HAS_LIGHTDM=true
[[ -f /usr/sbin/lightdm ]] && HAS_LIGHTDM=true
[[ -f /usr/bin/lightdm  ]] && HAS_LIGHTDM=true

if $HAS_LIGHTDM; then
    DISPLAY_STACK="lightdm"
    info "Detected: Raspberry Pi Desktop (LightDM) — Pi 4/5 mode"
else
    DISPLAY_STACK="minimal"
    info "Detected: No display manager — will install minimal stack (Pi Zero W2 mode)"
fi

# Detect if GPU flag should be disabled
# Pi Zero W2 (4K page size) needs --disable-gpu; Pi 4/5 (16K page size) does not
PAGESIZE=$(getconf PAGESIZE 2>/dev/null || echo 4096)
if [[ "${PAGESIZE}" -gt 4096 ]]; then
    DISABLE_GPU_FLAG=""
    info "Pi 4/5 detected (page size ${PAGESIZE}) — GPU enabled"
else
    DISABLE_GPU_FLAG="--disable-gpu"
    info "Pi Zero W2 detected (page size ${PAGESIZE}) — GPU disabled"
fi

# =============================================================================
# Step 1 — Load or keep existing config
# =============================================================================
header "Propared Calendar Displays Client Installer"

if [[ "${EUID}" -eq 0 ]]; then
    die "Run this installer as your normal user, not root."
fi

if ! command -v curl >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    header "Bootstrapping Installer Dependencies"
    sudo apt-get update -qq
    sudo apt-get install -y -qq curl python3
    info "Installed required bootstrap tools: curl, python3"
fi

SERVER_URL=""
CLIENT_ID=""

if [[ -f "${CONF_FILE}" ]]; then
    source "${CONF_FILE}"
    echo
    echo "  Existing config found:"
    echo "    Server    : ${SERVER_URL}"
    echo "    Client ID : ${CLIENT_ID}"
    echo
    read -rp "  Keep this config? [Y/n]: " KEEP
    if [[ "${KEEP,,}" == "n" ]]; then
        SERVER_URL=""
        # Keep CLIENT_ID — it's the Pi's permanent identity
        info "Server cleared. Client ID preserved: ${CLIENT_ID}"
    else
        info "Keeping existing config."
    fi
fi

# Generate a CLIENT_ID if we don't have one yet
if [[ -z "${CLIENT_ID}" ]]; then
    CLIENT_ID=$(cat /proc/sys/kernel/random/uuid)
    info "Generated new Client ID: ${CLIENT_ID}"
fi

# =============================================================================
# Step 2 — Server URL
# =============================================================================
if [[ -z "${SERVER_URL}" ]]; then
    header "Step 1 of 2 - Server"
    echo "  Enter the IP or hostname of your Propared Calendar Displays server."
    echo "  Example: 129.80.14.172"
    echo
    while true; do
        read -rp "  Server address: " RAW
        RAW="${RAW// /}"
        [[ -z "${RAW}" ]] && { warn "Cannot be empty."; continue; }
        RAW="${RAW#http://}"; RAW="${RAW#https://}"; RAW="${RAW%/}"
        SERVER_URL="http://${RAW}"
        info "Testing connection to ${SERVER_URL}/api/health ..."
        if curl -sf --max-time 5 "${SERVER_URL}/api/health" > /dev/null 2>&1; then
            info "Server reachable"
            break
        else
            warn "Could not reach ${SERVER_URL}/api/health"
            read -rp "  Try again? [Y/n]: " RETRY
            [[ "${RETRY,,}" == "n" ]] && break
        fi
    done
fi

# =============================================================================
# Step 2 — Register with server
# =============================================================================
header "Step 2 of 2 - Register with server"
info "Registering client ID with server..."
HOSTNAME_VAL=$(hostname)
curl -sf --max-time 8 \
    -X POST "${SERVER_URL}/api/checkin" \
    -H "Content-Type: application/json" \
    -d "{\"client_id\":\"${CLIENT_ID}\",\"hostname\":\"${HOSTNAME_VAL}\",\"ip\":\"\",\"role\":\"display\"}" \
    > /dev/null 2>&1 || warn "Could not register — will retry at runtime"
info "Client registered. Assign a room in the Admin panel at ${SERVER_URL}/admin"
echo
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │  Client ID: ${CLIENT_ID}"
echo "  │  Go to ${SERVER_URL}/admin to assign this Pi a room.        │"
echo "  └─────────────────────────────────────────────────────────────┘"
echo

# Save config
# =============================================================================
sudo mkdir -p "${CONF_DIR}"
sudo tee "${CONF_FILE}" > /dev/null << EOF
# Theatre & Dance Room Display client config -- auto-generated by install-client.sh
SERVER_URL="${SERVER_URL}"
CLIENT_ID="${CLIENT_ID}"
KIOSK_USER="${KIOSK_USER}"
KIOSK_DIR="${KIOSK_DIR}"
EOF
info "Config saved to ${CONF_FILE}"

# =============================================================================
# Step 5 — System packages
# =============================================================================
header "Installing packages..."
sudo apt-get update -qq

if [[ "${DISPLAY_STACK}" == "lightdm" ]]; then
    # Pi 4/5: LightDM + desktop already present
    sudo apt-get install -y -qq \
        chromium \
        curl \
        python3 \
        unclutter \
        x11-xserver-utils \
        gnome-keyring \
        libpam-gnome-keyring
else
    # Pi Zero W2: install minimal X stack + LightDM
    sudo apt-get install -y -qq \
        chromium \
        curl \
        python3 \
        unclutter \
        x11-xserver-utils \
        xserver-xorg \
        xinit \
        openbox \
        lightdm \
        lightdm-gtk-greeter \
        gnome-keyring \
        libpam-gnome-keyring
    DISPLAY_STACK="lightdm"
    info "Installed minimal X stack + LightDM"
fi
info "Packages installed."

# =============================================================================
# Step 6 — Chromium kiosk launcher
# =============================================================================
mkdir -p "${KIOSK_DIR}"

cat > "${KIOSK_DIR}/start-kiosk.sh" << 'KIOSK'
#!/usr/bin/env bash
exec > /tmp/kiosk.log 2>&1
echo "=== Kiosk starting at $(date) ==="
source /etc/propared/client.conf

CACHE_FILE="${KIOSK_DIR}/client-cache.json"
WAITING_URL="file://${KIOSK_DIR}/waiting.html"

# Write the waiting screen HTML file
cat > "${KIOSK_DIR}/waiting.html" << WAITHTML
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Waiting</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0c0f;color:#666680;font-family:sans-serif;
  display:flex;align-items:center;justify-content:center;height:100vh}
.box{text-align:center}
.icon{font-size:64px;margin-bottom:24px}
.title{font-size:28px;font-weight:300;color:#9090b0;margin-bottom:12px}
.sub{font-size:16px;color:#555570}
.url{font-size:14px;color:#4f6ef7;margin-top:8px}
</style>
</head>
<body>
<div class="box">
  <div class="icon">&#128225;</div>
  <div class="title">Waiting for room assignment</div>
  <div class="sub">This display has not been assigned a room yet.</div>
  <div class="url">Configure at ${SERVER_URL}/admin</div>
</div>
</body>
</html>
WAITHTML

# Fetch config from server, fall back to cache
fetch_config() {
    local HN=$(hostname)
    local RESPONSE
    RESPONSE=$(curl -sf --max-time 8         "${SERVER_URL}/api/client-config/${CLIENT_ID}?hostname=${HN}" 2>/dev/null)
    if [[ -n "${RESPONSE}" ]]; then
        echo "${RESPONSE}" > "${CACHE_FILE}"
        echo "${RESPONSE}"
        return 0
    fi
    # Server unreachable — try cache
    if [[ -f "${CACHE_FILE}" ]]; then
        echo "$(cat ${CACHE_FILE})"
        return 0
    fi
    return 1
}

apply_schedule() {
    local CFG="$1"
    local ENABLED=$(echo "${CFG}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduleEnabled',False))" 2>/dev/null)
    local ON=$(echo "${CFG}"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('screenOn','08:00'))" 2>/dev/null)
    local OFF=$(echo "${CFG}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('screenOff','22:00'))" 2>/dev/null)

    if [[ "${ENABLED}" == "True" ]]; then
        ON_H="${ON%%:*}"; ON_M="${ON##*:}"
        OFF_H="${OFF%%:*}"; OFF_M="${OFF##*:}"
        local NOW_H=$(date +%H); local NOW_M=$(date +%M)
        local NOW_MINS=$(( 10#${NOW_H} * 60 + 10#${NOW_M} ))
        local ON_MINS=$(( 10#${ON_H} * 60 + 10#${ON_M} ))
        local OFF_MINS=$(( 10#${OFF_H} * 60 + 10#${OFF_M} ))
        if (( NOW_MINS < ON_MINS || NOW_MINS >= OFF_MINS )); then
            echo "Screen schedule: off-hours, turning display off"
            vcgencmd display_power 0 2>/dev/null || true
        else
            vcgencmd display_power 1 2>/dev/null || true
        fi
    fi
}

# Wait for network before starting — avoids empty config fetch on fast boot
for i in $(seq 1 15); do
    if curl -sf --max-time 3 "${SERVER_URL}/api/health" > /dev/null 2>&1; then
        echo "Network ready after ${i}s"
        break
    fi
    echo "Waiting for network... (${i}/15)"
    sleep 2
done

# Keep xset running in a loop
(while true; do xset s off; xset s noblank; xset -dpms; sleep 30; done) &
unclutter -idle 3 -root &
openbox &
sleep 1

while true; do
    # Fetch config fresh on each loop iteration
    CFG=$(fetch_config)
    if [[ -n "${CFG}" ]]; then
        DISPLAY_URL=$(echo "${CFG}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('display_url',''))" 2>/dev/null)
        apply_schedule "${CFG}"
    else
        DISPLAY_URL=""
    fi

    # If unassigned, show waiting screen
    if [[ -z "${DISPLAY_URL}" ]]; then
        LAUNCH_URL="${WAITING_URL}"
    else
        LAUNCH_URL="${SERVER_URL}${DISPLAY_URL}"
    fi

    rm -f "${KIOSK_DIR}/chromium/SingletonLock"           "${KIOSK_DIR}/chromium/SingletonSocket"           "${KIOSK_DIR}/chromium/SingletonCookie" 2>/dev/null || true
    mkdir -p "${KIOSK_DIR}/chromium/Default"
    cat > "${KIOSK_DIR}/chromium/Default/Preferences" << 'PREFS'
{"browser":{"check_default_browser":false,"has_seen_welcome_page":true},"profile":{"exit_type":"Normal","exited_cleanly":true,"password_manager_enabled":false},"signin":{"allowed":false},"credentials_enable_service":false}
PREFS

    chromium         --no-memcheck         --kiosk         --start-fullscreen         --window-size=1920,1080         --window-position=0,0         --noerrdialogs         --disable-infobars         --no-first-run         --no-default-browser-check         --disable-translate         --disable-extensions         --disable-sync         --disable-background-networking         --disable-default-apps         --disable-component-update         --disable-hang-monitor         --disable-popup-blocking         --disable-prompt-on-repost         --disable-renderer-backgrounding         --metrics-recording-only         --safebrowsing-disable-auto-update         --password-store=basic         ${DISABLE_GPU_FLAG}         --disable-session-crashed-bubble         --user-data-dir="${KIOSK_DIR}/chromium"         "${LAUNCH_URL}"
    echo "Chromium exited $? at $(date) -- refetching config in 5s"
    sleep 5
done
KIOSK
chmod +x "${KIOSK_DIR}/start-kiosk.sh"
info "Kiosk launcher written"

# =============================================================================
# Step 7 — Register kiosk as a LightDM session
# A bare .desktop session -- no desktop shell, just Chromium
# =============================================================================
sudo tee /usr/share/xsessions/propared-kiosk.desktop > /dev/null << EOF
[Desktop Entry]
Name=Propared Kiosk
Comment=Propared Calendar Displays fullscreen kiosk
Exec=${KIOSK_DIR}/start-kiosk.sh
Type=Application
EOF
info "Kiosk session registered with LightDM"

# =============================================================================
# Step 8 — Configure LightDM autologin into kiosk session
# =============================================================================
LIGHTDM_CONF="/etc/lightdm/lightdm.conf"

sudo python3 - << PYEOF
import configparser

path = "${LIGHTDM_CONF}"
cfg = configparser.ConfigParser(strict=False)
cfg.read(path)

section = "Seat:*"
if not cfg.has_section(section):
    cfg.add_section(section)

cfg.set(section, "autologin-user",         "${KIOSK_USER}")
cfg.set(section, "autologin-session",      "propared-kiosk")
cfg.set(section, "autologin-user-timeout", "0")
cfg.set(section, "user-session",           "propared-kiosk")

with open(path, "w") as f:
    cfg.write(f)

print("LightDM config updated.")
PYEOF
info "LightDM: autologin as ${KIOSK_USER} into propared-kiosk session"

# Override LightDM unit to remove GPU device dependencies
# Pi Zero W2 has no dev-dri-card0 — without this LightDM never starts at boot
sudo mkdir -p /etc/systemd/system/lightdm.service.d
printf '[Unit]\nAfter=systemd-user-sessions.service\nWants=\n' | \
    sudo tee /etc/systemd/system/lightdm.service.d/override.conf > /dev/null
sudo systemctl daemon-reload
info "LightDM GPU dependency override applied"

# Ensure graphical target is default — Lite OS boots to multi-user by default
sudo systemctl set-default graphical.target
sudo systemctl enable lightdm --force
info "Default target set to graphical.target"

# =============================================================================
# Step 9 — Suppress GNOME Keyring prompt
#
# Chromium with --password-store=basic does NOT use the keyring at all,
# so the prompt should never appear. But we belt-and-braces it by:
#   1. Pre-creating a blank-password login keyring
#   2. Writing Chromium prefs to disable password saving
#   3. Adding PAM keyring auto-unlock to LightDM
# =============================================================================
info "Configuring keyring for silent unlock..."

# Remove any old keyring that has a password set
KEYRING_DIR="${HOME}/.local/share/keyrings"
mkdir -p "${KEYRING_DIR}"
rm -f "${KEYRING_DIR}"/*.keyring 2>/dev/null || true

# Pre-populate Chromium prefs -- disable password manager and sign-in
CHROMIUM_PREFS_DIR="${KIOSK_DIR}/chromium/Default"
mkdir -p "${CHROMIUM_PREFS_DIR}"
PREFS_FILE="${CHROMIUM_PREFS_DIR}/Preferences"

cat > "${PREFS_FILE}" << 'PREFS'
{
   "browser": {
      "check_default_browser": false,
      "has_seen_welcome_page": true
   },
   "profile": {
      "password_manager_enabled": false,
      "default_content_setting_values": {
         "notifications": 2
      }
   },
   "signin": {
      "allowed": false
   },
   "credentials_enable_service": false,
   "credentials_enable_autosignin": false
}
PREFS
info "Chromium preferences written (password store: basic, no sign-in)"

# PAM: auto-unlock keyring on LightDM login
LIGHTDM_PAM="/etc/pam.d/lightdm"
if [[ -f "${LIGHTDM_PAM}" ]] && ! grep -q "pam_gnome_keyring" "${LIGHTDM_PAM}"; then
    echo "auth     optional  pam_gnome_keyring.so"    | sudo tee -a "${LIGHTDM_PAM}" > /dev/null
    echo "session  optional  pam_gnome_keyring.so auto_start" | sudo tee -a "${LIGHTDM_PAM}" > /dev/null
    info "PAM keyring auto-unlock added to LightDM"
fi

# =============================================================================
# Step 9b — Fix Chromium crash on Pi 5 (16KB page size)
# On Pi 5, getconf PAGESIZE returns 16384 which triggers --no-decommit-pooled-pages
# in the Chromium wrapper, but Chromium 146+ does not support this flag and crashes.
# =============================================================================
if [[ "$(getconf PAGESIZE)" -gt "4096" ]]; then
    sudo tee /etc/chromium.d/propared-override > /dev/null << 'CHROMEOF'
# Propared Calendar Displays: remove unsupported --no-decommit-pooled-pages flag on Pi 5
export CHROMIUM_FLAGS=$(echo "$CHROMIUM_FLAGS" | sed 's/--js-flags=--no-decommit-pooled-pages//')
CHROMEOF
    info "Applied Chromium Pi 5 page size fix"
fi

# =============================================================================
# Step 10 — Disable console blanking
# =============================================================================
CMDLINE="/boot/firmware/cmdline.txt"
if [[ -f "${CMDLINE}" ]] && ! grep -q "consoleblank=0" "${CMDLINE}"; then
    sudo sed -i 's/$/ consoleblank=0/' "${CMDLINE}"
    info "Added consoleblank=0 to boot cmdline"
fi

# =============================================================================
# Step 11 — Watchdog: heartbeat + Chromium crash recovery
# =============================================================================
cat > "${KIOSK_DIR}/watchdog.sh" << 'WATCHDOG'
#!/usr/bin/env bash
source /etc/propared/client.conf

HOSTNAME_VAL="$(hostname)"
IP_VAL="$(hostname -I | awk '{print $1}')"
LOG_TAG="propared-watchdog"

# Send heartbeat checkin
curl -sf --max-time 4 \
    -X POST "${SERVER_URL}/api/checkin" \
    -H "Content-Type: application/json" \
    -d "{\"client_id\":\"${CLIENT_ID}\",\"hostname\":\"${HOSTNAME_VAL}\",\"ip\":\"${IP_VAL}\",\"role\":\"display\"}" \
    > /dev/null 2>&1 || true

# If server unreachable, leave Chromium running on last loaded page
if ! curl -sf --max-time 5 "${SERVER_URL}/api/health" > /dev/null 2>&1; then
    logger -t "${LOG_TAG}" "Server unreachable -- Chromium kept on last page"
    exit 0
fi

# Restart LightDM if Chromium has crashed
if ! pgrep -f "chromium.*kiosk" > /dev/null 2>&1; then
    logger -t "${LOG_TAG}" "Chromium not running -- restarting LightDM"
    sudo systemctl restart lightdm
fi
WATCHDOG
chmod +x "${KIOSK_DIR}/watchdog.sh"

# Watchdog systemd service
sudo tee /etc/systemd/system/${WATCHDOG_SERVICE}.service > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays Watchdog

[Service]
Type=oneshot
User=${KIOSK_USER}
ExecStart=${KIOSK_DIR}/watchdog.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=propared-watchdog
EOF

# Watchdog timer -- every 60s
sudo tee /etc/systemd/system/${WATCHDOG_SERVICE}.timer > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays Watchdog -- every 60s

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=10

[Install]
WantedBy=timers.target
EOF

# Allow kiosk user to restart LightDM without password (for crash recovery)
SUDOERS_FILE="/etc/sudoers.d/propared-kiosk"
echo "${KIOSK_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart lightdm" \
    | sudo tee "${SUDOERS_FILE}" > /dev/null
sudo chmod 440 "${SUDOERS_FILE}"
info "Watchdog configured"

# =============================================================================
# Step 12 — Screen on/off timers
# =============================================================================
if [[ "${SCREEN_SCHEDULE_ENABLED}" == "yes" ]]; then
    ON_HOUR="${SCREEN_ON%%:*}"; ON_MIN="${SCREEN_ON##*:}"
    OFF_HOUR="${SCREEN_OFF%%:*}"; OFF_MIN="${SCREEN_OFF##*:}"

    sudo tee /etc/systemd/system/${SCREEN_ON_TIMER}.service > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays -- Screen On
[Service]
Type=oneshot
ExecStart=/usr/bin/vcgencmd display_power 1
ExecStartPost=/bin/systemctl restart lightdm
EOF

    sudo tee /etc/systemd/system/${SCREEN_ON_TIMER}.timer > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays -- Screen On at ${SCREEN_ON}
[Timer]
OnCalendar=*-*-* ${ON_HOUR}:${ON_MIN}:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

    sudo tee /etc/systemd/system/${SCREEN_OFF_TIMER}.service > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays -- Screen Off
[Service]
Type=oneshot
ExecStart=/bin/systemctl stop lightdm
ExecStartPost=/usr/bin/vcgencmd display_power 0
EOF

    sudo tee /etc/systemd/system/${SCREEN_OFF_TIMER}.timer > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays -- Screen Off at ${SCREEN_OFF}
[Timer]
OnCalendar=*-*-* ${OFF_HOUR}:${OFF_MIN}:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now ${SCREEN_ON_TIMER}.timer ${SCREEN_OFF_TIMER}.timer
    info "Screen schedule: ON ${SCREEN_ON}, OFF ${SCREEN_OFF}"
else
    sudo systemctl disable ${SCREEN_ON_TIMER}.timer ${SCREEN_OFF_TIMER}.timer 2>/dev/null || true
    sudo systemctl stop    ${SCREEN_ON_TIMER}.timer ${SCREEN_OFF_TIMER}.timer 2>/dev/null || true
fi

# =============================================================================
# Step 13 — Convenience aliases
# =============================================================================
BASHRC="${HOME}/.bashrc"
declare -A ALIAS_MAP=(
    ["kiosk-logs"]="journalctl -u ${WATCHDOG_SERVICE} -f"
    ["kiosk-restart"]="sudo systemctl restart lightdm"
    ["kiosk-stop"]="sudo systemctl stop lightdm"
    ["kiosk-status"]="sudo systemctl status lightdm"
    ["screen-on"]="vcgencmd display_power 1 && sudo systemctl restart lightdm"
    ["screen-off"]="vcgencmd display_power 0 && sudo systemctl stop lightdm"
    ["client-config"]="cat /etc/propared/client.conf"
    ["client-log"]="cat /tmp/kiosk.log"
    ["client-id"]="grep CLIENT_ID /etc/propared/client.conf"
    ["watchdog-run"]="bash ~/.config/propared-kiosk/watchdog.sh"
)
for NAME in "${!ALIAS_MAP[@]}"; do
    if ! grep -qF "alias ${NAME}=" "${BASHRC}" 2>/dev/null; then
        echo "alias ${NAME}='${ALIAS_MAP[$NAME]}'" >> "${BASHRC}"
    fi
done
# Source bashrc so aliases are available immediately
source "${BASHRC}" 2>/dev/null || true
info "Shell aliases added and loaded"

# =============================================================================
# Step 14 — Enable watchdog and restart LightDM to launch kiosk
# =============================================================================
sudo systemctl daemon-reload
sudo systemctl enable ${WATCHDOG_SERVICE}.timer --now
# Force enable overriding any system preset
sudo systemctl enable ${WATCHDOG_SERVICE}.timer
sudo systemctl start  ${WATCHDOG_SERVICE}.timer
# Verify it's running
sudo systemctl is-active ${WATCHDOG_SERVICE}.timer && info "Watchdog timer active" || warn "Watchdog timer failed to start"
# Also add to /etc/systemd/system preset to survive reboots
sudo mkdir -p /etc/systemd/system-preset
echo "enable ${WATCHDOG_SERVICE}.timer" | sudo tee /etc/systemd/system-preset/50-propared.preset > /dev/null

info "Restarting LightDM -- kiosk should appear on screen now..."
sudo systemctl restart lightdm
sleep 4

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  Propared Calendar Displays Client installed!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo
echo "  Displaying  : ${DISPLAY_URL}"
echo "  Server      : ${SERVER_URL}"
echo "  Stack       : LightDM -> propared-kiosk session"
if [[ "${SCREEN_SCHEDULE_ENABLED}" == "yes" ]]; then
    echo "  Screen      : ON at ${SCREEN_ON}, OFF at ${SCREEN_OFF}"
else
    echo "  Screen      : Always on"
fi
echo
echo "  Commands (reload shell first):"
echo "    kiosk-restart   -- restart the kiosk"
echo "    kiosk-logs      -- live watchdog log"
echo "    screen-on / screen-off"
echo
echo "  To change URL:"
echo "    sudo nano ${CONF_FILE}"
echo "    kiosk-restart"
echo
echo "  Status page: ${SERVER_URL}/status"
echo

exit 0
