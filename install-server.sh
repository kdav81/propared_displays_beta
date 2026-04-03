#!/usr/bin/env bash
# =============================================================================
# Propared Calendar Displays — Production Server Installer (main branch)
# Target: Oracle Cloud Free Tier, Ubuntu 22.04 — or any Debian-based Linux server
#
# Run as: ubuntu (the default Oracle Cloud user), NOT root
# Usage:
#   bash install-server.sh            # fresh install
#   bash install-server.sh --update   # pull latest code, preserve all data
# =============================================================================
set -euo pipefail

BRANCH="main"
REPO="https://github.com/kdav81/propared_displays_beta.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()   { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()    { echo -e "${RED}[ERR]${NC}   $*" >&2; exit 1; }
header() {
    echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $*${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
}

UPDATE_ONLY=false
[[ "${1:-}" == "--update" ]] && UPDATE_ONLY=true

APP_USER="${USER}"
APP_DIR="${HOME}/propared-display"
VENV_DIR="${APP_DIR}/venv"
SERVICE_NAME="propared-display"
PORT=80
TZ_TARGET="America/New_York"

[[ "${APP_USER}" == "root" ]] && die "Do not run as root. Run as 'ubuntu'."

header "Propared Calendar Displays — Server Installer (branch: ${BRANCH})"
echo "  User      : ${APP_USER}"
echo "  App dir   : ${APP_DIR}"
echo "  Branch    : ${BRANCH}"
echo "  Port      : ${PORT}"
echo "  Timezone  : ${TZ_TARGET}"
[[ "${UPDATE_ONLY}" == "true" ]] && \
    echo -e "  Mode      : ${YELLOW}UPDATE ONLY — data files preserved${NC}" || \
    echo    "  Mode      : Fresh install"
echo

# =============================================================================
# UPDATE MODE — pull latest code and restart, nothing else
# =============================================================================
if [[ "${UPDATE_ONLY}" == "true" ]]; then
    header "Pulling latest code from GitHub (${BRANCH})"

    if [[ ! -d "${APP_DIR}/.git" ]]; then
        die "${APP_DIR} is not a git repo. Run without --update to do a fresh install."
    fi

    cd "${APP_DIR}"
    git fetch origin
    git checkout "${BRANCH}"
    git pull origin "${BRANCH}"
    info "Code updated from branch: ${BRANCH}"

    header "Updating Python packages"
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"
    info "Python packages up to date."

    header "Restarting service"
    sudo systemctl restart "${SERVICE_NAME}"
    sleep 2

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo -e "\n${GREEN}  ✓  ${SERVICE_NAME} restarted successfully${NC}"
    else
        echo -e "\n${RED}  ✗  Service failed to restart${NC}"
        warn "Check logs: journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
    echo
    exit 0
fi

# =============================================================================
# FRESH INSTALL
# =============================================================================

# ── 1. System packages ────────────────────────────────────────────────────────
header "Step 1 — System Packages"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-venv python3-pip \
    authbind curl git
info "Packages installed."

CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "unknown")
if [[ "${CURRENT_TZ}" != "${TZ_TARGET}" ]]; then
    sudo timedatectl set-timezone "${TZ_TARGET}"
    info "Timezone set to ${TZ_TARGET}."
else
    info "Timezone already ${TZ_TARGET}."
fi

sudo touch /etc/authbind/byport/${PORT}
sudo chmod 755 /etc/authbind/byport/${PORT}
sudo chown "${APP_USER}" /etc/authbind/byport/${PORT}
info "authbind configured for port ${PORT}."

# ── 2. Clone repository ───────────────────────────────────────────────────────
header "Step 2 — Downloading Application Files"

if [[ -d "${APP_DIR}/.git" ]]; then
    info "Existing repo found — fetching latest ${BRANCH}..."
    cd "${APP_DIR}"
    git fetch origin
    git checkout "${BRANCH}"
    git pull origin "${BRANCH}"
else
    info "Cloning ${REPO} (branch: ${BRANCH})..."
    git clone --branch "${BRANCH}" "${REPO}" "${APP_DIR}"
fi

# Create runtime directories that are gitignored
mkdir -p "${APP_DIR}"/{static,cache,backups}
mkdir -p "${APP_DIR}/static/admin"
info "Application files ready in ${APP_DIR}."

