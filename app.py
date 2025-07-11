from flask import Flask, render_template, redirect, url_for, session, request, flash
import os
import secrets # For generating a secure secret key
import database # Our new database module
import rathole_manager # Our new rathole tunnel manager

app = Flask(__name__)

# Generate a secure, random secret key if not set (e.g., in an environment variable)
# For production, this should be set via an environment variable or config file.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))

# Initialize the database (creates table if it doesn't exist)
database.init_db()

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if database.verify_user(username, password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            return render_template('login.html') # Removed error prop
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST']) # Allow POST requests for form submission
def dashboard():
    if 'username' not in session:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        service_name = request.form.get('service_name')
        service_type = request.form.get('service_type') # 'server_service' or 'client_service'
        # Common fields
        token = request.form.get('token') # Optional, can be auto-generated
        if not token: # Auto-generate if not provided by user
            token = rathole_manager.generate_token()

        if service_type == 'server_service':
            server_bind_addr = request.form.get('server_bind_addr')
            if service_name and server_bind_addr:
                if rathole_manager.add_service(name=service_name, service_type=service_type, token=token, server_bind_addr=server_bind_addr):
                    flash(f"Server service '{service_name}' added. Restart main rathole server to apply.", 'success')
                    # Consider auto-restarting main server or providing a button
                    # rathole_manager.stop_main_rathole_server() # Ensure it's stopped before starting with new config
                    # rathole_manager.start_main_rathole_server()
                    # flash(f"Server service '{service_name}' added and main server restarted.", 'success')
                else:
                    flash(f"Failed to add server service '{service_name}'. Check logs.", 'danger')
            else:
                flash("Service Name and Server Bind Address are required for server service.", 'danger')

        elif service_type == 'client_service':
            client_local_addr = request.form.get('client_local_addr')
            client_remote_addr = request.form.get('client_remote_addr') # Rathole server this client connects to
            if service_name and client_local_addr and client_remote_addr:
                if rathole_manager.add_service(name=service_name, service_type=service_type, token=token,
                                             client_local_addr=client_local_addr, client_remote_addr=client_remote_addr):
                    flash(f"Client service '{service_name}' added. You can start it now.", 'success')
                else:
                    flash(f"Failed to add client service '{service_name}'. Check logs.", 'danger')
            else:
                flash("Service Name, Client Local Address, and Client Remote Address are required for client service.", 'danger')
        else:
            flash("Invalid service type selected.", 'danger')
        return redirect(url_for('dashboard'))

    tunnels = rathole_manager.get_all_services()
    # Check status of main rathole server for display
    main_server_running = rathole_manager.is_process_running('main_rathole_server')

    return render_template('dashboard.html', username=session['username'], tunnels=tunnels, main_server_running=main_server_running)

# --- Tunnel Action Routes ---
@app.route('/start_tunnel/<service_name>')
def start_tunnel(service_name):
    if 'username' not in session:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('login'))

    service = rathole_manager.service_configurations.get(service_name)
    print(f"DEBUG: Attempting to start tunnel '{service_name}'. Service details: {service}") # DEBUG LINE
    if not service:
        flash(f"Service '{service_name}' not found.", 'danger')
        return redirect(url_for('dashboard'))

    if service.get('service_type') == 'client_service': # Use .get() for safety
        if rathole_manager.start_rathole_client_service(service_name):
            flash(f"Client service '{service_name}' started.", 'success')
        else:
            flash(f"Failed to start client service '{service_name}'.", 'danger')
    elif service['service_type'] == 'server_service':
        # Server services are managed by the main rathole server instance
        if not rathole_manager.is_process_running('main_rathole_server'):
            if rathole_manager.start_main_rathole_server():
                 flash(f"Main rathole server (handling '{service_name}') started.", 'success')
            else:
                 flash(f"Failed to start main rathole server for '{service_name}'.", 'danger')
        else:
            # If main server is running, server_service should be active.
            # A "restart main server" might be more appropriate here if config changed.
            flash(f"Main rathole server is already running. '{service_name}' should be active if configured correctly.", 'info')
            # To apply changes for a new server_service, the main server usually needs a restart.
            # This "start" action for a server_service might imply "ensure main server is running".
            rathole_manager.update_service_status_in_db(service_name, 'running') # Update status
    else:
        flash(f"Unknown service type for '{service_name}'.", 'danger')
    return redirect(url_for('dashboard'))

