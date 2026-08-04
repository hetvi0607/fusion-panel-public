"""
Flask web GUI for GitHub Commit Tracking Automation.

Provides a browser-based interface for:
- Generating commit reports with date range selection
- Managing repositories (add/edit/delete)
- Viewing generated reports
- Configuring settings
"""
import os
import sys
import csv
import json
import threading
import time
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import calendar
import requests as http_requests
from dateutil.relativedelta import relativedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Use pbkdf2 explicitly — scrypt is unavailable on macOS LibreSSL Python builds.
_PWD_HASH_METHOD = "pbkdf2:sha256:1000000"

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.core.config import app_config
from src.core.repository_db import RepositoryDB, is_plaintext_db, _HAS_SQLCIPHER
from src.core import db_security
from src.core.github_client import GitHubClient
from src.core.csv_reporter import CSVReporter
from src.core.ai.csv_summarizer import AICsvSummarizer
from src.core.invoice_generator import InvoiceGenerator
from src.core.offer_letter_generator import OfferLetterGenerator
from src.core.amc_ai_generator import AmcAiGenerator, PROMPT_VERSION, validate_amc_draft
from src.core.amc_document_generator import AmcDocumentGenerator

app = Flask(__name__, template_folder='templates', static_folder='static')

# Stable secret key so sessions survive restarts.  Stored in a file under data/.
_SECRET_KEY_FILE = os.path.join(PROJECT_ROOT, "data", ".flask_secret_key")
if os.path.isfile(_SECRET_KEY_FILE):
    with open(_SECRET_KEY_FILE, "rb") as fh:
        app.secret_key = fh.read()
else:
    app.secret_key = os.urandom(32)
    os.makedirs(os.path.dirname(_SECRET_KEY_FILE), exist_ok=True)
    with open(_SECRET_KEY_FILE, "wb") as fh:
        fh.write(app.secret_key)
    os.chmod(_SECRET_KEY_FILE, 0o600)

# Session defaults: expire when browser closes unless "remember me" is checked.
from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=30)

logger = logging.getLogger(__name__)

# Global state for tracking report generation jobs
jobs = {}


def get_db():
    return RepositoryDB()


def get_db_path():
    return os.path.join(PROJECT_ROOT, "data", "repositories.db")


def encryption_state():
    """Return the current encryption state as a dict.

    Keys:
        sqlcipher_available: bool
        has_password: bool
        db_exists: bool
        db_encrypted: bool
        needs_setup: bool      — first run, no password yet
        needs_password: bool   — encrypted DB but no password in keyring
    """
    db_path = get_db_path()
    db_exists = os.path.isfile(db_path)
    db_encrypted = db_exists and not is_plaintext_db(db_path)
    has_pwd = db_security.has_password()
    return {
        "sqlcipher_available": _HAS_SQLCIPHER,
        "has_password": has_pwd,
        "db_exists": db_exists,
        "db_encrypted": db_encrypted,
        "needs_setup": _HAS_SQLCIPHER and not has_pwd and not db_encrypted,
        "needs_password": _HAS_SQLCIPHER and not has_pwd and db_encrypted,
    }


@app.before_request
def check_encryption_setup():
    """Redirect to the encryption setup or login page when action is required.

    Order of checks:
      1. Encryption setup (DB must be accessible first)
      2. Login password setup (first run after encryption is configured)
      3. Login (user must be authenticated)
    """
    # Pages that bypass all checks
    if request.endpoint in ("static", "encryption_setup", "enter_password",
                            "setup_login_password", "login", "logout"):
        return

    # 1. Encryption check
    if _HAS_SQLCIPHER:
        state = encryption_state()
        if state["needs_password"]:
            return redirect(url_for("enter_password"))
        if state["needs_setup"]:
            return redirect(url_for("encryption_setup"))

    # 2. Login password setup check (first run)
    try:
        db = get_db()
        if not db.has_login_password():
            return redirect(url_for("setup_login_password"))
    except Exception:
        # If DB can't be opened, the encryption check above should have
        # caught it.  If we get here, skip login check to avoid crash loop.
        pass

    # 3. Login check
    if not session.get("logged_in"):
        return redirect(url_for("login"))


def get_reports_dir():
    return os.path.join(PROJECT_ROOT, "data", "reports")


def get_invoices_dir():
    return os.path.join(PROJECT_ROOT, "data", "invoices")


def get_offer_letters_dir():
    return os.path.join(PROJECT_ROOT, "data", "offer_letters")


def get_amc_contracts_dir():
    return os.path.join(PROJECT_ROOT, "data", "amc_contracts")


RUNTIME_SETTING_KEYS = (
    "GITHUB_TOKEN",
    "CLAUDE_API_KEY",
    "CLAUDE_MODEL",
    "AI_ENABLED",
    "AI_BUDGET_LIMIT",
    "AI_MAX_TOKENS",
    "PARALLEL_PROCESSING",
    "MAX_WORKERS",
    "BATCH_SIZE",
    "LOG_LEVEL",
)


def _runtime_setting_defaults():
    return {
        key: getattr(app_config, key)
        for key in RUNTIME_SETTING_KEYS
    }


def _apply_runtime_settings(settings):
    """Apply validated settings to new work without restarting Flask."""
    for key in RUNTIME_SETTING_KEYS:
        if key in settings:
            setattr(app_config, key, settings[key])
    logging.getLogger().setLevel(
        getattr(logging, app_config.LOG_LEVEL, logging.INFO)
    )


def _load_saved_runtime_settings():
    # Skip if encryption setup is needed (DB can't be opened yet).
    state = encryption_state()
    if state["needs_setup"] or state["needs_password"]:
        return
    try:
        db = get_db()
        # Skip if login password isn't set up yet (first run).
        if not db.has_login_password():
            return
        stored = db.get_runtime_settings(_runtime_setting_defaults())
        _apply_runtime_settings(stored)
    except Exception as exc:
        logger.warning("Could not load saved runtime settings: %s", exc)


def _masked_secret(value):
    value = str(value or "")
    return f"••••{value[-4:]}" if value else "Not configured"


def _ai_availability(db):
    """Return whether a new AI operation is allowed and a useful reason."""
    if not app_config.AI_ENABLED:
        return False, "AI is disabled in Settings."
    if not app_config.CLAUDE_API_KEY:
        return False, "Claude API key is not configured."
    usage = db.get_monthly_ai_usage()
    limit = float(app_config.AI_BUDGET_LIMIT or 0)
    if limit > 0 and float(usage["estimated_cost"]) >= limit:
        return (
            False,
            f"Monthly AI budget of ${limit:.2f} has been reached.",
        )
    return True, ""


def _record_ai_usage(db, feature, usage):
    db.record_ai_usage(
        feature,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        estimated_cost=usage.get("estimated_cost", 0),
    )


def _fetch_selected_commits(
    *,
    job,
    github_client,
    selected_repos,
    start_date,
    end_date,
):
    """Fetch repositories sequentially or concurrently using live settings."""
    all_commits = []

    def fetch_one(repo_config):
        repo_name = repo_config["repo"]
        branch = repo_config.get("branch")
        commits = github_client.fetch_commits(
            repo_name,
            start_date,
            end_date,
            branch=branch,
        )
        return repo_name, branch, commits

    parallel = (
        app_config.PARALLEL_PROCESSING
        and len(selected_repos) > 1
        and app_config.MAX_WORKERS > 1
    )
    if parallel:
        workers = min(app_config.MAX_WORKERS, len(selected_repos))
        job["log"].append(f"Parallel repository fetching: {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fetch_one, repo): repo
                for repo in selected_repos
            }
            for index, future in enumerate(as_completed(futures), 1):
                repo = futures[future]
                repo_name = repo["repo"]
                branch = repo.get("branch")
                branch_info = f" ({branch})" if branch else ""
                job["progress"] = (
                    f"Fetched {index}/{len(selected_repos)} repositories"
                )
                try:
                    _, _, commits = future.result()
                    all_commits.extend(commits)
                    job["log"].append(
                        f"✓ {repo_name}{branch_info}: {len(commits)} commits"
                    )
                except Exception as exc:
                    job["log"].append(f"✗ {repo_name}{branch_info}: {exc}")
        return all_commits

    for index, repo in enumerate(selected_repos, 1):
        repo_name = repo["repo"]
        branch = repo.get("branch")
        branch_info = f" ({branch})" if branch else ""
        job["progress"] = (
            f"Fetching {repo_name}{branch_info} "
            f"({index}/{len(selected_repos)})"
        )
        try:
            _, _, commits = fetch_one(repo)
            all_commits.extend(commits)
            job["log"].append(
                f"✓ {repo_name}{branch_info}: {len(commits)} commits"
            )
        except Exception as exc:
            job["log"].append(f"✗ {repo_name}{branch_info}: {exc}")
    return all_commits