# ── 3. Python virtual environment ─────────────────────────────────────────────
header "Step 3 — Python Environment"
if [[ -d "${VENV_DIR}" ]]; then
    info "Virtual environment exists — upgrading packages..."
else
    info "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"
info "Python packages installed."

# ── 4. Firewall (inbound + outbound) ─────────────────────────────────────────
header "Step 4 — Firewall"
# Inbound: allow port 80 and 443 before the default REJECT rule
if ! sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 4 -p tcp --dport 80 -j ACCEPT
    info "Added iptables rule: allow TCP in on 80"
fi
if ! sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 4 -p tcp --dport 443 -j ACCEPT
    info "Added iptables rule: allow TCP in on 443"
fi
# Outbound: allow reaching Dropbox, GitHub, iCal feeds etc.
if ! sudo iptables -C OUTPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; then
    sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
    info "Added iptables rule: allow TCP out on 443"
fi
if ! sudo iptables -C OUTPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    sudo iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT
    info "Added iptables rule: allow TCP out on 80"
fi
if command -v netfilter-persistent &>/dev/null; then
    sudo netfilter-persistent save 2>/dev/null || true
elif command -v iptables-save &>/dev/null; then
    sudo mkdir -p /etc/iptables
    sudo sh -c 'iptables-save > /etc/iptables/rules.v4' || true
fi
info "Firewall rules saved."

# ── 5. Systemd service ────────────────────────────────────────────────────────
header "Step 5 — Systemd Service"
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays Server (${BRANCH})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/authbind --deep ${VENV_DIR}/bin/python3 ${APP_DIR}/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}
Environment=PORT=${PORT}
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/${SERVICE_NAME}-nightly.service > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays Nightly Restart

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart ${SERVICE_NAME}
EOF

sudo tee /etc/systemd/system/${SERVICE_NAME}-nightly.timer > /dev/null << EOF
[Unit]
Description=Propared Calendar Displays Nightly Restart at 3 AM

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl enable "${SERVICE_NAME}-nightly.timer"
sudo systemctl start  "${SERVICE_NAME}-nightly.timer"
info "Service unit written and enabled."
info "Nightly 3 AM restart timer enabled."

# ── 6. Convenience aliases ────────────────────────────────────────────────────
BASHRC="${HOME}/.bashrc"
declare -A ALIAS_MAP=(
    ["display-logs"]="journalctl -u ${SERVICE_NAME} -f"
    ["display-restart"]="sudo systemctl restart ${SERVICE_NAME}"
    ["display-stop"]="sudo systemctl stop ${SERVICE_NAME}"
    ["display-status"]="sudo systemctl status ${SERVICE_NAME}"
    ["display-update"]="bash ${APP_DIR}/install-server.sh --update"
)
for NAME in "${!ALIAS_MAP[@]}"; do
    if ! grep -qF "alias ${NAME}=" "${BASHRC}" 2>/dev/null; then
        echo "alias ${NAME}='${ALIAS_MAP[$NAME]}'" >> "${BASHRC}"
    fi
done
info "Shell aliases added to ~/.bashrc"

# ── 7. Start service ──────────────────────────────────────────────────────────
header "Step 6 — Starting Service"
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    info "Restarting service..."
    sudo systemctl restart "${SERVICE_NAME}"
else
    info "Starting service..."
    sudo systemctl start "${SERVICE_NAME}"
fi
sleep 2

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${GREEN}══════════════════════════════════════════${NC}"
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo -e "${GREEN}  ✓  Propared Calendar Displays server is running!${NC}"
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    echo
    PUBLIC_IP=$(curl -sf --max-time 5 http://checkip.amazonaws.com 2>/dev/null || hostname -I | awk '{print $1}')
    echo "  Branch       : ${BRANCH}"
    echo "  Admin panel  : http://${PUBLIC_IP}/admin"
    echo "  Status page  : http://${PUBLIC_IP}/status"
    echo "  Logs         : journalctl -u ${SERVICE_NAME} -f"
    echo "  Alias        : display-logs  (reload shell first)"
    echo
    echo "  To update without reinstalling:"
    echo "    bash ${APP_DIR}/install-server.sh --update"
    echo "    (or: display-update  after reloading shell)"
else
    echo -e "${RED}  ✗  Service failed to start${NC}"
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    echo
    warn "Check logs: journalctl -u ${SERVICE_NAME} -n 50"
    exit 1
fi
echo

exit 0
