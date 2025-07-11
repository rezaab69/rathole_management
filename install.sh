#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting Tunnel Manager Installation..."

APP_SOURCE_DIR="$1"

if [ -z "$APP_SOURCE_DIR" ]; then
    echo "Error: Source directory not provided as the first argument to install.sh."
    echo "Usage: sudo bash install.sh /path/to/cloned/repo"
    exit 1
fi

if [ ! -d "$APP_SOURCE_DIR" ]; then
    echo "Error: Provided source directory '$APP_SOURCE_DIR' does not exist or is not a directory."
    exit 1
fi
echo "Using application source directory: $APP_SOURCE_DIR"


# --- Configuration ---
APP_DIR="/opt/my-tunnel-manager"
PYTHON_EXEC="python3"
PIP_EXEC="pip3"
RATHOLE_VERSION="v0.5.0" # Specify the desired rathole version
# Detect architecture for rathole download
ARCH=$(uname -m)
RATHOLE_ARCH=""
if [ "$ARCH" = "x86_64" ]; then
    RATHOLE_ARCH="x86_64-unknown-linux-gnu"
elif [ "$ARCH" = "aarch64" ]; then
    RATHOLE_ARCH="aarch64-unknown-linux-gnu"
else
    echo "Unsupported architecture: $ARCH for rathole auto-download. Please install rathole manually and ensure it's in PATH."
    exit 1
fi
RATHOLE_DOWNLOAD_URL="https://github.com/rathole-org/rathole/releases/download/${RATHOLE_VERSION}/rathole-${RATHOLE_ARCH}.zip"


# --- 1. System Dependencies ---
echo "Updating package lists..."
sudo apt-get update -y

echo "Installing system dependencies (python3, pip3, curl, unzip, git)..."
sudo apt-get install -y python3 python3-pip curl unzip git

# --- 2. Download and Install Rathole ---
echo "Downloading Rathole ${RATHOLE_VERSION} for ${RATHOLE_ARCH}..."
cd /tmp
curl -sSL -o rathole.zip "$RATHOLE_DOWNLOAD_URL"

if [ $? -ne 0 ]; then
    echo "Failed to download rathole.zip. Please check the URL or version."
    exit 1
else
    unzip -o rathole.zip
    if [ -f "rathole-${RATHOLE_ARCH}/rathole" ]; then
        sudo mv "rathole-${RATHOLE_ARCH}/rathole" /usr/local/bin/rathole
    elif [ -f "rathole" ]; then
        sudo mv rathole /usr/local/bin/rathole
    else
        echo "Could not find 'rathole' binary in the downloaded zip. Please check zip contents."
        exit 1
    fi
    sudo chmod +x /usr/local/bin/rathole
fi

echo "Rathole installed to /usr/local/bin/rathole"
rathole --version # Verify installation

# --- 3. Application Setup ---
echo "Creating application directory: $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo mkdir -p "$APP_DIR/instance/rathole_configs"

echo "Copying application files to $APP_DIR..."
SCRIPT_DIR_TMP="$APP_SOURCE_DIR" # Use the passed argument consistently

# Check if essential files exist in the SCRIPT_DIR_TMP (which is APP_SOURCE_DIR)
if [ ! -f "$SCRIPT_DIR_TMP/app.py" ] || [ ! -f "$SCRIPT_DIR_TMP/requirements.txt" ] || [ ! -d "$SCRIPT_DIR_TMP/templates" ]; then
    echo "Error: Essential application files (app.py, requirements.txt, templates/) not found in source directory: $SCRIPT_DIR_TMP"
    echo "Please ensure the provided source directory '$APP_SOURCE_DIR' is correct and contains the application files."
    exit 1
fi
echo "Essential files found in $SCRIPT_DIR_TMP. Proceeding with copy."

sudo cp -r "$SCRIPT_DIR_TMP/app.py" "$APP_DIR/"
sudo cp -r "$SCRIPT_DIR_TMP/database.py" "$APP_DIR/"
sudo cp -r "$SCRIPT_DIR_TMP/rathole_manager.py" "$APP_DIR/"
sudo cp -r "$SCRIPT_DIR_TMP/requirements.txt" "$APP_DIR/"
sudo cp -r "$SCRIPT_DIR_TMP/templates" "$APP_DIR/"
# Ensure 'instance' directory exists in APP_DIR for database.py and rathole_manager.py
sudo mkdir -p "$APP_DIR/instance" # Already created above, but good for explicitness
sudo mkdir -p "$APP_DIR/instance/rathole_configs" # Already created above

cd "$APP_DIR" # Change directory to APP_DIR for subsequent commands

# --- 4. Python Dependencies ---
echo "Installing Python dependencies..."
sudo $PIP_EXEC install -r requirements.txt

