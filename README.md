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

To download and install the Rathole Web Tunnel Manager on an Ubuntu system, first clone the repository and then run the installation script:

```bash
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git
cd <YOUR_REPO_NAME>
sudo bash install.sh "$(pwd)"
```

**Note:** Replace `<YOUR_USERNAME>` and `<YOUR_REPO_NAME>` with the actual username and repository name once it's on GitHub. The ` "$(pwd)"` part passes the current directory (which should be the repository root) to the install script.

If you want a one-liner to download and execute the install script directly from a specific branch (e.g., `main`) once the repository is public, it's more complex because the script needs access to the other repository files. The recommended method is to clone first. However, a more advanced `install.sh` could potentially handle cloning the repo itself. For now, please use the clone-then-run method above.

<!--
Hypothetical one-liner if install.sh handled cloning (currently it does not):
curl -sSL https://raw.githubusercontent.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>/main/install.sh | sudo bash -s <YOUR_REPO_URL_FOR_CLONING>
-->

After installation (using the recommended clone-then-run method), the script will display the access URL for the web panel along with the randomly generated admin username and password.

## TODO / Future Enhancements

*   More robust status checking for rathole processes.
*   Utilize rathole's hot-reloading for config changes where possible.
*   Detailed logging viewable in the UI.
*   User-specific tunnels if multi-user support is added.
*   Support for TLS/Noise configuration for rathole transport.
*   Package as a Docker container.
