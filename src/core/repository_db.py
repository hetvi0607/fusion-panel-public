# -*- coding: utf-8 -*-
"""
Repository database module for managing GitHub repository configurations.

This module provides functionality to store and retrieve repository configurations
from a SQLite database instead of environment variables.
"""
import sqlite3
import os
import logging
import json

logger = logging.getLogger(__name__)

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

        self._ensure_columns(cursor, "clients", {
            "contact_person": "TEXT DEFAULT ''",
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "website": "TEXT DEFAULT ''",
            "signatory_name": "TEXT DEFAULT ''",
            "signatory_title": "TEXT DEFAULT ''",
        })

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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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

    # ---------------------------------------------------------------------------
    # AMC settings and contract persistence
    # ---------------------------------------------------------------------------

    def get_runtime_settings(self, defaults=None):
        """Return persisted GUI runtime overrides merged over supplied defaults."""
        settings = dict(defaults or {})
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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

    def record_ai_usage(
        self,
        feature,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0,
    ):
        """Record one completed AI operation for the monthly budget guardrail."""
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
