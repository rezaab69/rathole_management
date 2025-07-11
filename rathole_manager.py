import os
import subprocess
import secrets
import toml
import psutil # For checking if a process is running by PID

# --- Constants ---
# Assume rathole binary is in PATH or specify full path
RATHOLE_EXECUTABLE = "rathole" # Installation script should ensure it's in PATH or a known location
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'instance', 'rathole_configs')
SERVER_CONFIG_FILE = os.path.join(CONFIG_DIR, 'server.toml')
CLIENT_CONFIG_FILE = os.path.join(CONFIG_DIR, 'client.toml') # May not be needed if we run one client per service config

# This will store the state of running rathole processes (PIDs)
# Key: service_name (or a unique ID for the process), Value: PID
# For the main server: 'main_rathole_server'
# For client services: service_name
running_processes = {}

import database # Our database module for persistence

# This will store the configurations of defined services/tunnels, loaded from DB.
# Structure is a dictionary where key is service_name, value is a dict of its properties.
# {
#   "service_name_1": {
#       "id": 1, # from DB
#       "name": "service_name_1",
#       "service_type": "server_service",
#       "token": "secret_token_1",
#       "server_bind_addr": "0.0.0.0:7001",
#       "client_local_addr": null,
#       "client_remote_addr": null,
#       "status": "stopped",
#       "config_path": null
#   },
# }
service_configurations = {} # In-memory cache, populated from DB

