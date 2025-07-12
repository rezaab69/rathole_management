# Rathole Web Tunnel Manager

A web-based graphical interface to manage [rathole](https://github.com/rathole-org/rathole) tunnels. This panel allows users to easily add, remove, start, and stop rathole services, acting as either a rathole server for multiple defined services or as a rathole client for specific remote services.

## Features

*   **Web-Based UI:** Manage tunnels from your browser.
    *   Login page for secure access.
    *   Dashboard for viewing and managing all configured tunnel services.
    *   Settings page to change panel login credentials.
*   **Rathole Integration:**
    *   **Panel Hosted Services:** Configure the panel to act as a rathole server, exposing multiple local or network-accessible services through unique public ports.
    *   **Remote Target Services:** Configure the panel to act as a rathole client, connecting to a remote service and exposing it through a rathole server (either the panel's own or an external one).
    *   Automatic token generation (optional).
    *   Start, stop, and remove individual tunnel services.
    *   View status of services and the main rathole server instance.
*   **Automatic Installation (Ubuntu):**
    *   Includes an `install.sh` script to automate setup on Ubuntu systems.
    *   Installs all required dependencies, including the rathole binary.
    *   Sets up the Python Flask application.
    *   Generates a random admin username and password for initial login.
    *   Provides guidance for firewall and systemd service configuration.

## Installation

Ensure you have `git` and `curl` installed (`sudo apt update && sudo apt install -y git curl`).

To download and install the Rathole Web Tunnel Manager on an Ubuntu system, run the installation script:

```
Hypothetical one-liner if install.sh handled cloning (currently it does not):
git clone -b feat/rathole-tunnel-manager-v1 https://github.com/rezaab69/rathole_management.git && cd rathole_management && sudo bash install.sh "$(pwd)"
```

After installation (using the recommended clone-then-run method), the script will display the access URL for the web panel along with the randomly generated admin username and password.

## TODO / Future Enhancements

*   More robust status checking for rathole processes.
*   Utilize rathole's hot-reloading for config changes where possible.
*   Detailed logging viewable in the UI.
*   User-specific tunnels if multi-user support is added.
*   Support for TLS/Noise configuration for rathole transport.
*   Package as a Docker container.
