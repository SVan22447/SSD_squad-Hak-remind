import sqlite3
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name="bot_database.db"):
        """Initialize the database connection and create tables if they don't exist."""
        self.db_name = db_name
        self.conn = None
        self.create_tables()

    def connect(self):
        """Establish a connection to the database."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            return self.conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            return None

    def create_tables(self):
        """Create the Teams and Reminders tables if they don't exist."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Create Teams table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                members TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create Reminders table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_time TIMESTAMP NOT NULL,
                team_name TEXT,
                reminder_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            conn.commit()
            logger.info("Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
        finally:
            if conn:
                conn.close()

    def add_team(self, name, members, created_by):
        """Add a new team to the database.
        
        Args:
            name (str): Name of the team
            members (list): List of user IDs who are members of the team
            created_by (int): User ID of team creator
            
        Returns:
            bool: Success or failure
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Convert members list to JSON string
            members_json = ','.join(map(str, members))
            
            cursor.execute(
                "INSERT INTO teams (name, members, created_by) VALUES (?, ?, ?)",
                (name, members_json, created_by)
            )
            
            conn.commit()
            logger.info(f"Team '{name}' added to database")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding team: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_teams(self, user_id=None):
        """Get all teams or teams where the user is a member.
        
        Args:
            user_id (int, optional): Filter teams by user ID membership
            
        Returns:
            list: List of team dictionaries
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            if user_id:
                # Get teams where user is a member or creator
                cursor.execute("SELECT * FROM teams")
                all_teams = cursor.fetchall()
                
                # Filter teams where user is a member
                teams = []
                for team in all_teams:
                    team_id, name, members_str, created_by, created_at = team
                    members = list(map(int, members_str.split(',')))
                    
                    if user_id in members or user_id == created_by:
                        teams.append({
                            'id': team_id,
                            'name': name,
                            'members': members,
                            'created_by': created_by,
                            'created_at': created_at
                        })
                
                return teams
            else:
                # Get all teams
                cursor.execute("SELECT * FROM teams")
                teams = []
                for team in cursor.fetchall():
                    team_id, name, members_str, created_by, created_at = team
                    members = list(map(int, members_str.split(',')))
                    
                    teams.append({
                        'id': team_id,
                        'name': name,
                        'members': members,
                        'created_by': created_by,
                        'created_at': created_at
                    })
                
                return teams
        except sqlite3.Error as e:
            logger.error(f"Error getting teams: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_reminder(self, user_id, reminder_time, reminder_text, team_name=None):
        """Add a new reminder to the database.
        
        Args:
            user_id (int): User ID of the reminder creator
            reminder_time (str): Time for the reminder in ISO format
            reminder_text (str): Text of the reminder
            team_name (str, optional): Team name if it's a team reminder
            
        Returns:
            bool: Success or failure
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO reminders (user_id, reminder_time, team_name, reminder_text) VALUES (?, ?, ?, ?)",
                (user_id, reminder_time, team_name, reminder_text)
            )
            
            conn.commit()
            logger.info(f"Reminder added for user {user_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding reminder: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_reminders(self, user_id=None, team_name=None):
        """Get reminders for a user or team.
        
        Args:
            user_id (int, optional): Filter reminders by user ID
            team_name (str, optional): Filter reminders by team name
            
        Returns:
            list: List of reminder dictionaries
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            if user_id and team_name:
                # Get reminders for a specific user in a specific team
                cursor.execute(
                    "SELECT * FROM reminders WHERE user_id = ? AND team_name = ?",
                    (user_id, team_name)
                )
            elif user_id:
                # Get personal reminders for a user (where team_name is NULL or empty)
                cursor.execute(
                    "SELECT * FROM reminders WHERE user_id = ? AND (team_name IS NULL OR team_name = '')",
                    (user_id,)
                )
            elif team_name:
                # Get all reminders for a team
                cursor.execute(
                    "SELECT * FROM reminders WHERE team_name = ?",
                    (team_name,)
                )
            else:
                # Get all reminders
                cursor.execute("SELECT * FROM reminders")
            
            reminders = []
            for reminder in cursor.fetchall():
                reminder_id, user_id, reminder_time, team_name, reminder_text, created_at = reminder
                
                reminders.append({
                    'id': reminder_id,
                    'user_id': user_id,
                    'reminder_time': reminder_time,
                    'team_name': team_name,
                    'reminder_text': reminder_text,
                    'created_at': created_at
                })
            
            return reminders
        except sqlite3.Error as e:
            logger.error(f"Error getting reminders: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