@app.route('/stop_tunnel/<service_name>')
def stop_tunnel(service_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    service = rathole_manager.service_configurations.get(service_name)
    if not service:
        flash(f"Service '{service_name}' not found.", 'danger')
        return redirect(url_for('dashboard'))

    if service['service_type'] == 'client_service':
        if rathole_manager.stop_rathole_client_service(service_name):
            flash(f"Client service '{service_name}' stopped.", 'success')
        else:
            flash(f"Failed to stop client service '{service_name}'.", 'danger')
    elif service['service_type'] == 'server_service':
        # Stopping a single server_service typically means stopping the main server,
        # or reconfiguring and restarting it without this service.
        # For simplicity, we can't stop individual server_services without affecting others.
        # A better UI might be "Disable" which removes from config and restarts server.
        flash(f"Stopping individual server services is not directly supported. Stop the main rathole server to stop all server services, or remove the service and restart.", 'warning')
        # Or, if we want "stop" for a server_service to mean "mark as inactive in config and restart server":
        # rathole_manager.update_service_status_in_db(service_name, 'stopped') # Mark as logically stopped
        # rathole_manager.stop_main_rathole_server()
        # rathole_manager.start_main_rathole_server() # Will pick up new config
        # flash(f"Service '{service_name}' marked as stopped and main server restarted.", 'info')
    else:
        flash(f"Unknown service type for '{service_name}'.", 'danger')
    return redirect(url_for('dashboard'))

@app.route('/remove_tunnel/<service_name>')
def remove_tunnel(service_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    if rathole_manager.remove_service(service_name):
        flash(f"Service '{service_name}' removed.", 'success')
        # If a server_service was removed, the main server needs a restart
        # remove_service already prints a message about this.
        # Consider auto-restarting or providing a button.
        # if removed_service_type == 'server_service':
        #     rathole_manager.stop_main_rathole_server()
        #     rathole_manager.start_main_rathole_server()
        #     flash(f"Service '{service_name}' removed and main server restarted.", 'success')
    else:
        flash(f"Failed to remove service '{service_name}'.", 'danger')
    return redirect(url_for('dashboard'))

@app.route('/restart_main_server')
def restart_main_server():
    if 'username' not in session:
        return redirect(url_for('login'))

    flash("Attempting to restart main rathole server...", 'info')
    rathole_manager.stop_main_rathole_server()
    if rathole_manager.start_main_rathole_server():
        flash("Main rathole server restarted successfully.", 'success')
    else:
        flash("Failed to restart main rathole server.", 'danger')
    return redirect(url_for('dashboard'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'username' not in session:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('login'))

    username = session['username']
    message = None # Using flash messages instead
    error = None   # Using flash messages instead

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not database.verify_user(username, current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        elif len(new_password) < 8: # Basic password strength check
            flash('New password must be at least 8 characters long.', 'danger')
        else:
            if database.update_password(username, new_password):
                flash('Password updated successfully!', 'success')
            else:
                flash('Failed to update password. Please try again.', 'danger')
        # Redirect to GET to avoid form resubmission issues
        return redirect(url_for('settings'))


    return render_template('settings.html', username=username)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Function to add initial user, useful for installer
def create_initial_user(username, password):
    if not database.get_user(username):
        if database.add_user(username, password):
            print(f"User '{username}' created successfully.")
            return True
        else:
            print(f"Failed to create user '{username}'.")
            return False
    else:
        print(f"User '{username}' already exists.")
        return True # Or False, depending on desired behavior if user exists

if __name__ == '__main__':
    # Example: Create a default admin user if it doesn't exist (for development)
    # In a real deployment, the installer script would handle this.
    # DO NOT use default credentials in production.
    # if not database.get_user('admin'):
    #     create_initial_user('admin', 'ChangeMeImmediately!')

    # In a production environment, use a proper WSGI server like Gunicorn or uWSGI
    # and set debug=False
    app.run(debug=True, host='0.0.0.0', port=5001)
