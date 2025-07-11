#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting Tunnel Manager Installation..."

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
# Fallback if zip isn't available for a target, some might be .tar.gz
# RATHOLE_DOWNLOAD_URL_TGZ="https://github.com/rathole-org/rathole/releases/download/${RATHOLE_VERSION}/rathole-${RATHOLE_ARCH}.tar.gz"


# --- 1. System Dependencies ---
echo "Updating package lists..."
sudo apt-get update -y

echo "Installing system dependencies (python3, pip3, curl, unzip)..."
sudo apt-get install -y python3 python3-pip curl unzip git

# --- 2. Download and Install Rathole ---
echo "Downloading Rathole ${RATHOLE_VERSION} for ${RATHOLE_ARCH}..."
cd /tmp
curl -sSL -o rathole.zip "$RATHOLE_DOWNLOAD_URL"

# Check if download was successful (curl returns 0 on success)
if [ $? -ne 0 ]; then
    echo "Failed to download rathole.zip. Please check the URL or version."
    # Attempt tar.gz as fallback for some architectures if needed
    # echo "Attempting to download tar.gz..."
    # curl -sSL -o rathole.tar.gz "$RATHOLE_DOWNLOAD_URL_TGZ"
    # if [ $? -ne 0 ]; then
    #    echo "Failed to download rathole.tar.gz as well. Exiting."
    #    exit 1
    # fi
    # sudo tar -xzf rathole.tar.gz -C /usr/local/bin rathole \
    #   && sudo chmod +x /usr/local/bin/rathole
    exit 1
else
    unzip -o rathole.zip
    # Assuming the binary is named 'rathole' directly in the zip, or in a subdirectory
    # Adjust if rathole zip structure changes
    if [ -f "rathole-${RATHOLE_ARCH}/rathole" ]; then # If it's in a subdirectory
        sudo mv "rathole-${RATHOLE_ARCH}/rathole" /usr/local/bin/rathole
    elif [ -f "rathole" ]; then # If it's in the root of the zip
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
sudo mkdir -p "$APP_DIR/instance/rathole_configs" # For rathole configs and DB

# Temporarily, let's assume the script is run from the repo root
# In a real scenario, you might git clone or unpack a release tarball
echo "Copying application files to $APP_DIR..."
# Create a temporary directory for copying
TEMP_COPY_DIR="/tmp/tunnel_manager_src"
mkdir -p "$TEMP_COPY_DIR"
cp -r . "$TEMP_COPY_DIR/" # Copy current dir (repo)

# Now copy from temp dir to app dir (as sudo)
sudo cp -r "$TEMP_COPY_DIR/app.py" "$APP_DIR/"
sudo cp -r "$TEMP_COPY_DIR/database.py" "$APP_DIR/"
sudo cp -r "$TEMP_COPY_DIR/rathole_manager.py" "$APP_DIR/"
sudo cp -r "$TEMP_COPY_DIR/requirements.txt" "$APP_DIR/"
sudo cp -r "$TEMP_COPY_DIR/templates" "$APP_DIR/"
# Ensure 'instance' directory exists in APP_DIR for database.py and rathole_manager.py
sudo mkdir -p "$APP_DIR/instance"
sudo mkdir -p "$APP_DIR/instance/rathole_configs"


# Set ownership to a non-root user if desired, for now run as root or manage permissions
# sudo chown -R youruser:yourgroup "$APP_DIR"

cd "$APP_DIR"

# --- 4. Python Dependencies ---
echo "Installing Python dependencies..."
sudo $PIP_EXEC install -r requirements.txt

# --- 5. Initial Database and User Setup ---
echo "Initializing database and creating admin user..."
# Generate a random password
ADMIN_PASSWORD=$(openssl rand -base64 12)
ADMIN_USERNAME="admin"

# Use Python to call the setup functions
# This assumes app.py and database.py can be run to initialize
# We need a way to pass the generated password to create_initial_user
# For now, we'll create a small helper script or directly call python code.

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
# This is the main server.toml for the panel's rathole server instance
# It will listen for incoming rathole client connections.
# Individual services exposed BY this panel will be added to this config dynamically by rathole_manager.py
echo "Generating default rathole server.toml..."
DEFAULT_SERVER_LISTEN_ADDR="0.0.0.0:2333" # Default rathole port
sudo $PYTHON_EXEC -c "
import toml
import os
config_dir = os.path.join('$APP_DIR', 'instance', 'rathole_configs')
os.makedirs(config_dir, exist_ok=True)
server_config_file = os.path.join(config_dir, 'server.toml')
config_data = {
    'server': {
        'bind_addr': '$DEFAULT_SERVER_LISTEN_ADDR',
        'heartbeat_interval': 30
    }
    # No services defined here initially; they are added dynamically
    # by rathole_manager.py by rewriting this file.
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
echo "Web Panel URL: http://<YOUR_SERVER_IP>:5001"
echo "Admin Username: $ADMIN_USERNAME"
echo "Admin Password: $ADMIN_PASSWORD  (SAVE THIS! It will not be shown again.)"
echo ""
echo "Important Next Steps:"
echo "1. Configure your firewall to allow traffic on port 5001 (for the web panel) and $DEFAULT_SERVER_LISTEN_ADDR (for rathole server)."
echo "   Example for ufw: sudo ufw allow 5001/tcp"
echo "                    sudo ufw allow ${DEFAULT_SERVER_LISTEN_ADDR#*:}tcp" # Extracts port from bind_addr
echo "   Also allow ports for any 'Panel Hosted Services' you configure."
echo ""
echo "2. To run the application, navigate to $APP_DIR and run:"
echo "   sudo $PYTHON_EXEC app.py"
echo "   (This will also attempt to start the main rathole server process if services are configured)"
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
echo "   (Note: The Flask app currently tries to manage this, but a separate service can be more robust)"
echo "   --------------------------------------------------------------------"
echo "[Unit]"
echo "Description=Tunnel Manager - Rathole Server"
echo "After=network.target"
echo ""
echo "[Service]"
echo "User=root # Or a dedicated user"
echo "WorkingDirectory=$APP_DIR/instance/rathole_configs"
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
rm -rf "$TEMP_COPY_DIR"

exit 0