_load_saved_runtime_settings()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    db = get_db()
    repos = db.get_repositories(enabled_only=False)
    enabled_count = sum(1 for r in repos if r['enabled'])
    
    # Count reports
    reports_dir = get_reports_dir()
    report_months = []
    if os.path.isdir(reports_dir):
        for item in sorted(os.listdir(reports_dir), reverse=True):
            item_path = os.path.join(reports_dir, item)
            if os.path.isdir(item_path) and item not in ('.DS_Store',):
                all_commits = os.path.join(item_path, "all_commits.csv")
                commit_count = 0
                if os.path.exists(all_commits):
                    with open(all_commits, 'r', encoding='utf-8') as f:
                        commit_count = max(sum(1 for _ in f) - 1, 0)  # subtract header
                report_months.append({
                    'name': item,
                    'path': item_path,
                    'commit_count': commit_count,
                })

    return render_template("dashboard.html",
                           total_repos=len(repos),
                           enabled_repos=enabled_count,
                           report_months=report_months,
                           ai_enabled=app_config.AI_ENABLED,
                           jobs=jobs)


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------
@app.route("/generate", methods=["GET"])
def generate_page():
    db = get_db()
    repos = db.get_repositories(enabled_only=True)
    now = datetime.now()
    default_start = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    default_end = now.strftime("%Y-%m-%d")
    return render_template("generate.html",
                           repos=repos,
                           default_start=default_start,
                           default_end=default_end,
                           ai_enabled=app_config.AI_ENABLED)


def run_report_job(job_id, start_date, end_date, use_ai, selected_repos):
    """Background worker that generates a report."""
    jobs[job_id]['status'] = 'running'
    jobs[job_id]['progress'] = 'Initializing...'
    try:
        db = get_db()
        github_client = GitHubClient()

        ai_summarizer = None
        if use_ai:
            allowed, reason = _ai_availability(db)
            if not allowed:
                jobs[job_id]['log'].append(f"AI skipped: {reason}")
                use_ai = False
            else:
                try:
                    ai_summarizer = AICsvSummarizer()
                    jobs[job_id]['progress'] = 'AI summarizer ready'
                except Exception as e:
                    jobs[job_id]['log'].append(f"AI init failed: {e}")
                    use_ai = False

        all_commits = _fetch_selected_commits(
            job=jobs[job_id],
            github_client=github_client,
            selected_repos=selected_repos,
            start_date=start_date,
            end_date=end_date,
        )

        if not all_commits:
            jobs[job_id]['status'] = 'done'
            jobs[job_id]['progress'] = 'No commits found'
            jobs[job_id]['result'] = {'total_commits': 0}
            return

        jobs[job_id]['progress'] = f"Generating CSV report ({len(all_commits)} commits)..."
        month_year = datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
        csv_reporter = CSVReporter()
        report_path = csv_reporter.create_repository_reports(all_commits, month_year)
        jobs[job_id]['log'].append(f"CSV report: {report_path}")

        summary_path = None
        if use_ai and ai_summarizer:
            jobs[job_id]['progress'] = 'Generating AI summaries...'
            try:
                repo_summaries = {}
                month_dir = os.path.dirname(report_path)
                repo_branch_combos = set(
                    (c["repo_name"], c.get("branch", "default")) for c in all_commits
                )
                for repo_name, branch in repo_branch_combos:
                    repo_sanitized = repo_name.replace('/', '-')
                    branch_sanitized = branch.replace('/', '-')
                    repo_csv_path = os.path.join(month_dir, repo_sanitized, branch_sanitized, "commits.csv")
                    if os.path.exists(repo_csv_path):
                        commits_data = ai_summarizer.read_csv_data(repo_csv_path)
                        if commits_data:
                            key = f"{repo_name} ({branch})"
                            summary = ai_summarizer.generate_repository_summary(key, commits_data)
                            repo_summaries[key] = summary

                all_csv_commits = ai_summarizer.read_csv_data(report_path)
                repo_names = [r['repo'] for r in selected_repos]
                overall_summary = ai_summarizer.generate_overall_summary(all_csv_commits, repo_names)
                summary_path = ai_summarizer.create_summary_report(
                    report_path, repo_summaries, overall_summary, f"{start_date} to {end_date}"
                )
                usage = ai_summarizer.get_usage_stats()
                _record_ai_usage(db, "report_summary", usage)
                jobs[job_id]['log'].append(
                    f"AI summary done – cost: ${usage['estimated_cost']:.4f}, tokens: {usage['total_tokens']}"
                )
            except Exception as e:
                jobs[job_id]['log'].append(f"AI summary error: {e}")

        jobs[job_id]['status'] = 'done'
        jobs[job_id]['progress'] = 'Complete'
        jobs[job_id]['result'] = {
            'total_commits': len(all_commits),
            'report_path': report_path,
            'summary_path': summary_path,
            'date_range': f"{start_date} to {end_date}",
        }
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['progress'] = f"Error: {e}"
        jobs[job_id]['log'].append(str(e))


@app.route("/generate", methods=["POST"])
def generate_report():
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    use_ai = (
        request.form.get("use_ai") == "on"
        and app_config.AI_ENABLED
    )
    selected_repo_ids = request.form.getlist("repos")

    db = get_db()
    all_repos = db.get_repositories(enabled_only=True)

    if selected_repo_ids:
        selected_repos = [r for r in all_repos if f"{r['repo']}:{r['branch']}" in selected_repo_ids]
    else:
        selected_repos = all_repos

    if not selected_repos:
        flash("No repositories selected.", "error")
        return redirect(url_for("generate_page"))

    job_id = f"job_{int(time.time())}"
    jobs[job_id] = {
        'status': 'queued',
        'progress': 'Queued',
        'log': [],
        'result': None,
        'started_at': datetime.now().isoformat(),
    }

    thread = threading.Thread(target=run_report_job,
                              args=(job_id, start_date, end_date, use_ai, selected_repos),
                              daemon=True)
    thread.start()
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/job/<job_id>")
def job_status_page(job_id):
    job = jobs.get(job_id)
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("job_status.html", job_id=job_id, job=job)


