# -*- coding: utf-8 -*-
"""
Repository database module for managing GitHub repository configurations.

This module provides functionality to store and retrieve repository configurations
from a SQLite database instead of environment variables.

When ``sqlcipher3`` is installed and an encryption password is available (via
``db_security``), the database is transparently encrypted at rest with AES-256.
If ``sqlcipher3`` is not installed the module falls back to plain ``sqlite3``.
"""
import os
import shutil
import logging
import json
import binascii
from datetime import datetime

try:
    import sqlcipher3 as _db_module
    _HAS_SQLCIPHER = True
except ImportError:
    import sqlite3 as _db_module
    _HAS_SQLCIPHER = False

logger = logging.getLogger(__name__)

# Re-export common exception/row classes so the rest of the module body can
# reference them without caring which backend is active.
_DatabaseError = _db_module.DatabaseError
_OperationalError = _db_module.OperationalError
_IntegrityError = _db_module.IntegrityError
_Row = _db_module.Row

SQLITE_MAGIC = b"SQLite format 3\x00"


def is_plaintext_db(path):
    """Return True if *path* starts with the standard SQLite header."""
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as fh:
        return fh.read(16) == SQLITE_MAGIC

DEFAULT_AMC_SETTINGS = {
    "provider_name": "Example Company",
    "provider_owner_name": "Example Owner",
    "provider_signatory_title": "Proprietor",
    "provider_address": "123 Example Street, Example City",
    "provider_email": "billing@example.com",
    "provider_phone": "+1-202-555-0100",
    "provider_website": "https://example.com/",
    "term_months": "12",
    "payment_schedule": "Annual payment due within 15 days of invoice",
    "jurisdiction": "Ahmedabad, Gujarat, India",
    "default_response_time": "Initial response within two business days",
    "renewal_policy": "Renewal requires written agreement by both parties",
    "notice_period_days": "30",
    "include_bank_details": False,
    "bank_details": "",
}