# --- 5. Initial Database and User Setup ---
echo "Initializing database and creating admin user..."
ADMIN_PASSWORD=$(openssl rand -base64 12)
ADMIN_USERNAME="admin"

sudo $PYTHON_EXEC -c "
import database
import app
print('Initializing DB from install script...')
database.init_db()
print('Attempting to create initial user...')
if app.create_initial_user('$ADMIN_USERNAME', '$ADMIN_PASSWORD'):
    print('Initial user created successfully.')
else:
    print('Failed to create initial user or user already exists.')
"

# --- 6. Default Rathole Server Config ---
echo "Generating default rathole server.toml..."
DEFAULT_SERVER_LISTEN_ADDR="0.0.0.0:2333"
sudo $PYTHON_EXEC -c "
import toml
import os
config_dir = os.path.join('$APP_DIR', 'instance', 'rathole_configs')
os.makedirs(config_dir, exist_ok=True) # Ensure it exists, though App Setup section should create it
server_config_file = os.path.join(config_dir, 'server.toml')
config_data = {
    'server': {
        'bind_addr': '$DEFAULT_SERVER_LISTEN_ADDR',
        'heartbeat_interval': 30
    }
}
with open(server_config_file, 'w') as f:
    toml.dump(config_data, f)
print(f'Default server.toml created at {server_config_file}')
"

# --- 7. Systemd Service Files (Examples) ---
echo ""
echo "--------------------------------------------------------------------"
echo "Installation Complete!"
echo "--------------------------------------------------------------------"
echo ""
SERVER_IP_FOR_URL=$(hostname -I | awk '{print $1}')
if [ -z "$SERVER_IP_FOR_URL" ]; then
    SERVER_IP_FOR_URL="<YOUR_SERVER_IP_OR_0.0.0.0>"
fi
RATHOLE_PORT=${DEFAULT_SERVER_LISTEN_ADDR##*:}

echo "Web Panel URL: http://${SERVER_IP_FOR_URL}:5001"
echo "Admin Username: $ADMIN_USERNAME"
echo "Admin Password: $ADMIN_PASSWORD  (SAVE THIS! It will not be shown again.)"
echo ""
echo "Important Next Steps:"
echo "1. Configure your firewall to allow traffic on:"
echo "   - Port 5001/tcp (for the web panel)"
echo "   - Port ${RATHOLE_PORT}/tcp (for the main rathole server, listening on $DEFAULT_SERVER_LISTEN_ADDR)"
echo "   Example for ufw: sudo ufw allow 5001/tcp"
echo "                    sudo ufw allow ${RATHOLE_PORT}/tcp"
echo "   Also allow ports for any 'Panel Hosted Services' you configure."
echo ""
echo "2. To run the application, navigate to $APP_DIR and run:"
echo "   sudo $PYTHON_EXEC app.py"
echo ""
echo "3. For production, set up systemd services to run the Flask app and rathole server automatically:"
echo ""
echo "   Example systemd service for Flask app (e.g., /etc/systemd/system/tunnel-manager-web.service):"
echo "   --------------------------------------------------------------------"
echo "[Unit]"
echo "Description=Tunnel Manager Web UI"
echo "After=network.target"
echo ""
echo "[Service]"
echo "User=root # Or a dedicated user with permissions to $APP_DIR and rathole"
echo "WorkingDirectory=$APP_DIR"
echo "ExecStart=$PYTHON_EXEC app.py"
echo "Restart=always"
echo "Environment=\"FLASK_SECRET_KEY=$(openssl rand -hex 16)\" # IMPORTANT: Set a persistent random key"
echo ""
echo "[Install]"
echo "WantedBy=multi-user.target"
echo "   --------------------------------------------------------------------"
echo ""
echo "   Example systemd service for the main Rathole server (e.g., /etc/systemd/system/tunnel-manager-rathole.service):"
echo "   --------------------------------------------------------------------"
echo "[Unit]"
echo "Description=Tunnel Manager - Rathole Server"
echo "After=network.target"
echo ""
echo "[Service]"
echo "User=root # Or a dedicated user"
echo "WorkingDirectory=$APP_DIR/instance/rathole_configs" # Rathole server should run from where its server.toml is
echo "ExecStart=/usr/local/bin/rathole server.toml"
echo "Restart=always"
echo "Environment=\"RUST_LOG=info\""
echo ""
echo "[Install]"
echo "WantedBy=multi-user.target"
echo "   --------------------------------------------------------------------"
echo "   After creating service files, run: sudo systemctl daemon-reload && sudo systemctl enable --now <service_name>"
echo ""
echo "Rathole version used: $RATHOLE_VERSION"
echo "Installation script finished."

# Clean up downloaded files
rm -f /tmp/rathole.zip
rm -rf /tmp/rathole-${RATHOLE_ARCH}
# TEMP_COPY_DIR was removed, so no need to clean it up.

exit 0
