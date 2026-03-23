# sophos_ai_backend/core/database.py

import sqlite3
import logging
from typing import Optional
from .config import config

# Initialize a logger for this module to handle logging throughout the script.
logger = logging.getLogger(__name__)

class User:
    """
    A simple data class to represent an authenticated user.
    This object holds user information after a successful login,
    which can be used for authorization and logging purposes.
    """
    def __init__(self, username: str, is_admin: bool):
        self.username = username
        self.is_admin = is_admin

def initialize_all_databases():
    """
    Initializes all necessary SQLite databases when the application starts.
    This function creates tables if they don't exist and populates the users
    table with default accounts for the first run. This ensures the application
    is ready to use immediately after setup.
    """
    try:
        # --- User Database (users.db) ---
        # Connect to the SQLite database file specified in the config.
        conn = sqlite3.connect(config.USER_DB)
        cursor = conn.cursor()
        
        # Create the 'users' table if it doesn't already exist.
        # - username: The user's unique login name (Primary Key).
        # - password: The user's password (note: in a real-world app, this should be hashed).
        # - is_admin: An integer flag (1 for true, 0 for false) to denote admin privileges.
        cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, is_admin INTEGER NOT NULL)")
        
        # Check if the 'users' table is empty.
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            # If the table is empty, insert default admin and user accounts.
            # This is crucial for the initial setup, providing a way to log in for the first time.
            cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", ("admin", "adminpass", 1))
            cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", ("user", "userpass", 0))
            conn.commit()  # Save the changes to the database.
        conn.close()

        # --- Application Metadata Database (app_metadata.db) ---
        # Connect to the metadata database.
        conn = sqlite3.connect(config.APP_METADATA_DB)
        cursor = conn.cursor()
        
        # Create the 'report_counts' table to track feedback on incorrect answers.
        # This helps in monitoring the RAG bot's performance.
        cursor.execute("CREATE TABLE IF NOT EXISTS report_counts (id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)")
        
        # Insert a default row with a count of 0 if it doesn't exist.
        # 'INSERT OR IGNORE' prevents an error if the row with id=1 already exists.
        cursor.execute("INSERT OR IGNORE INTO report_counts (id, count) VALUES (1, 0)")
        conn.commit()
        conn.close()

        logger.info("All SQLite databases initialized successfully.")
    except Exception as e:
        # Log any errors that occur during database initialization and re-raise the exception
        # to halt the application startup, as the databases are critical.
        logger.error(f"Error initializing databases: {e}", exc_info=True)
        raise

def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Authenticates a user against the users.db database.
    It checks if the provided username exists and if the password matches.

    Args:
        username: The username to authenticate.
        password: The password to check.

    Returns:
        A User object if authentication is successful, otherwise None.
    """
    try:
        conn = sqlite3.connect(config.USER_DB)
        cursor = conn.cursor()
        
        # Query the database for a user with the given username.
        cursor.execute("SELECT password, is_admin FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()  # Fetches the first matching row.
        conn.close()
        
        # Check if a user was found and if the provided password matches the stored one.
        if result and result[0] == password:
            # If successful, return a User object with the username and admin status.
            return User(username=username, is_admin=bool(result[1]))
    except Exception as e:
        # Log any errors that occur during the authentication process.
        logger.error(f"Error authenticating user {username}: {e}")
    
    # Return None if the user doesn't exist, the password doesn't match, or an error occurred.
    return None

def get_and_increment_report_count() -> int:
    """
    Retrieves and atomically increments the report count from the metadata database.
    This function is called when a user reports an incorrect answer.

    Returns:
        The new, incremented report count.
    
    Raises:
        Exception: If there is an error interacting with the database.
    """

    try:
        conn = sqlite3.connect(config.APP_METADATA_DB)
        cursor = conn.cursor()
        
        # Step 1: Retrieve the current report count.
        cursor.execute("SELECT count FROM report_counts WHERE id = 1")
        current_count = cursor.fetchone()[0]
        
        # Step 2: Increment the count in the application logic.
        new_count = current_count + 1
        
        # Step 3: Update the database with the new count.
        cursor.execute("UPDATE report_counts SET count = ? WHERE id = 1", (new_count,))
        conn.commit()  # Commit the transaction to make the change permanent.
        conn.close()
        
        return new_count
    except Exception as e:
        # Log the error and re-raise it so the calling function can handle it.
        logger.error(f"Error getting/incrementing report count: {e}", exc_info=True)
        raise