class RepositoryDB:
    """Manages repository configurations in SQLite database."""

    def __init__(self, db_path=None, password=None):
        """
        Initialize repository database.

        Args:
            db_path: Path to SQLite database file.
            password: SQLCipher encryption password.  If None, the password
                is automatically fetched from ``db_security`` (keyring).  If
                no password is available and sqlcipher3 is installed, the DB
                is opened in plaintext mode for backward compatibility.
        """
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(project_root, "data", "repositories.db")
        self.db_path = db_path

        # Resolve encryption password.
        if password is not None:
            self._password = password
        elif _HAS_SQLCIPHER:
            from src.core.db_security import get_password
            self._password = get_password()
        else:
            self._password = None

        # Auto-migrate plaintext DB to encrypted if we have a password.
        if self._password and _HAS_SQLCIPHER and is_plaintext_db(self.db_path):
            logger.info("Auto-migrating plaintext database to encrypted.")
            self._encrypt_in_place(self._password)

        self._init_database()

    @property
    def is_encrypted(self):
        """True when this instance is using SQLCipher encryption."""
        return self._password is not None and _HAS_SQLCIPHER

    def _connect(self):
        """Open a connection to the database, applying the encryption key
        if one is set."""
        conn = _db_module.connect(self.db_path)
        if self._password and _HAS_SQLCIPHER:
            hex_key = binascii.hexlify(self._password.encode()).decode()
            conn.execute("PRAGMA key = \"x'{}'\"".format(hex_key))
        return conn
    
    def _init_database(self):
        """Create the database tables if they don't exist."""
        conn = self._connect()
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

        self._ensure_columns(cursor, "clients", {
            "contact_person": "TEXT DEFAULT ''",
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "website": "TEXT DEFAULT ''",
            "signatory_name": "TEXT DEFAULT ''",
            "signatory_title": "TEXT DEFAULT ''",
        })

        # Maps a repository to the client it belongs to. Keyed on repo_name
        # (not repo+branch) so every tracked branch of a repo shares one
        # client, and so a repo can only ever belong to a single client.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_repositories (
                repo_name TEXT PRIMARY KEY,
                client_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_repositories_client
            ON client_repositories(client_id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS amc_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'drafting',
                input_json TEXT NOT NULL,
                draft_json TEXT DEFAULT '',
                model TEXT DEFAULT '',
                prompt_version TEXT DEFAULT '',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost REAL DEFAULT 0,
                output_filename TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS amc_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                revision_no INTEGER NOT NULL,
                instruction TEXT DEFAULT '',
                draft_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contract_id) REFERENCES amc_contracts(id),
                UNIQUE(contract_id, revision_no)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized at {}".format(self.db_path))

    @staticmethod
    def _ensure_columns(cursor, table_name, columns):
        """Add backward-compatible columns to an existing SQLite table."""
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing = {row[1] for row in cursor.fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"
                )
    
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
        conn = self._connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO repositories (repo_name, branch, enabled, ai_enabled)
                VALUES (?, ?, ?, ?)
            """, (repo_name, branch, 1 if enabled else 0, 1 if ai_enabled else 0))
            
            conn.commit()
            logger.info("Added repository: {} (branch: {})".format(repo_name, branch))
            return True
        except _IntegrityError:
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
        conn = self._connect()
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
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM repositories 
            WHERE repo_name = ? AND branch = ?
        """, (repo_name, branch))
        deleted = cursor.rowcount > 0

        # Drop the client mapping once the last branch of this repo is gone.
        cursor.execute(
            "SELECT COUNT(*) FROM repositories WHERE repo_name = ?", (repo_name,)
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "DELETE FROM client_repositories WHERE repo_name = ?", (repo_name,)
            )

        conn.commit()
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
            List of repository dictionaries with keys: repo, branch, enabled,
            ai_enabled, client_id, client_name. The client fields are None
            when the repository has not been assigned to a client.
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        query = """
            SELECT r.repo_name, r.branch, r.enabled, r.ai_enabled,
                   c.id, c.name
            FROM repositories r
            LEFT JOIN client_repositories cr ON cr.repo_name = r.repo_name
            LEFT JOIN clients c ON c.id = cr.client_id
        """
        if enabled_only:
            query += " WHERE r.enabled = 1"
        query += " ORDER BY r.repo_name, r.branch"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        repositories = []
        for row in rows:
            repositories.append({
                'repo': row[0],
                'branch': row[1],
                'enabled': bool(row[2]),
                'ai_enabled': bool(row[3]),
                'client_id': row[4],
                'client_name': row[5],
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
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.repo_name, r.branch, r.enabled, r.ai_enabled, c.id, c.name
            FROM repositories r
            LEFT JOIN client_repositories cr ON cr.repo_name = r.repo_name
            LEFT JOIN clients c ON c.id = cr.client_id
            WHERE r.repo_name = ? AND r.branch = ?
        """, (repo_name, branch))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'repo': row[0],
                'branch': row[1],
                'enabled': bool(row[2]),
                'ai_enabled': bool(row[3]),
                'client_id': row[4],
                'client_name': row[5],
            }
        
        return None
    
    def clear_all(self):
        """
        Clear all repository configurations.
        
        Returns:
            Number of repositories deleted
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM repositories")
        deleted = cursor.rowcount
        cursor.execute("DELETE FROM client_repositories")
        conn.commit()
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

    def add_client(
        self,
        name,
        address_line1='',
        address_line2='',
        gstin='',
        contact='',
        contact_person='',
        email='',
        phone='',
        website='',
        signatory_name='',
        signatory_title='',
    ):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (
                name, address_line1, address_line2, gstin, contact,
                contact_person, email, phone, website,
                signatory_name, signatory_title
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, address_line1, address_line2, gstin, contact,
            contact_person, email, phone, website,
            signatory_name, signatory_title,
        ))
        conn.commit()
        client_id = cursor.lastrowid
        conn.close()
        return client_id

    def update_client(
        self,
        client_id,
        name,
        address_line1='',
        address_line2='',
        gstin='',
        contact='',
        contact_person='',
        email='',
        phone='',
        website='',
        signatory_name='',
        signatory_title='',
    ):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clients
            SET name=?, address_line1=?, address_line2=?, gstin=?, contact=?,
                contact_person=?, email=?, phone=?, website=?,
                signatory_name=?, signatory_title=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            name, address_line1, address_line2, gstin, contact,
            contact_person, email, phone, website,
            signatory_name, signatory_title, client_id,
        ))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        return updated

    def delete_client(self, client_id):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM client_repositories WHERE client_id=?", (client_id,)
        )
        cursor.execute("DELETE FROM clients WHERE id=?", (client_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def get_clients(self):
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_client(self, client_id):
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    # ---------------------------------------------------------------------------
    # Client <-> repository mapping
    # ---------------------------------------------------------------------------

    def set_client_repositories(self, client_id, repo_names):
        """Make *repo_names* the exact set of repositories owned by *client_id*.

        Repositories previously owned by this client but absent from
        *repo_names* are unassigned. Repositories currently owned by another
        client are reassigned to this one, since a repo has a single owner.

        Returns the number of repositories now mapped to the client.
        """
        repo_names = list(dict.fromkeys(repo_names))
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM client_repositories WHERE client_id=?", (client_id,)
        )
        for repo_name in repo_names:
            cursor.execute("""
                INSERT INTO client_repositories (repo_name, client_id)
                VALUES (?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET client_id=excluded.client_id
            """, (repo_name, client_id))
        conn.commit()
        conn.close()
        logger.info(
            "Client %s now owns %d repositories", client_id, len(repo_names)
        )
        return len(repo_names)

    def assign_repository_to_client(self, repo_name, client_id):
        """Assign a single repository to a client, or unassign when
        *client_id* is falsy. Moves the repo if it belonged to someone else."""
        conn = self._connect()
        cursor = conn.cursor()
        if client_id:
            cursor.execute("""
                INSERT INTO client_repositories (repo_name, client_id)
                VALUES (?, ?)
                ON CONFLICT(repo_name) DO UPDATE SET client_id=excluded.client_id
            """, (repo_name, client_id))
        else:
            cursor.execute(
                "DELETE FROM client_repositories WHERE repo_name=?", (repo_name,)
            )
        conn.commit()
        conn.close()
        return True

    def get_repository_client_map(self):
        """Return {repo_name: {'client_id': int, 'client_name': str}}."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cr.repo_name, c.id, c.name
            FROM client_repositories cr
            JOIN clients c ON c.id = cr.client_id
        """)
        rows = cursor.fetchall()
        conn.close()
        return {
            row[0]: {"client_id": row[1], "client_name": row[2]} for row in rows
        }

    def get_clients_with_repositories(self):
        """Return all clients, each with a sorted ``repos`` list of the
        repository names assigned to them."""
        clients = self.get_clients()
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT client_id, repo_name FROM client_repositories "
            "ORDER BY repo_name"
        )
        by_client = {}
        for client_id, repo_name in cursor.fetchall():
            by_client.setdefault(client_id, []).append(repo_name)
        conn.close()
        for client in clients:
            client["repos"] = by_client.get(client["id"], [])
        return clients

    # ---------------------------------------------------------------------------
    # AMC settings and contract persistence
    # ---------------------------------------------------------------------------

    def get_runtime_settings(self, defaults=None):
        """Return persisted GUI runtime overrides merged over supplied defaults."""
        settings = dict(defaults or {})
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value_json FROM app_settings WHERE key='runtime_settings'"
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            try:
                stored = json.loads(row[0])
                if isinstance(stored, dict):
                    settings.update(stored)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Ignoring invalid stored runtime settings")
        return settings

    def save_runtime_settings(self, settings):
        """Persist validated GUI runtime settings."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES ('runtime_settings', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP
        """, (json.dumps(settings, ensure_ascii=False),))
        conn.commit()
        conn.close()
        return dict(settings)

    # ------------------------------------------------------------------
    # Login password (hashed, stored in app_settings)
    # ------------------------------------------------------------------
    def get_login_password_hash(self):
        """Return the stored login password hash, or None if not set."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value_json FROM app_settings WHERE key='login_password_hash'"
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            try:
                data = json.loads(row[0])
                return data.get("hash", "")
            except (TypeError, json.JSONDecodeError):
                return ""
        return None

    def set_login_password(self, password_hash):
        """Store a login password hash."""
        conn = self._connect()
        cursor = conn.cursor()
        payload = json.dumps({"hash": password_hash}, ensure_ascii=False)
        cursor.execute("""
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES ('login_password_hash', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP
        """, (payload,))
        conn.commit()
        conn.close()

    def has_login_password(self):
        """Return True if a login password hash has been stored."""
        return bool(self.get_login_password_hash())

    def record_ai_usage(
        self,
        feature,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0,
    ):
        """Record one completed AI operation for the monthly budget guardrail."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_usage (
                feature, input_tokens, output_tokens, estimated_cost
            )
            VALUES (?, ?, ?, ?)
        """, (
            str(feature),
            int(input_tokens or 0),
            int(output_tokens or 0),
            float(estimated_cost or 0),
        ))
        conn.commit()
        conn.close()

    def get_monthly_ai_usage(self):
        """Return aggregate AI usage for the current SQLite calendar month."""
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimated_cost), 0) AS estimated_cost,
                COUNT(*) AS operations
            FROM ai_usage
            WHERE created_at >= datetime('now', 'start of month')
              AND created_at < datetime('now', 'start of month', '+1 month')
        """)
        row = cursor.fetchone()
        conn.close()
        return dict(row)

    def get_amc_settings(self):
        settings = dict(DEFAULT_AMC_SETTINGS)
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value_json FROM app_settings WHERE key='amc_defaults'")
        row = cursor.fetchone()
        conn.close()
        if row:
            try:
                stored = json.loads(row[0])
                if isinstance(stored, dict):
                    settings.update(stored)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Ignoring invalid stored AMC settings")
        return settings

    def save_amc_settings(self, settings):
        # Support separate company-details and AMC-default forms without one
        # resetting fields owned by the other.
        merged = self.get_amc_settings()
        merged.update(settings)
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES ('amc_defaults', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP
        """, (json.dumps(merged, ensure_ascii=False),))
        conn.commit()
        conn.close()
        return merged

    def create_amc_contract(
        self,
        client_id,
        input_data,
        model='',
        prompt_version='',
    ):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO amc_contracts (
                client_id, status, input_json, model, prompt_version
            )
            VALUES (?, 'drafting', ?, ?, ?)
        """, (
            client_id,
            json.dumps(input_data, ensure_ascii=False),
            model,
            prompt_version,
        ))
        contract_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return contract_id

    def update_amc_contract(self, contract_id, **values):
        allowed = {
            "status", "input_json", "draft_json", "model", "prompt_version",
            "input_tokens", "output_tokens", "estimated_cost",
            "output_filename", "error_message",
        }
        updates = []
        params = []
        for key, value in values.items():
            if key not in allowed:
                continue
            if key in {"input_json", "draft_json"} and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            updates.append(f"{key}=?")
            params.append(value)
        if not updates:
            return False

        updates.append("updated_at=CURRENT_TIMESTAMP")
        params.append(contract_id)
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE amc_contracts SET {', '.join(updates)} WHERE id=?",
            params,
        )
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        return updated

    def get_amc_contract(self, contract_id):
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT amc_contracts.*, clients.name AS client_name
            FROM amc_contracts
            JOIN clients ON clients.id = amc_contracts.client_id
            WHERE amc_contracts.id=?
        """, (contract_id,))
        row = cursor.fetchone()
        conn.close()
        return self._decode_amc_row(row)

    def list_amc_contracts(self, limit=50):
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT amc_contracts.*, clients.name AS client_name
            FROM amc_contracts
            JOIN clients ON clients.id = amc_contracts.client_id
            ORDER BY amc_contracts.updated_at DESC, amc_contracts.id DESC
            LIMIT ?
        """, (int(limit),))
        rows = cursor.fetchall()
        conn.close()
        return [self._decode_amc_row(row) for row in rows]

    def add_amc_revision(self, contract_id, draft, instruction=''):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM amc_revisions "
            "WHERE contract_id=?",
            (contract_id,),
        )
        revision_no = int(cursor.fetchone()[0])
        cursor.execute("""
            INSERT INTO amc_revisions (
                contract_id, revision_no, instruction, draft_json
            )
            VALUES (?, ?, ?, ?)
        """, (
            contract_id,
            revision_no,
            instruction,
            json.dumps(draft, ensure_ascii=False),
        ))
        conn.commit()
        conn.close()
        return revision_no

    def get_amc_revisions(self, contract_id):
        conn = self._connect()
        conn.row_factory = _Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM amc_revisions
            WHERE contract_id=?
            ORDER BY revision_no DESC
        """, (contract_id,))
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            item = dict(row)
            item["draft"] = json.loads(item.pop("draft_json"))
            result.append(item)
        return result

    @staticmethod
    def _decode_amc_row(row):
        if not row:
            return None
        item = dict(row)
        try:
            item["input_data"] = json.loads(item.pop("input_json"))
        except (TypeError, json.JSONDecodeError):
            item["input_data"] = {}
        raw_draft = item.pop("draft_json", "")
        try:
            item["draft"] = json.loads(raw_draft) if raw_draft else None
        except (TypeError, json.JSONDecodeError):
            item["draft"] = None
        return item

    # ------------------------------------------------------------------
    # Backup & Restore
    # ------------------------------------------------------------------
    EXPECTED_TABLES = (
        "repositories",
        "clients",
        "app_settings",
        "amc_contracts",
        "amc_revisions",
        "ai_usage",
    )

    def get_db_info(self):
        """Return summary metadata about the current database file."""
        info = {
            "path": self.db_path,
            "exists": os.path.isfile(self.db_path),
            "encrypted": False,
            "sqlcipher_available": _HAS_SQLCIPHER,
            "size_bytes": 0,
            "size_kb": 0.0,
            "tables": {},
        }
        if not info["exists"]:
            return info
        info["encrypted"] = not is_plaintext_db(self.db_path)
        info["size_bytes"] = os.path.getsize(self.db_path)
        info["size_kb"] = round(info["size_bytes"] / 1024, 1)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            for (table,) in cursor.fetchall():
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    info["tables"][table] = cursor.fetchone()[0]
                except _OperationalError:
                    info["tables"][table] = None
        finally:
            conn.close()
        return info

    @staticmethod
    def validate_db_file(path, password=None):
        """Validate that a file is a SQLite DB with the expected tables.

        If *password* is provided (or the file is not plaintext), the file
        is opened with ``sqlcipher3`` using that password.  A wrong password
        results in a validation failure.

        Returns (True, None) on success, (False, message) on failure.
        """
        if not os.path.isfile(path):
            return False, "File does not exist."
        if os.path.getsize(path) < 100:
            return False, "File is too small to be a valid SQLite database."

        plaintext = is_plaintext_db(path)

        if plaintext:
            # Plain SQLite — open read-only with the standard module.
            import sqlite3
            try:
                conn = sqlite3.connect("file:{}?mode=ro".format(path), uri=True)
            except _DatabaseError as exc:
                return False, "Could not open as SQLite database: {}".format(exc)
        else:
            # Encrypted — need sqlcipher3 + password.
            if not _HAS_SQLCIPHER:
                return False, (
                    "Database appears to be encrypted but sqlcipher3 is not "
                    "installed. Install it with: pip install sqlcipher3"
                )
            if not password:
                return False, (
                    "Database is encrypted. A password is required to import it."
                )
            try:
                conn = _db_module.connect(path)
                hex_key = binascii.hexlify(password.encode()).decode()
                conn.execute("PRAGMA key = \"x'{}'\"".format(hex_key))
                # Force a read to verify the key is correct.
                conn.execute("SELECT count(*) FROM sqlite_master")
            except _DatabaseError:
                return False, "Wrong password or corrupted database file."
            except Exception as exc:
                return False, "Could not open encrypted database: {}".format(exc)

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
            found = {row[0] for row in cursor.fetchall()}
        except _DatabaseError as exc:
            return False, "Could not read schema: {}".format(exc)
        finally:
            conn.close()
        missing = [
            t for t in RepositoryDB.EXPECTED_TABLES if t not in found
        ]
        if missing:
            return False, "Missing expected tables: {}".format(
                ", ".join(missing)
            )
        return True, None

    def import_db(self, source_path, password=None):
        """Replace the current database with the one at source_path.

        If *source_path* is an encrypted database, *password* is used to
        validate it and becomes the new encryption password for the live
        database (stored in the keyring via ``db_security``).

        Backs up the existing DB to a timestamped sibling file before
        swapping. Runs _init_database afterwards so any new columns are
        added to the imported schema.

        Returns dict with keys: ok (bool), backup_path (str), message (str).
        """
        ok, message = self.validate_db_file(source_path, password)
        if not ok:
            return {"ok": False, "backup_path": "", "message": message}

        source_is_encrypted = not is_plaintext_db(source_path)

        backup_path = ""
        if os.path.isfile(self.db_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = "{}.backup_{}".format(self.db_path, timestamp)
            shutil.copy2(self.db_path, backup_path)

        # Copy imported file into place.
        shutil.copy2(source_path, self.db_path)

        # Update the password for future connections.
        if source_is_encrypted and password:
            self._password = password
            from src.core import db_security
            db_security.set_password(password)
        elif is_plaintext_db(self.db_path):
            # Imported a plaintext DB — we should encrypt it if we have a password.
            if self._password and _HAS_SQLCIPHER:
                self._encrypt_in_place(self._password)

        try:
            self._init_database()
        except _DatabaseError as exc:
            if backup_path and os.path.isfile(backup_path):
                shutil.copy2(backup_path, self.db_path)
            return {
                "ok": False,
                "backup_path": backup_path,
                "message": "Imported DB opened but schema init failed: {}".format(
                    exc
                ),
            }
        logger.info(
            "Database imported from %s (backup: %s)", source_path, backup_path
        )
        return {
            "ok": True,
            "backup_path": backup_path,
            "message": "Database imported successfully.",
        }

    def _encrypt_in_place(self, password):
        """Encrypt the current plaintext database file in-place.

        Reads the plaintext DB, creates an encrypted copy, then replaces
        the original.  No-op if the DB is already encrypted.
        """
        if not _HAS_SQLCIPHER or not password:
            return
        if not is_plaintext_db(self.db_path):
            return  # already encrypted

        import sqlite3
        enc_path = self.db_path + ".enc_tmp"
        try:
            # Read plaintext dump.
            src = sqlite3.connect(self.db_path)
            dump = "\n".join(src.iterdump())
            src.close()
            # Create encrypted destination and load dump.
            dst = _db_module.connect(enc_path)
            hex_key = binascii.hexlify(password.encode()).decode()
            dst.execute("PRAGMA key = \"x'{}'\"".format(hex_key))
            dst.executescript(dump)
            dst.commit()
            dst.close()
            # Replace plaintext with encrypted.
            shutil.copy2(enc_path, self.db_path)
        finally:
            if os.path.isfile(enc_path):
                os.remove(enc_path)

    def migrate_to_encrypted(self, password):
        """Migrate a plaintext database to an encrypted one.

        Returns dict with keys: ok (bool), message (str).
        """
        if not _HAS_SQLCIPHER:
            return {
                "ok": False,
                "message": "sqlcipher3 is not installed. Run: pip install sqlcipher3",
            }
        if not password:
            return {"ok": False, "message": "Password is required."}
        if not os.path.isfile(self.db_path):
            # No DB yet — just set the password; _init_database will create
            # an encrypted DB on the next RepositoryDB() call.
            self._password = password
            self._init_database()
            return {"ok": True, "message": "New encrypted database created."}
        if not is_plaintext_db(self.db_path):
            return {"ok": True, "message": "Database is already encrypted."}

        # Back up plaintext, then encrypt in-place.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = "{}.plaintext_backup_{}".format(self.db_path, timestamp)
        shutil.copy2(self.db_path, backup)

        self._password = password
        self._encrypt_in_place(password)
        try:
            self._init_database()
        except _DatabaseError as exc:
            # Restore plaintext backup on failure.
            shutil.copy2(backup, self.db_path)
            return {
                "ok": False,
                "message": "Encryption failed: {}. Plaintext DB restored.".format(
                    exc
                ),
            }
        logger.info("Database migrated to encrypted (backup: %s)", backup)
        return {
            "ok": True,
            "message": "Database encrypted successfully. Plaintext backup: {}".format(
                os.path.basename(backup)
            ),
        }
