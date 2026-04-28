# -*- coding: utf-8 -*-
"""
Repository database module for managing GitHub repository configurations.

This module provides functionality to store and retrieve repository configurations
from a SQLite database instead of environment variables.
"""
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


class RepositoryDB:
    """Manages repository configurations in SQLite database."""
    
    def __init__(self, db_path=None):
        """
        Initialize repository database.
        
        Args:
            db_path: Path to SQLite database file
        """
        if db_path is None:
            # Default to data/repositories.db relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(project_root, "data", "repositories.db")
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create the database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create repositories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                branch TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                ai_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repo_name, branch)
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_repo_name 
            ON repositories(repo_name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_enabled
            ON repositories(enabled)
        """)

        # Create clients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address_line1 TEXT DEFAULT '',
                address_line2 TEXT DEFAULT '',
                gstin TEXT DEFAULT '',
                contact TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized at {}".format(self.db_path))
    
    def add_repository(self, repo_name, branch, enabled=True, ai_enabled=True):
        """
        Add a repository configuration to the database.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            branch: Branch name
            enabled: Whether the repository is enabled
            ai_enabled: Whether AI analysis is enabled for this repo
            
        Returns:
            True if added successfully, False if already exists
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO repositories (repo_name, branch, enabled, ai_enabled)
                VALUES (?, ?, ?, ?)
            """, (repo_name, branch, 1 if enabled else 0, 1 if ai_enabled else 0))
            
            conn.commit()
            logger.info("Added repository: {} (branch: {})".format(repo_name, branch))
            return True
        except sqlite3.IntegrityError:
            logger.warning("Repository already exists: {} (branch: {})".format(repo_name, branch))
            return False
        finally:
            conn.close()
    
    def update_repository(self, repo_name, branch, enabled=None, ai_enabled=None):
        """
        Update a repository configuration.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            branch: Branch name
            enabled: Whether the repository is enabled (None = no change)
            ai_enabled: Whether AI analysis is enabled (None = no change)
            
        Returns:
            True if updated successfully, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        
        if ai_enabled is not None:
            updates.append("ai_enabled = ?")
            params.append(1 if ai_enabled else 0)
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        params.extend([repo_name, branch])
        
        query = f"""
            UPDATE repositories 
            SET {', '.join(updates)}
            WHERE repo_name = ? AND branch = ?
        """
        
        cursor.execute(query, params)
        conn.commit()
        
        updated = cursor.rowcount > 0
        conn.close()
        
        if updated:
            logger.info("Updated repository: {} (branch: {})".format(repo_name, branch))
        else:
            logger.warning("Repository not found: {} (branch: {})".format(repo_name, branch))
        
        return updated
    
    def delete_repository(self, repo_name, branch):
        """
        Delete a repository configuration.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            branch: Branch name
            
        Returns:
            True if deleted successfully, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM repositories 
            WHERE repo_name = ? AND branch = ?
        """, (repo_name, branch))
        
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        
        if deleted:
            logger.info("Deleted repository: {} (branch: {})".format(repo_name, branch))
        else:
            logger.warning("Repository not found: {} (branch: {})".format(repo_name, branch))
        
        return deleted
    
    def get_repositories(self, enabled_only=True):
        """
        Get all repository configurations.
        
        Args:
            enabled_only: If True, only return enabled repositories
            
        Returns:
            List of repository dictionaries with keys: repo, branch, enabled, ai_enabled
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT repo_name, branch, enabled, ai_enabled FROM repositories"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY repo_name, branch"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        repositories = []
        for row in rows:
            repositories.append({
                'repo': row[0],
                'branch': row[1],
                'enabled': bool(row[2]),
                'ai_enabled': bool(row[3])
            })
        
        return repositories
    
    def get_repository(self, repo_name, branch):
        """
        Get a specific repository configuration.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            branch: Branch name
            
        Returns:
            Repository dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT repo_name, branch, enabled, ai_enabled 
            FROM repositories 
            WHERE repo_name = ? AND branch = ?
        """, (repo_name, branch))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'repo': row[0],
                'branch': row[1],
                'enabled': bool(row[2]),
                'ai_enabled': bool(row[3])
            }
        
        return None
    
    def clear_all(self):
        """
        Clear all repository configurations.
        
        Returns:
            Number of repositories deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM repositories")
        conn.commit()
        
        deleted = cursor.rowcount
        conn.close()
        
        logger.info("Cleared all repositories ({} deleted)".format(deleted))
        return deleted
    
    def bulk_import(self, repositories):
        """
        Import multiple repositories at once.
        
        Args:
            repositories: List of repository dicts with keys: repo, branch, enabled, ai_enabled
            
        Returns:
            Tuple of (added_count, skipped_count)
        """
        added = 0
        skipped = 0
        
        for repo in repositories:
            success = self.add_repository(
                repo_name=repo['repo'],
                branch=repo['branch'],
                enabled=repo.get('enabled', True),
                ai_enabled=repo.get('ai_enabled', True)
            )
            
            if success:
                added += 1
            else:
                skipped += 1
        
        logger.info("Bulk import complete: {} added, {} skipped".format(added, skipped))
        return added, skipped

    # ---------------------------------------------------------------------------
    # Client management
    # ---------------------------------------------------------------------------

    def add_client(self, name, address_line1='', address_line2='', gstin='', contact=''):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (name, address_line1, address_line2, gstin, contact)
            VALUES (?, ?, ?, ?, ?)
        """, (name, address_line1, address_line2, gstin, contact))
        conn.commit()
        client_id = cursor.lastrowid
        conn.close()
        return client_id

    def update_client(self, client_id, name, address_line1='', address_line2='', gstin='', contact=''):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clients
            SET name=?, address_line1=?, address_line2=?, gstin=?, contact=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (name, address_line1, address_line2, gstin, contact, client_id))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        return updated

    def delete_client(self, client_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clients WHERE id=?", (client_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def get_clients(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_client(self, client_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
