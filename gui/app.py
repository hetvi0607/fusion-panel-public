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
from datetime import datetime
import calendar

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.core.config import app_config
from src.core.repository_db import RepositoryDB
from src.core.github_client import GitHubClient
from src.core.csv_reporter import CSVReporter
from src.core.ai.csv_summarizer import AICsvSummarizer
from src.core.invoice_generator import InvoiceGenerator

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.urandom(24)

logger = logging.getLogger(__name__)

# Global state for tracking report generation jobs
jobs = {}


def get_db():
    return RepositoryDB()


def get_reports_dir():
    return os.path.join(PROJECT_ROOT, "data", "reports")


def get_invoices_dir():
    return os.path.join(PROJECT_ROOT, "data", "invoices")


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
        github_client = GitHubClient()
        
        ai_summarizer = None
        if use_ai:
            try:
                ai_summarizer = AICsvSummarizer()
                jobs[job_id]['progress'] = 'AI summarizer ready'
            except Exception as e:
                jobs[job_id]['log'].append(f"AI init failed: {e}")
                use_ai = False

        all_commits = []
        for i, repo_config in enumerate(selected_repos):
            repo_name = repo_config['repo']
            branch = repo_config.get('branch')
            branch_info = f" ({branch})" if branch else ""
            jobs[job_id]['progress'] = f"Fetching {repo_name}{branch_info} ({i+1}/{len(selected_repos)})"
            try:
                commits = github_client.fetch_commits(repo_name, start_date, end_date, branch=branch)
                all_commits.extend(commits)
                jobs[job_id]['log'].append(f"✓ {repo_name}{branch_info}: {len(commits)} commits")
            except Exception as e:
                jobs[job_id]['log'].append(f"✗ {repo_name}{branch_info}: {e}")

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
    use_ai = request.form.get("use_ai") == "on"
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
@app.route("/repos")
def repos_page():
    db = get_db()
    repos = db.get_repositories(enabled_only=False)
    return render_template("repos.html", repos=repos)


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
    return render_template("generate_invoice.html",
                           repos=repos,
                           default_start=default_start,
                           default_end=default_end)


def run_invoice_job(job_id, start_date, end_date, selected_repos, repo_labels,
                    bill_to, invoice_meta):
    """Background worker that generates an invoice DOCX."""
    jobs[job_id]['status'] = 'running'
    jobs[job_id]['progress'] = 'Initializing...'
    try:
        github_client = GitHubClient()
        invoice_gen = InvoiceGenerator()

        # 1. Fetch commits
        all_commits = []
        for i, repo_config in enumerate(selected_repos):
            repo_name = repo_config['repo']
            branch = repo_config.get('branch')
            branch_info = f" ({branch})" if branch else ""
            jobs[job_id]['progress'] = f"Fetching {repo_name}{branch_info} ({i+1}/{len(selected_repos)})"
            try:
                commits = github_client.fetch_commits(repo_name, start_date, end_date, branch=branch)
                all_commits.extend(commits)
                jobs[job_id]['log'].append(f"\u2713 {repo_name}{branch_info}: {len(commits)} commits")
            except Exception as e:
                jobs[job_id]['log'].append(f"\u2717 {repo_name}{branch_info}: {e}")

        if not all_commits:
            jobs[job_id]['status'] = 'done'
            jobs[job_id]['progress'] = 'No commits found'
            jobs[job_id]['result'] = {'total_commits': 0}
            return

        # 2. AI categorization
        jobs[job_id]['progress'] = f"AI categorizing {len(all_commits)} commits..."
        work_details = invoice_gen.categorize_commits(all_commits, repo_labels)
        jobs[job_id]['log'].append(
            f"AI returned {len(work_details)} work categories"
        )

        # 3. Generate DOCX
        jobs[job_id]['progress'] = 'Generating DOCX invoice...'
        invoices_dir = get_invoices_dir()
        date_slug = datetime.strptime(start_date, '%Y-%m-%d').strftime('%B-%Y').lower()
        invoice_no = invoice_meta.get('invoice_no', 'draft')
        filename = f"invoice_{invoice_no}_{date_slug}.docx"
        output_path = os.path.join(invoices_dir, filename)

        invoice_gen.generate_invoice(
            work_details=work_details,
            bill_to=bill_to,
            invoice_meta=invoice_meta,
            output_path=output_path,
        )

        usage = invoice_gen.get_usage_stats()
        jobs[job_id]['log'].append(
            f"Invoice generated \u2013 cost: ${usage['estimated_cost']:.4f}, tokens: {usage['total_tokens']}"
        )

        jobs[job_id]['status'] = 'done'
        jobs[job_id]['progress'] = 'Complete'
        jobs[job_id]['result'] = {
            'total_commits': len(all_commits),
            'invoice_path': output_path,
            'invoice_filename': filename,
            'date_range': f"{start_date} to {end_date}",
            'categories': len(work_details),
        }
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['progress'] = f"Error: {e}"
        jobs[job_id]['log'].append(str(e))


@app.route("/invoice", methods=["POST"])
def generate_invoice():
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    selected_repo_ids = request.form.getlist("repos")

    db = get_db()
    all_repos = db.get_repositories(enabled_only=True)

    if selected_repo_ids:
        selected_repos = [r for r in all_repos if f"{r['repo']}:{r['branch']}" in selected_repo_ids]
    else:
        selected_repos = all_repos

    if not selected_repos:
        flash("No repositories selected.", "error")
        return redirect(url_for("invoice_page"))

    # Collect repo labels from form
    repo_labels = {}
    for r in selected_repos:
        key = f"label_{r['repo']}:{r['branch']}"
        label = request.form.get(key, "").strip()
        if label:
            repo_labels[r['repo']] = label

    # Billing info
    bill_to = {
        "name": request.form.get("bill_to_name", "").strip(),
        "address_line1": request.form.get("bill_to_addr1", "").strip(),
        "address_line2": request.form.get("bill_to_addr2", "").strip(),
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
              bill_to, invoice_meta),
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
# Settings
# ---------------------------------------------------------------------------
@app.route("/settings")
def settings_page():
    settings = {
        'GITHUB_TOKEN': '***' + (app_config.GITHUB_TOKEN[-4:] if app_config.GITHUB_TOKEN else ''),
        'CLAUDE_API_KEY': '***' + (app_config.CLAUDE_API_KEY[-4:] if app_config.CLAUDE_API_KEY else ''),
        'CLAUDE_MODEL': app_config.CLAUDE_MODEL,
        'AI_ENABLED': app_config.AI_ENABLED,
        'AI_BUDGET_LIMIT': app_config.AI_BUDGET_LIMIT,
        'AI_MAX_TOKENS': app_config.AI_MAX_TOKENS,
        'PARALLEL_PROCESSING': app_config.PARALLEL_PROCESSING,
        'MAX_WORKERS': app_config.MAX_WORKERS,
        'BATCH_SIZE': app_config.BATCH_SIZE,
        'LOG_LEVEL': app_config.LOG_LEVEL,
        'WHATSAPP_ENABLED': app_config.WHATSAPP_ENABLED,
        'ENVIRONMENT': os.getenv("ENVIRONMENT", "development"),
    }
    return render_template("settings.html", settings=settings)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5050)
