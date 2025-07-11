import sqlite3
import bcrypt
import os

DATABASE_DIR = os.path.join(os.path.dirname(__file__), 'instance')
DATABASE_PATH = os.path.join(DATABASE_DIR, 'users.db')

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates the users table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tunnels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            service_type TEXT NOT NULL, -- 'server_service' or 'client_service'
            token TEXT NOT NULL,
            server_bind_addr TEXT,    -- For 'server_service'
            client_local_addr TEXT,   -- For 'client_service'
            client_remote_addr TEXT,  -- For 'client_service' (rathole server to connect to)
            status TEXT DEFAULT 'stopped', -- 'running', 'stopped', 'error'
            config_path TEXT,         -- Path to specific client config, if applicable
            user_id INTEGER,          -- Optional: if tunnels are user-specific
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

def add_user(username, password):
    """Adds a new user to the database with a hashed password."""
    if get_user(username):
        return False # User already exists

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password.decode('utf-8')))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # Should be caught by get_user check, but as a safeguard
        return False
    finally:
        conn.close()

def verify_user(username, password):
    """Verifies a user's credentials against the stored hash."""
    user = get_user(username)
    if user:
        password_hash = user['password_hash'].encode('utf-8')
        if bcrypt.checkpw(password.encode('utf-8'), password_hash):
            return True
    return False

def get_user(username):
    """Retrieves a user by username."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_password(username, new_password):
    """Updates a user's password."""
    user = get_user(username)
    if not user:
        return False # User not found

    new_hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hashed_password.decode('utf-8'), username))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating password: {e}") # For logging
        return False
    finally:
        conn.close()

if __name__ == '__main__':
# --- Tunnel Configuration CRUD ---

def add_tunnel_config(name, service_type, token, server_bind_addr=None, client_local_addr=None, client_remote_addr=None, status='stopped', config_path=None, user_id=None):
    """Adds a new tunnel configuration to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO tunnels (name, service_type, token, server_bind_addr, client_local_addr, client_remote_addr, status, config_path, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, service_type, token, server_bind_addr, client_local_addr, client_remote_addr, status, config_path, user_id))
        conn.commit()
        print(f"Tunnel '{name}' added to database.")
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        print(f"Error: Tunnel with name '{name}' already exists in database.")
        return None
    except Exception as e:
        print(f"Database error adding tunnel {name}: {e}")
        return None
    finally:
        conn.close()

def get_tunnel_config(name):
    """Retrieves a tunnel configuration by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tunnels WHERE name = ?", (name,))
    tunnel_data = cursor.fetchone()
    conn.close()
    return dict(tunnel_data) if tunnel_data else None

def get_all_tunnel_configs():
    """Retrieves all tunnel configurations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tunnels")
    tunnels_data = cursor.fetchall()
    conn.close()
    return [dict(row) for row in tunnels_data]

def update_tunnel_config(name, updates: dict):
    """
    Updates specified fields for a tunnel configuration.
    `updates` is a dictionary of column_name: new_value.
    """
    if not updates:
        return False

    fields = []
    values = []
    for key, value in updates.items():
        # Basic protection against SQL injection by ensuring keys are valid column names
        # A more robust solution would be an ORM or more strict validation
        if key in ['service_type', 'token', 'server_bind_addr', 'client_local_addr', 'client_remote_addr', 'status', 'config_path', 'user_id']:
            fields.append(f"{key} = ?")
            values.append(value)
        else:
            print(f"Warning: Invalid field '{key}' specified for tunnel update.")

    if not fields:
        print("No valid fields to update.")
        return False

    values.append(name) # For the WHERE clause

    sql = f"UPDATE tunnels SET {', '.join(fields)} WHERE name = ?"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, tuple(values))
        conn.commit()
        if cursor.rowcount == 0:
            print(f"No tunnel found with name '{name}' to update.")
            return False
        print(f"Tunnel '{name}' updated in database.")
        return True
    except Exception as e:
        print(f"Database error updating tunnel {name}: {e}")
        return False
    finally:
        conn.close()

def delete_tunnel_config(name):
    """Deletes a tunnel configuration by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM tunnels WHERE name = ?", (name,))
        conn.commit()
        if cursor.rowcount == 0:
            print(f"No tunnel found with name '{name}' to delete.")
            return False
        print(f"Tunnel '{name}' deleted from database.")
        return True
    except Exception as e:
        print(f"Database error deleting tunnel {name}: {e}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    # For testing and initial setup
    print("Initializing database...")
    init_db() # This will now also create/ensure the tunnels table
    print("Database initialized.")

    # --- Example Usage for Tunnel Configs (run this file directly to test) ---
    # print("\n--- Testing Tunnel Configs ---")
    # # Clean up before test
    # if get_tunnel_config("test_server_tunnel"):
    #     delete_tunnel_config("test_server_tunnel")
    # if get_tunnel_config("test_client_tunnel"):
    #     delete_tunnel_config("test_client_tunnel")

    # # Add server tunnel
    # add_tunnel_config(
    #     name="test_server_tunnel",
    #     service_type="server_service",
    #     token="server_token_123",
    #     server_bind_addr="0.0.0.0:9001"
    # )
    # # Add client tunnel
    # add_tunnel_config(
    #     name="test_client_tunnel",
    #     service_type="client_service",
    #     token="client_token_456",
    #     client_local_addr="127.0.0.1:80",
    #     client_remote_addr="mypanel.example.com:2333"
    # )

    # print("\nAll tunnels after adding:")
    # for tunnel in get_all_tunnel_configs():
    #     print(tunnel)

    # print("\nGet specific tunnel 'test_server_tunnel':")
    # print(get_tunnel_config("test_server_tunnel"))

    # print("\nUpdate 'test_server_tunnel' status:")
    # update_tunnel_config("test_server_tunnel", {"status": "running", "token": "new_server_token"})
    # print(get_tunnel_config("test_server_tunnel"))

    # print("\nUpdate non-existent tunnel:")
    # update_tunnel_config("non_existent_tunnel", {"status": "error"})


    # print("\nDelete 'test_client_tunnel':")
    # delete_tunnel_config("test_client_tunnel")

    # print("\nAll tunnels after deleting one:")
    # for tunnel in get_all_tunnel_configs():
    #     print(tunnel)

    # # Clean up test data
    # delete_tunnel_config("test_server_tunnel")
    # print("\nCleaned up test tunnels.")