def ensure_config_dir():
    """Ensures the rathole configuration directory exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)

def generate_token(length=32):
    """Generates a cryptographically secure random token."""
    return secrets.token_hex(length // 2)

# --- Rathole Server Management ---

def get_main_server_config(listen_addr="0.0.0.0:2333", services_config=None):
    """
    Generates the TOML configuration for the main rathole server.
    `services_config` should be a dictionary for the [server.services] part.
    """
    config = {
        "server": {
            "bind_addr": listen_addr,
            "heartbeat_interval": 30 # Default from rathole docs
        },
        # transport can be added here if needed, e.g. noise or tls
    }
    if services_config:
        config["server"]["services"] = services_config
    return config

def write_server_config(config_data):
    """Writes the server configuration to server.toml."""
    ensure_config_dir()
    with open(SERVER_CONFIG_FILE, 'w') as f:
        toml.dump(config_data, f)
    print(f"Server config written to {SERVER_CONFIG_FILE}")

def start_main_rathole_server():
    """Starts the main rathole server process."""
    if is_process_running('main_rathole_server'):
        print("Main rathole server is already running.")
        return True

    # Assemble server config from all 'server' type services in service_configurations
    server_services_details = {}
    for name, details in service_configurations.items():
        if details.get("type") == "server_service": # Exposed by our panel's server
             server_services_details[name] = {
                "token": details["token"],
                "bind_addr": details["server_bind_addr"]
             }

    if not server_services_details:
        print("No server services configured. Main rathole server will not start with specific services.")
        # Still might want to start a base server if client services need to connect to it.
        # For now, only start if there are services to offer or if we expect clients for our "client" services.
        # Let's assume for now it starts with a base config if it needs to listen for our own client services.
        # This logic needs refinement based on how we manage client services connecting to *this* server.

    main_server_listen_addr = "0.0.0.0:2333" # This should be configurable
    server_config_content = get_main_server_config(listen_addr=main_server_listen_addr, services_config=server_services_details)
    write_server_config(server_config_content)

    try:
        # Using Popen for non-blocking execution
        process = subprocess.Popen([RATHOLE_EXECUTABLE, SERVER_CONFIG_FILE],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={**os.environ, "RUST_LOG": "info"}) # Example logging
        running_processes['main_rathole_server'] = process.pid
        service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'running'
        print(f"Main rathole server started with PID: {process.pid}")
        # TODO: Monitor this process, handle logs, etc.
        return True
    except Exception as e:
        print(f"Error starting main rathole server: {e}")
        service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'error'
        return False

def stop_main_rathole_server():
    """Stops the main rathole server process."""
    pid = running_processes.get('main_rathole_server')
    if pid:
        try:
            proc = psutil.Process(pid)
            proc.terminate() # or proc.kill()
            proc.wait(timeout=5) # Wait for termination
            print(f"Main rathole server (PID: {pid}) stopped.")
            del running_processes['main_rathole_server']
            service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'stopped'
            return True
        except psutil.NoSuchProcess:
            print(f"Main rathole server process (PID: {pid}) not found.")
            del running_processes['main_rathole_server'] # Clean up stale entry
            service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'stopped'
        except psutil.TimeoutExpired:
            print(f"Timeout waiting for main rathole server (PID: {pid}) to terminate. Killing.")
            proc.kill()
            del running_processes['main_rathole_server']
            service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'stopped'
            return True # Or false depending on if kill is considered a clean stop
        except Exception as e:
            print(f"Error stopping main rathole server (PID: {pid}): {e}")
            return False
    else:
        print("Main rathole server is not running or PID not tracked.")
        service_configurations.setdefault('main_rathole_server_meta', {})['status'] = 'stopped' # Ensure status is correct
        return True # Or False, depending on desired strictness

# --- Rathole Client Service Management ---

def get_client_service_config(remote_addr, service_name, token, local_addr):
    """Generates TOML config for a single client service."""
    return {
        "client": {
            "remote_addr": remote_addr, # e.g., "mypanel.com:2333"
            # "heartbeat_timeout": 40, # Optional
            # "retry_interval": 1,   # Optional
        },
        "client.services": {
            service_name: {
                "token": token,
                "local_addr": local_addr # e.g., "127.0.0.1:8000" on the machine running this client
            }
        }
        # transport can be added here if needed
    }

def start_rathole_client_service(service_name):
    """
    Starts a rathole client process for a specific service.
    This implies each client service runs its own rathole instance.
    Alternatively, one client.toml could define multiple services.
    """
    if is_process_running(service_name):
        print(f"Rathole client for service '{service_name}' is already running.")
        return True

    details = service_configurations.get(service_name)
    if not details or details.get("type") != "client_service":
        print(f"Service '{service_name}' not found or not a client service type.")
        return False

    config_content = get_client_service_config(
        remote_addr=details["client_remote_addr"],
        service_name=service_name, # Rathole service name can be different from our internal name
        token=details["token"],
        local_addr=details["client_local_addr"]
    )

    client_service_config_path = os.path.join(CONFIG_DIR, f"client_{service_name}.toml")
    ensure_config_dir()
    with open(client_service_config_path, 'w') as f:
        toml.dump(config_content, f)
    print(f"Client config for '{service_name}' written to {client_service_config_path}")
    details["config_path"] = client_service_config_path


    try:
        process = subprocess.Popen([RATHOLE_EXECUTABLE, "--client", client_service_config_path],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={**os.environ, "RUST_LOG": "info"})
        running_processes[service_name] = process.pid
        details['status'] = 'running'
        print(f"Rathole client for service '{service_name}' started with PID: {process.pid}")
        return True
    except Exception as e:
        print(f"Error starting rathole client for '{service_name}': {e}")
        details['status'] = 'error'
        return False

def stop_rathole_client_service(service_name):
    """Stops a rathole client process for a specific service."""
    pid = running_processes.get(service_name)
    details = service_configurations.get(service_name)

    if pid:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
            print(f"Rathole client for service '{service_name}' (PID: {pid}) stopped.")
            del running_processes[service_name]
            if details: details['status'] = 'stopped'
            return True
        except psutil.NoSuchProcess:
            print(f"Rathole client process for '{service_name}' (PID: {pid}) not found.")
            if service_name in running_processes: del running_processes[service_name]
            if details: details['status'] = 'stopped'
        except psutil.TimeoutExpired:
            print(f"Timeout stopping client '{service_name}' (PID: {pid}). Killing.")
            proc.kill()
            del running_processes[service_name]
            if details: details['status'] = 'stopped'
            return True
        except Exception as e:
            print(f"Error stopping rathole client for '{service_name}' (PID: {pid}): {e}")
            if details: details['status'] = 'error' # Or 'unknown'
            return False
    else:
        print(f"Rathole client for service '{service_name}' is not running or PID not tracked.")
        if details: details['status'] = 'stopped'
        return True


# --- General Service Management ---

def add_service(name, service_type, token, server_bind_addr=None, client_local_addr=None, client_remote_addr=None):
    """
    Adds a new service configuration.
    service_type: 'server_service' (exposed by our panel's rathole server)
                  'client_service' (our panel acts as a rathole client to expose a remote service)
    """
    if name in service_configurations:
        print(f"Service '{name}' already exists.")
        return False

    if not token: # Auto-generate if not provided
        token = generate_token()

    new_service = {
        "name": name, # Store name also inside for easier access
        "type": service_type,
        "token": token,
        "status": "stopped", # Initial status
    }

    if service_type == "server_service":
        if not server_bind_addr:
            print("Error: server_bind_addr is required for server_service type.")
            return False
        new_service["server_bind_addr"] = server_bind_addr
        # This service will be added to the main server.toml
        # The main server needs to be restarted/reloaded for this to take effect
    elif service_type == "client_service":
        if not client_local_addr or not client_remote_addr:
            print("Error: client_local_addr and client_remote_addr are required for client_service type.")
            return False
        new_service["client_local_addr"] = client_local_addr
        new_service["client_remote_addr"] = client_remote_addr
        # This service will run as its own client process with its own config file.
    else:
        print(f"Unknown service type: {service_type}")
        return False

    service_configurations[name] = new_service
    print(f"Service '{name}' ({service_type}) added with token '{token}'.")

    # Persist service_configurations to DB here in a real app
    save_all_service_configs_to_db() # Placeholder

    # If it's a server service, the main server config needs to be updated and restarted
    if service_type == "server_service":
        print("Main rathole server needs to be restarted to apply changes for new server_service.")
        # reload_main_rathole_server() # Implement reload or restart
    return True


def remove_service(name):
    """Removes a service configuration and stops it if running."""
    if name not in service_configurations:
        print(f"Service '{name}' not found.")
        return False

    details = service_configurations[name]
    if details['status'] == 'running':
        if details['type'] == 'client_service':
            stop_rathole_client_service(name)
        elif details['type'] == 'server_service':
            # Removing a server service requires stopping/reconfiguring the main server
            print(f"Service '{name}' is a server_service. Stopping main server to remove.")
            stop_main_rathole_server()
            # Then, when server restarts, this service won't be in its config

    # Remove from configurations
    del service_configurations[name]
    print(f"Service '{name}' removed.")

    # Persist changes to DB
    save_all_service_configs_to_db() # Placeholder

    # If it was a server service, the main server config needs to be updated and potentially restarted
    if details['type'] == "server_service":
        print("Main rathole server needs to be restarted without the removed service.")
        # start_main_rathole_server() # Or a more graceful reload
    return True

def get_service_status(name):
    """Gets the status of a service."""
    details = service_configurations.get(name)
    if not details:
        return "not_found"

    # Update status based on running process if not already accurate
    if is_process_running(name if details['type'] == 'client_service' else 'main_rathole_server'):
        if details['status'] != 'running': # If our record is out of sync
             details['status'] = 'running'
    else:
        if details['status'] == 'running': # If our record says running but process isn't
            details['status'] = 'error' # Or 'stopped' if it was a clean stop we missed
            if name in running_processes: # Clean up stale PID
                del running_processes[name]


    return details['status']

def get_all_services():
    """Returns all configured services and their statuses."""
    # Ensure statuses are up-to-date
    for name in list(service_configurations.keys()): # list() for safe iteration if modified
        if name == 'main_rathole_server_meta': continue
        get_service_status(name) # This updates the status in service_configurations
    return service_configurations

def is_process_running(process_key_name):
    """Checks if a process associated with process_key_name is running."""
    pid = running_processes.get(process_key_name)
    if pid:
        return psutil.pid_exists(pid)
    return False

# --- Persistence (Placeholder - should use the database module) ---
# For now, let's simulate with a JSON file or just keep in memory for dev
DB_FILE_SIMULATOR = os.path.join(CONFIG_DIR, 'services_db.json')

def load_all_service_configs_from_db():
    """Placeholder: Loads service configurations from a simulated DB (JSON file)."""
    global service_configurations
    ensure_config_dir()
    try:
        if os.path.exists(DB_FILE_SIMULATOR):
            with open(DB_FILE_SIMULATOR, 'r') as f:
                service_configurations = json.load(f)
                # Ensure status is reset for processes that aren't actually running
                for name, details in service_configurations.items():
                    if name != 'main_rathole_server_meta': # Special key for server status
                        if not is_process_running(name if details.get('type') == 'client_service' else 'main_rathole_server'):
                            details['status'] = 'stopped'
                            if name in running_processes:
                                del running_processes[name]
                print("Service configurations loaded from simulated DB.")
        else:
            service_configurations = {} # Initialize if no file
            print("No simulated DB file found, starting with empty service configurations.")

    except Exception as e:
        print(f"Error loading service configurations from simulated DB: {e}")
        service_configurations = {}


def save_all_service_configs_to_db():
    """Placeholder: Saves all service configurations to a simulated DB (JSON file)."""
    ensure_config_dir()
    try:
        # Prune any non-persistent data from details before saving if necessary
        # e.g., live PIDs if they are not meant to be persisted directly
        with open(DB_FILE_SIMULATOR, 'w') as f:
            # A bit hacky to import json here, better at top
            import json
            json.dump(service_configurations, f, indent=2)
        print("Service configurations saved to simulated DB.")
    except Exception as e:
        print(f"Error saving service configurations to simulated DB: {e}")


# --- Initialization ---
if __name__ == '__main__':
    ensure_config_dir()
    load_all_service_configs_from_db() # Load existing configs on module start

    print("Rathole Manager Initialized.")
    # Example Usage (for testing this module directly):
    # print("Adding example server service...")
    # add_service("my_web_server", "server_service", token="supersecret1", server_bind_addr="0.0.0.0:8080")

    # print("\nAdding example client service...")
    # add_service("remote_ssh_via_panel", "client_service",
    #             token="supersecret2", # This token should match a service on the rathole server
    #             client_local_addr="127.0.0.1:22", # What to connect to on the machine running this client instance
    #             client_remote_addr="YOUR_PANEL_PUBLIC_IP_OR_DOMAIN:2333") # The rathole server it connects to

    # print("\nCurrent Services:")
    # print(get_all_services())

    # print("\nStarting main rathole server...")
    # start_main_rathole_server()
    # print(f"Main server status: {get_service_status('main_rathole_server_meta')}")


    # print("\nStarting client service 'remote_ssh_via_panel'...")
    # if "remote_ssh_via_panel" in service_configurations:
    #    start_rathole_client_service("remote_ssh_via_panel")
    #    print(f"Service remote_ssh_via_panel status: {get_service_status('remote_ssh_via_panel')}")

    # print("\nStopping client service 'remote_ssh_via_panel'...")
    # if "remote_ssh_via_panel" in service_configurations:
    #    stop_rathole_client_service("remote_ssh_via_panel")
    #    print(f"Service remote_ssh_via_panel status: {get_service_status('remote_ssh_via_panel')}")

    # print("\nStopping main rathole server...")
    # stop_main_rathole_server()
    # print(f"Main server status: {get_service_status('main_rathole_server_meta')}")

    # print("\nRemoving services...")
    # remove_service("my_web_server")
    # remove_service("remote_ssh_via_panel")

    # print("\nFinal Services:")
    # print(get_all_services())

    # save_all_service_configs_to_db()
else:
    # When imported, load configurations
    ensure_config_dir()
    load_all_service_configs_from_db()