@app.route("/api/job/<job_id>")
def job_status_api(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


# ---------------------------------------------------------------------------
# Repository Management
# ---------------------------------------------------------------------------
@app.route("/settings/repositories")
def repos_page():
    db = get_db()
    repos = db.get_repositories(enabled_only=False)
    return render_template("repos.html", repos=repos)


@app.route("/repos")
def legacy_repos_page():
    return redirect(url_for("repos_page"))


@app.route("/settings/repositories/add", methods=["POST"])
@app.route("/repos/add", methods=["POST"])
def add_repo():
    repo_name = request.form.get("repo_name", "").strip()
    branch = request.form.get("branch", "").strip()
    enabled = request.form.get("enabled") == "on"
    ai_enabled = request.form.get("ai_enabled") == "on"

    if not repo_name or not branch:
        flash("Repository name and branch are required.", "error")
        return redirect(url_for("repos_page"))

    db = get_db()
    success = db.add_repository(repo_name, branch, enabled, ai_enabled)
    if success:
        flash(f"Added {repo_name} ({branch})", "success")
    else:
        flash(f"Repository already exists: {repo_name} ({branch})", "error")
    return redirect(url_for("repos_page"))


@app.route("/settings/repositories/update", methods=["POST"])
@app.route("/repos/update", methods=["POST"])
def update_repo():
    repo_name = request.form.get("repo_name")
    branch = request.form.get("branch")
    enabled = request.form.get("enabled") == "on"
    ai_enabled = request.form.get("ai_enabled") == "on"

    db = get_db()
    db.update_repository(repo_name, branch, enabled=enabled, ai_enabled=ai_enabled)
    flash(f"Updated {repo_name} ({branch})", "success")
    return redirect(url_for("repos_page"))


@app.route("/settings/repositories/delete", methods=["POST"])
@app.route("/repos/delete", methods=["POST"])
def delete_repo():
    repo_name = request.form.get("repo_name")
    branch = request.form.get("branch")
    db = get_db()
    success = db.delete_repository(repo_name, branch)
    if success:
        flash(f"Deleted {repo_name} ({branch})", "success")
    else:
        flash(f"Repository not found: {repo_name} ({branch})", "error")
    return redirect(url_for("repos_page"))


# ---------------------------------------------------------------------------
# Reports Viewer
# ---------------------------------------------------------------------------
@app.route("/reports")
def reports_page():
    reports_dir = get_reports_dir()
    months = []
    if os.path.isdir(reports_dir):
        for item in sorted(os.listdir(reports_dir), reverse=True):
            item_path = os.path.join(reports_dir, item)
            if os.path.isdir(item_path) and item not in ('.DS_Store',):
                files = []
                for root, dirs, filenames in os.walk(item_path):
                    for fn in filenames:
                        if fn.endswith('.csv') or fn.endswith('.txt'):
                            full = os.path.join(root, fn)
                            rel = os.path.relpath(full, reports_dir)
                            size_kb = os.path.getsize(full) / 1024
                            files.append({'rel': rel, 'name': fn, 'size_kb': round(size_kb, 1),
                                          'full': full, 'dir': os.path.relpath(root, item_path)})
                months.append({'name': item, 'files': files})
    return render_template("reports.html", months=months)


@app.route("/reports/view/<path:rel_path>")
def view_report(rel_path):
    reports_dir = get_reports_dir()
    full_path = os.path.join(reports_dir, rel_path)
    if not os.path.exists(full_path):
        flash("File not found.", "error")
        return redirect(url_for("reports_page"))

    rows = []
    headers = []
    is_csv = full_path.endswith('.csv')
    text_content = ""

    if is_csv:
        with open(full_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            for row in reader:
                rows.append(row)
    else:
        with open(full_path, 'r', encoding='utf-8') as f:
            text_content = f.read()

    return render_template("view_report.html",
                           filename=os.path.basename(full_path),
                           rel_path=rel_path,
                           is_csv=is_csv,
                           headers=headers,
                           rows=rows,
                           text_content=text_content)


@app.route("/reports/download/<path:rel_path>")
def download_report(rel_path):
    reports_dir = get_reports_dir()
    full_path = os.path.join(reports_dir, rel_path)
    if not os.path.exists(full_path):
        flash("File not found.", "error")
        return redirect(url_for("reports_page"))
    return send_file(full_path, as_attachment=True)


# ---------------------------------------------------------------------------
# Invoice Generation
# ---------------------------------------------------------------------------
@app.route("/invoice", methods=["GET"])
def invoice_page():
    db = get_db()
    repos = db.get_repositories(enabled_only=True)
    now = datetime.now()
    default_start = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    default_end = now.strftime("%Y-%m-%d")
    clients = db.get_clients()
    return render_template("generate_invoice.html",
                           repos=repos,
                           clients=clients,
                           default_start=default_start,
                           default_end=default_end)


def run_invoice_job(
    job_id,
    start_date,
    end_date,
    selected_repos,
    repo_labels,
    bill_to,
    invoice_meta,
    per_hour_rate,
    currency,
    invoice_type="development",
    service_items=None,
):
    """Background worker that generates an invoice DOCX."""
    jobs[job_id]['status'] = 'running'
    jobs[job_id]['progress'] = 'Initializing...'
    try:
        service_items = service_items or []
        if invoice_type == "fixed":
            invoice_gen = InvoiceGenerator(enable_ai=False)
            work_details = service_items
            all_commits = []
            date_slug = datetime.now().strftime('%B-%Y').lower()
            jobs[job_id]['log'].append(
                f"Added {len(work_details)} fixed-rate service item(s)"
            )
        else:
            db = get_db()
            github_client = GitHubClient()
            ai_allowed, ai_reason = _ai_availability(db)
            invoice_gen = InvoiceGenerator(enable_ai=ai_allowed)
            if not ai_allowed:
                jobs[job_id]['log'].append(
                    f"AI categorization skipped: {ai_reason}"
                )

            # 1. Fetch commits
            all_commits = _fetch_selected_commits(
                job=jobs[job_id],
                github_client=github_client,
                selected_repos=selected_repos,
                start_date=start_date,
                end_date=end_date,
            )

            if not all_commits:
                jobs[job_id]['status'] = 'done'
                jobs[job_id]['progress'] = 'No commits found'
                jobs[job_id]['result'] = {'total_commits': 0}
                return

            # 2. Fetch stats for accurate hour estimation
            jobs[job_id]['progress'] = (
                f"Fetching code stats for {len(all_commits)} commits..."
            )

            def stats_progress(current, total):
                jobs[job_id]['progress'] = (
                    f"Fetching code stats ({current}/{total})..."
                )

            github_client.fetch_commit_stats(
                all_commits,
                progress_callback=stats_progress,
            )
            total_additions = sum(
                c.get('stats', {}).get('additions', 0)
                for c in all_commits
            )
            total_deletions = sum(
                c.get('stats', {}).get('deletions', 0)
                for c in all_commits
            )
            jobs[job_id]['log'].append(
                f"Code stats: +{total_additions} additions, "
                f"-{total_deletions} deletions across "
                f"{len(all_commits)} commits"
            )

            # 3. AI categorization
            if ai_allowed:
                jobs[job_id]['progress'] = (
                    f"AI categorizing {len(all_commits)} commits..."
                )
                try:
                    work_details = invoice_gen.categorize_commits(
                        all_commits,
                        repo_labels,
                    )
                    jobs[job_id]['log'].append(
                        f"AI returned {len(work_details)} work categories"
                    )
                except Exception as ai_err:
                    jobs[job_id]['log'].append(
                        f"✗ AI categorization failed: {ai_err}"
                    )
                    jobs[job_id]['log'].append(
                        "Falling back to per-repo grouping"
                    )
                    ai_allowed = False

            if not ai_allowed:
                # Simple fallback: one category per repository.
                from collections import defaultdict
                repo_msgs = defaultdict(list)
                for c in all_commits:
                    repo_msgs[c.get("repo_name", "unknown")].append(
                        c.get("message", "")
                    )
                work_details = [
                    {
                        "category": repo_labels.get(repo, repo),
                        "hours": max(1, len(msgs) // 5),
                        "items": msgs[:8],
                    }
                    for repo, msgs in repo_msgs.items()
                ]
            date_slug = datetime.strptime(
                start_date,
                '%Y-%m-%d',
            ).strftime('%B-%Y').lower()

        # 4. Generate DOCX
        jobs[job_id]['progress'] = 'Generating DOCX invoice...'
        invoices_dir = get_invoices_dir()
        invoice_no = secure_filename(
            invoice_meta.get('invoice_no', '')
        ) or 'draft'
        filename = f"invoice_{invoice_no}_{date_slug}.docx"
        output_path = os.path.join(invoices_dir, filename)

        invoice_gen.generate_invoice(
            work_details=work_details,
            bill_to=bill_to,
            invoice_meta=invoice_meta,
            output_path=output_path,
            per_hour_rate=per_hour_rate,
            currency=currency,
            pricing_mode=(
                "fixed" if invoice_type == "fixed" else "hourly"
            ),
        )

        usage = invoice_gen.get_usage_stats()
        if invoice_type == "development" and usage["total_tokens"]:
            _record_ai_usage(db, "invoice_categorization", usage)
        if invoice_type == "development":
            jobs[job_id]['log'].append(
                f"Invoice generated \u2013 cost: "
                f"${usage['estimated_cost']:.4f}, "
                f"tokens: {usage['total_tokens']}"
            )
        else:
            jobs[job_id]['log'].append("✓ Fixed-rate invoice generated")

        jobs[job_id]['status'] = 'done'
        jobs[job_id]['progress'] = 'Complete'
        result = {
            'invoice_path': output_path,
            'invoice_filename': filename,
            'categories': len(work_details),
        }
        if invoice_type == "fixed":
            result.update({
                'service_count': len(work_details),
                'total_amount': sum(
                    float(item.get("amount", 0))
                    for item in work_details
                ),
                'currency': currency,
            })
        else:
            result.update({
                'total_commits': len(all_commits),
                'date_range': f"{start_date} to {end_date}",
            })
        jobs[job_id]['result'] = result
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['progress'] = f"Error: {e}"
        jobs[job_id]['log'].append(str(e))


@app.route("/invoice", methods=["POST"])
def generate_invoice():
    invoice_type = request.form.get(
        "invoice_type",
        "development",
    ).strip().lower()
    if invoice_type not in ("development", "fixed"):
        invoice_type = "development"

    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    selected_repos = []
    repo_labels = {}
    service_items = []

    if invoice_type == "development":
        selected_repo_ids = request.form.getlist("repos")
        db = get_db()
        all_repos = db.get_repositories(enabled_only=True)

        if selected_repo_ids:
            selected_repos = [
                r for r in all_repos
                if f"{r['repo']}:{r['branch']}" in selected_repo_ids
            ]
        else:
            selected_repos = all_repos

        if not selected_repos:
            flash("No repositories selected.", "error")
            return redirect(url_for("invoice_page"))

        # Collect repository labels from form.
        for repo in selected_repos:
            key = f"label_{repo['repo']}:{repo['branch']}"
            label = request.form.get(key, "").strip()
            if label:
                repo_labels[repo['repo']] = label
    else:
        service_names = request.form.getlist("service_name[]")
        service_descriptions = request.form.getlist(
            "service_description[]"
        )
        service_amounts = request.form.getlist("service_amount[]")
        for index, name in enumerate(service_names):
            name = name.strip()
            description = (
                service_descriptions[index].strip()
                if index < len(service_descriptions)
                else ""
            )
            raw_amount = (
                service_amounts[index].strip()
                if index < len(service_amounts)
                else ""
            )
            if not name and not description and not raw_amount:
                continue
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                flash(
                    f"Enter a valid amount for service item {index + 1}.",
                    "error",
                )
                return redirect(url_for("invoice_page"))
            if not name:
                flash(
                    f"Enter a service name for item {index + 1}.",
                    "error",
                )
                return redirect(url_for("invoice_page"))
            if not math.isfinite(amount) or amount <= 0:
                flash(
                    f"Service amount must be greater than zero "
                    f"for item {index + 1}.",
                    "error",
                )
                return redirect(url_for("invoice_page"))
            service_items.append({
                "category": name,
                "items": [description] if description else [],
                "amount": amount,
            })

        if not service_items:
            flash("Add at least one fixed-rate service.", "error")
            return redirect(url_for("invoice_page"))

    # Per hour rate and currency
    try:
        per_hour_rate = float(request.form.get("per_hour_rate", "0").strip() or "0")
    except ValueError:
        per_hour_rate = 0
    currency = request.form.get("currency", "INR").strip().upper()
    if currency not in ("INR", "USD"):
        currency = "INR"

    # Billing info
    bill_to = {
        "name": request.form.get("bill_to_name", "").strip(),
        "address_line1": request.form.get("bill_to_addr1", "").strip(),
        "address_line2": request.form.get("bill_to_addr2", "").strip(),
        "gstin": request.form.get("bill_to_gstin", "").strip(),
    }

    invoice_meta = {
        "invoice_no": request.form.get("invoice_no", "").strip(),
        "po_number": request.form.get("po_number", "").strip(),
        "invoice_for": request.form.get("invoice_for", "").strip(),
        "date_submitted": request.form.get("date_submitted", "").strip(),
    }

    job_id = f"inv_{int(time.time())}"
    jobs[job_id] = {
        'status': 'queued',
        'progress': 'Queued',
        'log': [],
        'result': None,
        'started_at': datetime.now().isoformat(),
        'type': 'invoice',
    }

    thread = threading.Thread(
        target=run_invoice_job,
        args=(job_id, start_date, end_date, selected_repos, repo_labels,
              bill_to, invoice_meta, per_hour_rate, currency,
              invoice_type, service_items),
        daemon=True,
    )
    thread.start()
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/invoice/download/<path:filename>")
def download_invoice(filename):
    invoices_dir = get_invoices_dir()
    full_path = os.path.join(invoices_dir, filename)
    if not os.path.exists(full_path):
        flash("Invoice file not found.", "error")
        return redirect(url_for("dashboard"))
    return send_file(full_path, as_attachment=True)


# ---------------------------------------------------------------------------
# Offer Letter Generation
# ---------------------------------------------------------------------------
@app.route("/offer-letter", methods=["GET"])
def offer_letter_page():
    return render_template("offer_letter.html", form=None)


@app.route("/offer-letter", methods=["POST"])
def generate_offer_letter():
    form = request.form

    candidate_name = form.get("candidate_name", "").strip()
    if not candidate_name:
        flash("Candidate name is required.", "error")
        return render_template("offer_letter.html", form=form)

    # Parse issue_date from YYYY-MM-DD to "D Month YYYY"
    issue_date_raw = form.get("issue_date", "")
    try:
        parsed_issue = datetime.strptime(issue_date_raw, "%Y-%m-%d")
        issue_date_str = parsed_issue.strftime("%-d %B %Y")
    except ValueError:
        issue_date_str = issue_date_raw

    # Parse start_date from YYYY-MM-DD to "D Month YYYY"
    start_date_raw = form.get("start_date", "")
    try:
        parsed_start = datetime.strptime(start_date_raw, "%Y-%m-%d")
        start_date_str = parsed_start.strftime("%-d %B %Y")
    except ValueError:
        start_date_str = start_date_raw

    data = {
        "candidate_name": candidate_name,
        "candidate_email": form.get("candidate_email", "").strip(),
        "candidate_phone": form.get("candidate_phone", "").strip(),
        "candidate_college": form.get("candidate_college", "").strip(),
        "issue_date": issue_date_str,
        "letter_ref": form.get("letter_ref", "").strip(),
        "position": form.get("position", "Software Development Intern").strip(),
        "department": form.get("department", "").strip(),
        "start_date": start_date_str,
        "duration": form.get("duration", "").strip(),
        "mode": form.get("mode", "Remote").strip(),
        "reporting_manager": form.get("reporting_manager", "").strip(),
        "working_hours": form.get("working_hours", "Flexible").strip(),
        "stipend": form.get("stipend", "").strip(),
        "project_description": form.get("project_description", "").strip(),
        "extra_terms": form.get("extra_terms", "").strip(),
    }

    try:
        generator = OfferLetterGenerator()
        offer_letters_dir = get_offer_letters_dir()
        os.makedirs(offer_letters_dir, exist_ok=True)

        safe_name = candidate_name.lower().replace(" ", "_")
        date_slug = issue_date_raw or datetime.now().strftime("%Y-%m-%d")
        filename = f"offer_letter_{safe_name}_{date_slug}.docx"
        output_path = os.path.join(offer_letters_dir, filename)

        generator.generate_offer_letter(data, output_path)
        logger.info(f"Offer letter generated: {output_path}")
        return send_file(output_path, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"Error generating offer letter: {e}")
        flash(f"Error generating offer letter: {e}", "error")
        return render_template("offer_letter.html", form=form)


# ---------------------------------------------------------------------------
# AI-first Annual Maintenance Contracts
# ---------------------------------------------------------------------------
def _display_date(value):
    return value.strftime("%d %B %Y").lstrip("0")


def _split_nonempty_lines(value):
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _maintenance_items_from_form(form):
    """Parse and validate repeatable AMC maintenance items."""
    try:
        item_count = int(form.get("maintenance_item_count", "0") or 0)
    except (TypeError, ValueError):
        item_count = 0
    item_count = min(max(item_count, 0), 20)

    items = []
    for index in range(item_count):
        service_type = form.get(
            f"maintenance_type_{index}",
            "",
        ).strip()
        asset_name = form.get(
            f"maintenance_name_{index}",
            "",
        ).strip()
        asset_url = form.get(
            f"maintenance_url_{index}",
            "",
        ).strip()
        if not service_type and not asset_name and not asset_url:
            continue
        if not service_type or not asset_name:
            raise ValueError(
                f"Maintenance item {index + 1} needs both a type "
                "and project / asset name."
            )
        items.append({
            "service_type": service_type,
            "asset_name": asset_name,
            "asset_url": asset_url,
        })

    # Backward compatibility for older forms and direct API-style posts.
    if not items:
        service_type = form.get(
            "service_type",
            "Website Maintenance",
        ).strip()
        asset_name = form.get("asset_name", "").strip()
        asset_url = form.get("asset_url", "").strip()
        if asset_name:
            items.append({
                "service_type": service_type or "Website Maintenance",
                "asset_name": asset_name,
                "asset_url": asset_url,
            })

    if not items:
        raise ValueError("Add at least one maintenance item.")
    return items


def _amc_draft_from_form(form, existing):
    draft = dict(existing or {})
    draft.update({
        "title": form.get("title", "").strip(),
        "opening": form.get("opening", "").strip(),
        "overview": form.get("overview", "").strip(),
        "scope_included": _split_nonempty_lines(form.get("scope_included", "")),
        "scope_excluded": _split_nonempty_lines(form.get("scope_excluded", "")),
        "assumptions": _split_nonempty_lines(form.get("assumptions", "")),
        "needs_confirmation": _split_nonempty_lines(
            form.get("needs_confirmation", "")
        ),
        "risk_flags": _split_nonempty_lines(form.get("risk_flags", "")),
        "consistency_notes": _split_nonempty_lines(
            form.get("consistency_notes", "")
        ),
    })

    service_levels = []
    for index in range(int(form.get("service_level_count", "0") or 0)):
        service = form.get(f"service_{index}", "").strip()
        commitment = form.get(f"commitment_{index}", "").strip()
        if service and commitment:
            service_levels.append({
                "service": service,
                "commitment": commitment,
            })
    draft["service_levels"] = service_levels

    clauses = []
    for index in range(int(form.get("clause_count", "0") or 0)):
        heading = form.get(f"clause_heading_{index}", "").strip()
        body = form.get(f"clause_body_{index}", "").strip()
        if heading and body:
            clauses.append({"heading": heading, "body": body})
    draft["clauses"] = clauses
    return validate_amc_draft(draft)


def _queue_amc_job(db, client_id, input_data):
    allowed, reason = _ai_availability(db)
    if not allowed:
        raise RuntimeError(reason)
    contract_id = db.create_amc_contract(
        client_id=client_id,
        input_data=input_data,
        model=app_config.CLAUDE_MODEL,
        prompt_version=PROMPT_VERSION,
    )
    facts = input_data["facts"]
    if not facts.get("contract_reference"):
        facts["contract_reference"] = (
            f"FB/AMC/{facts['effective_date'][:4]}/{contract_id:04d}"
        )
        db.update_amc_contract(contract_id, input_json=input_data)

    job_id = f"amc_{time.time_ns()}"
    jobs[job_id] = {
        "status": "queued",
        "progress": "Queued",
        "log": [],
        "result": None,
        "started_at": datetime.now().isoformat(),
        "type": "amc",
    }
    thread = threading.Thread(
        target=run_amc_job,
        args=(job_id, contract_id),
        daemon=True,
    )
    thread.start()
    return job_id, contract_id


def run_amc_job(job_id, contract_id):
    jobs[job_id]["status"] = "running"
    jobs[job_id]["progress"] = "Preparing contract facts..."
    db = get_db()
    try:
        contract = db.get_amc_contract(contract_id)
        client = db.get_client(contract["client_id"])
        settings = db.get_amc_settings()
        input_data = contract["input_data"]

        jobs[job_id]["progress"] = "Claude is drafting the AMC..."
        jobs[job_id]["log"].append("✓ Contract facts validated")
        generator = AmcAiGenerator()
        draft = generator.generate_draft(
            facts=input_data["facts"],
            client=client,
            defaults=settings,
            project_context=input_data.get("project_context"),
        )
        usage = generator.get_usage_stats()
        _record_ai_usage(db, "amc_draft", usage)
        db.update_amc_contract(
            contract_id,
            status="review",
            draft_json=draft,
            model=generator.claude.model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            estimated_cost=usage["estimated_cost"],
            error_message="",
        )
        db.add_amc_revision(contract_id, draft, "Initial AI draft")
        jobs[job_id]["log"].append(
            "✓ AI draft and consistency review complete"
        )
        jobs[job_id]["log"].append(
            f"Tokens: {usage['total_tokens']} | "
            f"Estimated cost: ${usage['estimated_cost']:.4f}"
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = "Draft ready for review"
        jobs[job_id]["result"] = {"amc_id": contract_id}
    except Exception as exc:
        logger.exception("AMC generation failed")
        db.update_amc_contract(
            contract_id,
            status="error",
            error_message=str(exc),
        )
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = f"Error: {exc}"
        jobs[job_id]["log"].append(f"✗ {exc}")


@app.route("/amc", methods=["GET"])
def amc_page():
    db = get_db()
    return render_template(
        "amc.html",
        clients=db.get_clients(),
        repos=db.get_repositories(enabled_only=True),
        contracts=db.list_amc_contracts(),
        defaults=db.get_amc_settings(),
        default_effective_date=datetime.now().strftime("%Y-%m-%d"),
    )


@app.route("/amc/generate", methods=["POST"])
def generate_amc():
    db = get_db()
    try:
        client_id = int(request.form.get("client_id", "0"))
    except ValueError:
        client_id = 0
    client = db.get_client(client_id)
    if not client:
        flash("Select a valid client or vendor.", "error")
        return redirect(url_for("amc_page"))

    effective_raw = request.form.get("effective_date", "").strip()
    fee_raw = request.form.get("annual_fee", "").strip()
    if not effective_raw or not fee_raw:
        flash(
            "Maintenance items, effective date and annual fee are required.",
            "error",
        )
        return redirect(url_for("amc_page"))

    try:
        maintenance_items = _maintenance_items_from_form(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("amc_page"))

    try:
        effective = datetime.strptime(effective_raw, "%Y-%m-%d")
        annual_fee = float(fee_raw)
        if annual_fee <= 0:
            raise ValueError
    except ValueError:
        flash(
            "Enter a valid effective date and a positive annual fee.",
            "error",
        )
        return redirect(url_for("amc_page"))

    settings = db.get_amc_settings()
    try:
        term_months = max(1, int(settings.get("term_months", "12")))
    except (TypeError, ValueError):
        term_months = 12
    end_date = effective + relativedelta(months=term_months) - relativedelta(days=1)

    primary_item = maintenance_items[0]
    facts = {
        "maintenance_items": maintenance_items,
        # Keep the first item in the legacy scalar fields for old exports and
        # integrations that have not adopted the repeatable structure yet.
        "service_type": primary_item["service_type"],
        "asset_name": primary_item["asset_name"],
        "asset_url": primary_item["asset_url"],
        "effective_date": effective.strftime("%Y-%m-%d"),
        "effective_date_display": _display_date(effective),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "end_date_display": _display_date(end_date),
        "term_months": term_months,
        "annual_fee": annual_fee,
        "currency": request.form.get("currency", "INR").strip().upper(),
        "tax_note": "Taxes as applicable",
        "scope_hint": request.form.get("scope_hint", "").strip(),
        "contract_reference": "",
    }
    project_context = {
        "repositories": request.form.getlist("repositories"),
    }
    try:
        job_id, _ = _queue_amc_job(
            db,
            client_id,
            {"facts": facts, "project_context": project_context},
        )
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("amc_page"))
    return redirect(url_for("job_status_page", job_id=job_id))


@app.route("/amc/<int:contract_id>", methods=["GET"])
def review_amc(contract_id):
    db = get_db()
    contract = db.get_amc_contract(contract_id)
    if not contract:
        flash("AMC not found.", "error")
        return redirect(url_for("amc_page"))
    if not contract.get("draft"):
        flash(
            contract.get("error_message") or "The AMC draft is not ready yet.",
            "error",
        )
        return redirect(url_for("amc_page"))
    return render_template(
        "amc_review.html",
        contract=contract,
        client=db.get_client(contract["client_id"]),
        settings=db.get_amc_settings(),
        revisions=db.get_amc_revisions(contract_id),
    )


@app.route("/amc/<int:contract_id>/save", methods=["POST"])
def save_amc(contract_id):
    db = get_db()
    contract = db.get_amc_contract(contract_id)
    if not contract or not contract.get("draft"):
        flash("AMC draft not found.", "error")
        return redirect(url_for("amc_page"))
    try:
        draft = _amc_draft_from_form(request.form, contract["draft"])
        db.update_amc_contract(contract_id, status="review", draft_json=draft)
        db.add_amc_revision(contract_id, draft, "Manual edit")
        flash("AMC draft saved.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("review_amc", contract_id=contract_id))


@app.route("/amc/<int:contract_id>/revise", methods=["POST"])
def revise_amc(contract_id):
    db = get_db()
    contract = db.get_amc_contract(contract_id)
    instruction = request.form.get("revision_instruction", "").strip()
    if not contract or not contract.get("draft"):
        flash("AMC draft not found.", "error")
        return redirect(url_for("amc_page"))
    if not instruction:
        flash("Describe the change you want Claude to make.", "error")
        return redirect(url_for("review_amc", contract_id=contract_id))
    allowed, reason = _ai_availability(db)
    if not allowed:
        flash(reason, "error")
        return redirect(url_for("review_amc", contract_id=contract_id))

    try:
        current_draft = _amc_draft_from_form(request.form, contract["draft"])
        client = db.get_client(contract["client_id"])
        settings = db.get_amc_settings()
        generator = AmcAiGenerator()
        revised = generator.revise_draft(
            draft=current_draft,
            instruction=instruction,
            facts=contract["input_data"]["facts"],
            client=client,
            defaults=settings,
            project_context=contract["input_data"].get("project_context"),
        )
        usage = generator.get_usage_stats()
        _record_ai_usage(db, "amc_revision", usage)
        db.update_amc_contract(
            contract_id,
            status="review",
            draft_json=revised,
            input_tokens=contract["input_tokens"] + usage["input_tokens"],
            output_tokens=contract["output_tokens"] + usage["output_tokens"],
            estimated_cost=contract["estimated_cost"] + usage["estimated_cost"],
        )
        db.add_amc_revision(contract_id, revised, instruction)
        flash("Claude revised the AMC draft.", "success")
    except Exception as exc:
        logger.exception("AMC revision failed")
        flash(f"Could not revise the AMC: {exc}", "error")
    return redirect(url_for("review_amc", contract_id=contract_id))


@app.route("/amc/<int:contract_id>/export", methods=["POST"])
def export_amc(contract_id):
    db = get_db()
    contract = db.get_amc_contract(contract_id)
    if not contract or not contract.get("draft"):
        flash("AMC draft not found.", "error")
        return redirect(url_for("amc_page"))
    if request.form.get("confirm_review") != "on":
        flash("Confirm that you reviewed the AI draft before exporting.", "error")
        return redirect(url_for("review_amc", contract_id=contract_id))

    try:
        draft = _amc_draft_from_form(request.form, contract["draft"])
        client = db.get_client(contract["client_id"])
        settings = db.get_amc_settings()
        facts = contract["input_data"]["facts"]
        safe_client = secure_filename(client["name"].lower()) or "client"
        filename = (
            f"amc_{safe_client}_{facts['effective_date']}_{contract_id}.docx"
        )
        output_path = os.path.join(get_amc_contracts_dir(), filename)
        AmcDocumentGenerator().generate(
            draft=draft,
            facts=facts,
            client=client,
            settings=settings,
            output_path=output_path,
        )
        db.update_amc_contract(
            contract_id,
            status="exported",
            draft_json=draft,
            output_filename=filename,
        )
        db.add_amc_revision(contract_id, draft, "Approved for DOCX export")
        return send_file(output_path, as_attachment=True, download_name=filename)
    except Exception as exc:
        logger.exception("AMC DOCX export failed")
        flash(f"Could not generate the DOCX: {exc}", "error")
        return redirect(url_for("review_amc", contract_id=contract_id))


@app.route("/amc/download/<path:filename>")
def download_amc(filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        flash("Invalid AMC filename.", "error")
        return redirect(url_for("amc_page"))
    full_path = os.path.join(get_amc_contracts_dir(), safe_name)
    if not os.path.isfile(full_path):
        flash("AMC file not found.", "error")
        return redirect(url_for("amc_page"))
    return send_file(full_path, as_attachment=True)


@app.route("/amc/settings", methods=["GET", "POST"])
def amc_settings():
    db = get_db()
    if request.method == "POST":
        fields = [
            "term_months", "payment_schedule", "jurisdiction",
            "default_response_time", "renewal_policy",
            "notice_period_days",
        ]
        values = {
            field: request.form.get(field, "").strip()
            for field in fields
        }
        db.save_amc_settings(values)
        flash("AMC defaults saved.", "success")
        return redirect(url_for("amc_settings"))
    return render_template("amc_settings.html", defaults=db.get_amc_settings())


@app.route("/amc/<int:contract_id>/renew", methods=["POST"])
def renew_amc(contract_id):
    db = get_db()
    contract = db.get_amc_contract(contract_id)
    if not contract:
        flash("AMC not found.", "error")
        return redirect(url_for("amc_page"))
    input_data = contract["input_data"]
    facts = dict(input_data["facts"])
    try:
        effective = datetime.strptime(facts["end_date"], "%Y-%m-%d") + relativedelta(days=1)
    except (KeyError, ValueError):
        effective = datetime.now()
    term_months = int(facts.get("term_months", 12))
    end_date = effective + relativedelta(months=term_months) - relativedelta(days=1)
    facts.update({
        "effective_date": effective.strftime("%Y-%m-%d"),
        "effective_date_display": _display_date(effective),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "end_date_display": _display_date(end_date),
        "contract_reference": "",
    })
    try:
        job_id, _ = _queue_amc_job(
            db,
            contract["client_id"],
            {
                "facts": facts,
                "project_context": input_data.get("project_context", {}),
            },
        )
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("amc_page"))
    return redirect(url_for("job_status_page", job_id=job_id))


# ---------------------------------------------------------------------------
# Client Management
# ---------------------------------------------------------------------------
@app.route("/settings/clients")
def clients_page():
    db = get_db()
    clients = db.get_clients()
    return render_template("clients.html", clients=clients)


@app.route("/clients")
def legacy_clients_page():
    return redirect(url_for("clients_page"))


@app.route("/settings/clients/add", methods=["POST"])
@app.route("/clients/add", methods=["POST"])
def add_client():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("clients_page"))
    db = get_db()
    db.add_client(
        name=name,
        address_line1=request.form.get("address_line1", "").strip(),
        address_line2=request.form.get("address_line2", "").strip(),
        gstin=request.form.get("gstin", "").strip(),
        contact=request.form.get("contact", "").strip(),
        contact_person=request.form.get("contact_person", "").strip(),
        email=request.form.get("email", "").strip(),
        phone=request.form.get("phone", "").strip(),
        website=request.form.get("website", "").strip(),
        signatory_name=request.form.get("signatory_name", "").strip(),
        signatory_title=request.form.get("signatory_title", "").strip(),
    )
    flash(f"Added client: {name}", "success")
    return redirect(url_for("clients_page"))


@app.route("/settings/clients/update", methods=["POST"])
@app.route("/clients/update", methods=["POST"])
def update_client():
    client_id = request.form.get("client_id")
    name = request.form.get("name", "").strip()
    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("clients_page"))
    db = get_db()
    db.update_client(
        client_id=int(client_id),
        name=name,
        address_line1=request.form.get("address_line1", "").strip(),
        address_line2=request.form.get("address_line2", "").strip(),
        gstin=request.form.get("gstin", "").strip(),
        contact=request.form.get("contact", "").strip(),
        contact_person=request.form.get("contact_person", "").strip(),
        email=request.form.get("email", "").strip(),
        phone=request.form.get("phone", "").strip(),
        website=request.form.get("website", "").strip(),
        signatory_name=request.form.get("signatory_name", "").strip(),
        signatory_title=request.form.get("signatory_title", "").strip(),
    )
    flash(f"Updated client: {name}", "success")
    return redirect(url_for("clients_page"))


@app.route("/settings/clients/delete", methods=["POST"])
@app.route("/clients/delete", methods=["POST"])
def delete_client():
    client_id = request.form.get("client_id")
    db = get_db()
    client = db.get_client(int(client_id))
    db.delete_client(int(client_id))
    flash(f"Deleted client: {client['name'] if client else client_id}", "success")
    return redirect(url_for("clients_page"))


@app.route("/api/clients")
def api_clients():
    db = get_db()
    return jsonify(db.get_clients())


# ---------------------------------------------------------------------------
# GitHub API helpers (used by Add Repository modal)
# ---------------------------------------------------------------------------
@app.route("/api/github/repos")
def api_github_repos():
    q = request.args.get("q", "").strip().lower()
    try:
        client = GitHubClient()
        resp = http_requests.get(
            f"{client.api_base_url}/user/repos",
            headers=client.headers,
            params={"per_page": 100, "sort": "pushed",
                    "affiliation": "owner,collaborator,organization_member"}
        )
        resp.raise_for_status()
        names = [r["full_name"] for r in resp.json()]
        if q:
            names = [n for n in names if q in n.lower()]
        return jsonify(names[:30])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/github/branches")
def api_github_branches():
    repo = request.args.get("repo", "").strip()
    if not repo:
        return jsonify([])
    try:
        client = GitHubClient()
        resp = http_requests.get(
            f"{client.api_base_url}/repos/{repo}/branches",
            headers=client.headers,
            params={"per_page": 100}
        )
        resp.raise_for_status()
        return jsonify([b["name"] for b in resp.json()])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@app.route("/settings/company", methods=["GET", "POST"])
def company_settings():
    db = get_db()
    if request.method == "POST":
        fields = [
            "provider_name",
            "provider_owner_name",
            "provider_signatory_title",
            "provider_address",
            "provider_email",
            "provider_phone",
            "provider_website",
            "bank_details",
        ]
        values = {
            field: request.form.get(field, "").strip()
            for field in fields
        }
        if not values["provider_name"] or not values["provider_owner_name"]:
            flash(
                "Business name and authorized signatory are required.",
                "error",
            )
            return render_template(
                "company_settings.html",
                defaults={
                    **db.get_amc_settings(),
                    **values,
                    "include_bank_details": (
                        request.form.get("include_bank_details") == "on"
                    ),
                },
            )
        values["include_bank_details"] = (
            request.form.get("include_bank_details") == "on"
        )
        db.save_amc_settings(values)
        flash("Company details saved.", "success")
        return redirect(url_for("company_settings"))
    return render_template(
        "company_settings.html",
        defaults=db.get_amc_settings(),
    )


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    db = get_db()
    current = db.get_runtime_settings(_runtime_setting_defaults())

    if request.method == "POST":
        try:
            model = request.form.get("claude_model", "").strip()
            if not model:
                raise ValueError("Claude model is required.")

            budget_limit = float(
                request.form.get("ai_budget_limit", "").strip()
            )
            if not 0 <= budget_limit <= 100000:
                raise ValueError("AI budget must be between 0 and 100,000.")

            max_tokens = int(request.form.get("ai_max_tokens", "").strip())
            if not 1 <= max_tokens <= 100000:
                raise ValueError(
                    "AI token cap must be between 1 and 100,000."
                )

            max_workers = int(request.form.get("max_workers", "").strip())
            if not 1 <= max_workers <= 32:
                raise ValueError("Max workers must be between 1 and 32.")

            batch_size = int(request.form.get("batch_size", "").strip())
            if not 1 <= batch_size <= 1000:
                raise ValueError("Batch size must be between 1 and 1,000.")

            log_level = request.form.get("log_level", "INFO").strip().upper()
            if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
                raise ValueError("Select a valid log level.")

            values = {
                "GITHUB_TOKEN": current.get("GITHUB_TOKEN", ""),
                "CLAUDE_API_KEY": current.get("CLAUDE_API_KEY", ""),
                "CLAUDE_MODEL": model,
                "AI_ENABLED": request.form.get("ai_enabled") == "on",
                "AI_BUDGET_LIMIT": budget_limit,
                "AI_MAX_TOKENS": max_tokens,
                "PARALLEL_PROCESSING": (
                    request.form.get("parallel_processing") == "on"
                ),
                "MAX_WORKERS": max_workers,
                "BATCH_SIZE": batch_size,
                "LOG_LEVEL": log_level,
            }
            github_token = request.form.get("github_token", "").strip()
            claude_key = request.form.get("claude_api_key", "").strip()
            if github_token:
                values["GITHUB_TOKEN"] = github_token
            if claude_key:
                values["CLAUDE_API_KEY"] = claude_key

            db.save_runtime_settings(values)
            _apply_runtime_settings(values)
            flash(
                "Settings saved and applied to new jobs immediately.",
                "success",
            )
            return redirect(url_for("settings_page"))
        except ValueError as exc:
            flash(str(exc), "error")

    current = db.get_runtime_settings(_runtime_setting_defaults())
    usage = db.get_monthly_ai_usage()
    settings = {
        **current,
        "GITHUB_TOKEN_MASKED": _masked_secret(current.get("GITHUB_TOKEN")),
        "CLAUDE_API_KEY_MASKED": _masked_secret(
            current.get("CLAUDE_API_KEY")
        ),
        "GITHUB_TOKEN_SET": bool(current.get("GITHUB_TOKEN")),
        "CLAUDE_API_KEY_SET": bool(current.get("CLAUDE_API_KEY")),
        "MONTHLY_AI_USAGE": usage,
    }
    return render_template("settings.html", settings=settings)


# ---------------------------------------------------------------------------
# Encryption Setup
# ---------------------------------------------------------------------------
@app.route("/settings/encryption", methods=["GET", "POST"])
def encryption_setup():
    state = encryption_state()
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not password:
            flash("Password must not be empty.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            db_security.set_password(password)
            # If a plaintext DB exists, migrate it now.
            db_path = get_db_path()
            if os.path.isfile(db_path) and is_plaintext_db(db_path):
                db = RepositoryDB()
                result = db.migrate_to_encrypted(password)
                flash(result["message"], "success" if result["ok"] else "error")
            else:
                flash("Encryption password set. Database will be encrypted.", "success")
            return redirect(url_for("dashboard"))
        return render_template("setup_password.html", state=state, mode="setup")
    return render_template("setup_password.html", state=state, mode="setup")


@app.route("/settings/encryption/enter", methods=["GET", "POST"])
def enter_password():
    state = encryption_state()
    if request.method == "POST":
        password = request.form.get("password", "")
        if not password:
            flash("Password must not be empty.", "error")
            return render_template("setup_password.html", state=state, mode="enter")
        # Verify the password against the encrypted DB.
        db_path = get_db_path()
        ok, message = RepositoryDB.validate_db_file(db_path, password)
        if ok:
            db_security.set_password(password)
            flash("Database unlocked successfully.", "success")
            return redirect(url_for("dashboard"))
        flash(message, "error")
    return render_template("setup_password.html", state=state, mode="enter")


@app.route("/settings/encryption/change", methods=["POST"])
def change_encryption_password():
    if not _HAS_SQLCIPHER:
        flash("sqlcipher3 is not installed; encryption is unavailable.", "error")
        return redirect(url_for("backup_page"))

    current_pwd = request.form.get("current_password", "")
    new_pwd = request.form.get("new_password", "")
    confirm_pwd = request.form.get("confirm_password", "")

    if not current_pwd or not new_pwd:
        flash("All fields are required.", "error")
        return redirect(url_for("backup_page"))
    if len(new_pwd) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("backup_page"))
    if new_pwd != confirm_pwd:
        flash("New passwords do not match.", "error")
        return redirect(url_for("backup_page"))

    # Verify current password.
    db_path = get_db_path()
    ok, msg = RepositoryDB.validate_db_file(db_path, current_pwd)
    if not ok:
        flash("Current password is incorrect.", "error")
        return redirect(url_for("backup_page"))

    # Re-encrypt with new password: export data, re-encrypt with new key.
    db = RepositoryDB(password=current_pwd)
    # Use SQLCipher's rekey to change the password in-place.
    try:
        conn = db._connect()
        hex_new = __import__("binascii").hexlify(new_pwd.encode()).decode()
        conn.execute("PRAGMA rekey = \"x'{}'\"".format(hex_new))
        conn.close()
        db_security.set_password(new_pwd)
        flash("Encryption password changed successfully.", "success")
    except Exception as exc:
        flash("Failed to change password: {}".format(exc), "error")
    return redirect(url_for("backup_page"))


# ---------------------------------------------------------------------------
# Authentication (login / logout / password setup)
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    # If no login password is set yet, redirect to setup.
    try:
        db = get_db()
        if not db.has_login_password():
            return redirect(url_for("setup_login_password"))
    except Exception:
        pass

    if request.method == "POST":
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        try:
            db = get_db()
            stored_hash = db.get_login_password_hash()
        except Exception as exc:
            flash("Could not access database: {}".format(exc), "error")
            return render_template("login.html")

        if stored_hash and check_password_hash(stored_hash, password):
            session.permanent = remember
            session["logged_in"] = True
            next_url = request.args.get("next") or url_for("dashboard")
            # Prevent open redirect — only allow relative URLs.
            if not next_url.startswith("/"):
                next_url = url_for("dashboard")
            flash("Logged in successfully.", "success")
            return redirect(next_url)
        flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/settings/login-password", methods=["GET", "POST"])
def setup_login_password():
    """First-run login password setup, and password change."""
    try:
        db = get_db()
        has_pwd = db.has_login_password()
    except Exception:
        has_pwd = False

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        current = request.form.get("current_password", "")

        # If changing, verify current password.
        if has_pwd:
            stored_hash = db.get_login_password_hash()
            if not stored_hash or not check_password_hash(stored_hash, current):
                flash("Current password is incorrect.", "error")
                return render_template("setup_login.html", mode="change", has_password=True)

        if not password:
            flash("Password must not be empty.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            try:
                db.set_login_password(generate_password_hash(password, method=_PWD_HASH_METHOD))
                session["logged_in"] = True
                flash("Login password set successfully.", "success")
                return redirect(url_for("dashboard"))
            except Exception as exc:
                flash("Could not save password: {}".format(exc), "error")

        return render_template("setup_login.html",
                               mode="change" if has_pwd else "setup",
                               has_password=has_pwd)

    return render_template("setup_login.html",
                           mode="change" if has_pwd else "setup",
                           has_password=has_pwd)


# ---------------------------------------------------------------------------
# Backup & Restore
# ---------------------------------------------------------------------------
@app.route("/settings/backup")
def backup_page():
    db = get_db()
    info = db.get_db_info()
    enc_state = encryption_state()
    backups = []
    db_dir = os.path.dirname(info["path"])
    db_name = os.path.basename(info["path"])
    if os.path.isdir(db_dir):
        for fn in sorted(os.listdir(db_dir), reverse=True):
            if fn.startswith(db_name + ".backup_") or fn.startswith(db_name + ".plaintext_backup_"):
                full = os.path.join(db_dir, fn)
                backups.append({
                    "name": fn,
                    "rel": fn,
                    "size_kb": round(os.path.getsize(full) / 1024, 1),
                    "mtime": datetime.fromtimestamp(
                        os.path.getmtime(full)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                })
    return render_template("backup.html", info=info, backups=backups, enc_state=enc_state)


@app.route("/settings/backup/download")
def backup_download():
    db = get_db()
    info = db.get_db_info()
    if not info["exists"]:
        flash("Database file does not exist yet.", "error")
        return redirect(url_for("backup_page"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if info.get("encrypted"):
        download_name = "repositories_encrypted_{}.db".format(timestamp)
    else:
        download_name = "repositories_backup_{}.db".format(timestamp)
    return send_file(
        info["path"],
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/settings/backup/restore", methods=["POST"])
def backup_restore():
    uploaded = request.files.get("db_file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a .db file to import.", "error")
        return redirect(url_for("backup_page"))

    filename = secure_filename(uploaded.filename)
    if not filename.lower().endswith(".db"):
        flash("Only .db files are accepted.", "error")
        return redirect(url_for("backup_page"))

    password = request.form.get("import_password", "").strip()

    tmp_dir = os.path.join(PROJECT_ROOT, "data", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, "import_{}.db".format(
        datetime.now().strftime("%Y%m%d_%H%M%S")
    ))
    uploaded.save(tmp_path)
    try:
        # Detect if the uploaded file is encrypted.
        from src.core.repository_db import is_plaintext_db
        file_is_encrypted = not is_plaintext_db(tmp_path)
        if file_is_encrypted and not password:
            flash("This database is encrypted. Please enter the password used to encrypt it.", "error")
            return redirect(url_for("backup_page"))

        db = get_db()
        result = db.import_db(tmp_path, password=password if file_is_encrypted else None)
        if result["ok"]:
            msg = result["message"]
            if result["backup_path"]:
                msg += " Previous DB backed up to {}.".format(
                    os.path.basename(result["backup_path"])
                )
            flash(msg, "success")
        else:
            flash(result["message"], "error")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return redirect(url_for("backup_page"))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5050)
