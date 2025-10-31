#!/usr/bin/env python3
"""
BlueQubit Quantum Job Tracker - Backend
Simulates quantum computing jobs with Flask backend
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from flask_cors import CORS
import random
import time
import threading
from datetime import datetime
import os
from zoneinfo import ZoneInfo
from typing import List, Dict, Any
from functools import wraps

app = Flask(__name__)
CORS(app)

# NOTE: replace with a secure random key for production
app.secret_key = 'dev-secret-change-me'


# Display timezone for timestamps (can be set via DISPLAY_TZ environment variable)
# Example: DISPLAY_TZ="Asia/Kolkata". Defaults to UTC if not set or invalid.
def get_display_tz() -> str:
    return app.config.get('DISPLAY_TZ') or os.environ.get('DISPLAY_TZ') or 'UTC'


def now_iso() -> str:
    """Return current time as ISO 8601 string with timezone info using zoneinfo.

    Uses the timezone name from DISPLAY_TZ (app config or env). Falls back to UTC.
    """
    tz_name = get_display_tz()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo('UTC')
    return datetime.now(tz=tz).isoformat()

# Simple hard-coded user store for demo purposes
USERS = {
    'admin': 'admin',
    'akhil': 'akhil'
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

class BlueQubitJobSimulator:
    """Simulates quantum computing jobs for BlueQubit"""

    def __init__(self, max_jobs: int = 200):
        self.jobs: List[Dict[str, Any]] = []
        self.job_counter = 1
        self.running = True
        self.max_jobs = max_jobs
        self.start_simulation()

    def create_job(self, manual: bool = False) -> Dict[str, Any]:
        """Create a new quantum job"""
        job = {
            'id': f'BQJ-{self.job_counter}',
            'type': random.choice([
                "Quantum Fourier Transform",
                "Variational Quantum Eigensolver",
                "Grover's Algorithm",
                "Quantum Phase Estimation"
            ]),
            'status': 'QUEUED',
            # store timezone-aware ISO timestamp
            'created_at': now_iso(),
            'estimated_runtime': random.randint(30, 300),  # seconds
            'success_probability': random.uniform(85.0, 99.5),
            'manual': manual
        }
        self.job_counter += 1
        self.jobs.append(job)

        # keep list size under control
        if len(self.jobs) > self.max_jobs:
            self.jobs.pop(0)

        return job

    def update_jobs(self):
        """Update job statuses"""
        for job in self.jobs:
            if job['status'] == 'QUEUED':
                if random.random() < 0.4:  # 40% chance to start running
                    job['status'] = 'RUNNING'
            elif job['status'] == 'RUNNING':
                if random.random() < 0.3:  # 30% chance to finish
                    job['status'] = 'COMPLETED' if random.random() < job['success_probability'] / 100 else 'FAILED'

    def get_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get jobs with optional limit"""
        # Sort jobs by status (RUNNING first, then QUEUED, then FAILED, then COMPLETED)
        status_order = {'RUNNING': 0, 'QUEUED': 1, 'FAILED': 2, 'COMPLETED': 3}
        sorted_jobs = sorted(self.jobs, key=lambda j: (status_order[j['status']], j['created_at']))
        return sorted_jobs[-limit:]

    def clear_completed(self) -> int:
        """Remove all completed jobs and return count of removed jobs"""
        completed_count = len([j for j in self.jobs if j['status'] == 'COMPLETED'])
        self.jobs = [j for j in self.jobs if j['status'] != 'COMPLETED']
        return completed_count

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get a specific job by ID"""
        for job in self.jobs:
            if job['id'] == job_id:
                return job
        return {}

    def simulation_loop(self):
        """Main simulation loop"""
        while self.running:
            # 50% chance to auto-create a new job
            if random.random() < 0.5:
                self.create_job()
            self.update_jobs()
            time.sleep(2)  # Update every 2 seconds

    def start_simulation(self):
        """Start the simulation in a separate thread"""
        self.sim_thread = threading.Thread(target=self.simulation_loop, daemon=True)
        self.sim_thread.start()


# NOTE: In production (gunicorn) there may be multiple worker processes.
# In-memory state is NOT shared between workers. To ensure the background
# simulator thread runs inside each worker process, we instantiate it lazily
# on the first request handled by that worker. This is a mitigation — for
# a robust production setup use a shared datastore (Redis/Postgres) and a
# separate worker (RQ/Celery) to process jobs.
simulator: BlueQubitJobSimulator | None = None


def start_simulator_once() -> None:
    """Start the simulator if it's not already running in this process."""
    global simulator
    if simulator is None:
        simulator = BlueQubitJobSimulator()


# Ensure the simulator starts when the first request arrives in this worker.
# Flask 3 removed `before_first_request`; use `before_request` which exists
# in Flask 3 and call an idempotent startup helper.
@app.before_request
def _ensure_simulator_started():
    start_simulator_once()


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Render login page and handle auth"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username in USERS and USERS[username] == password:
            session['user'] = username
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        error = 'Invalid username or password'
        return render_template('login.html', error=error)
    return render_template('login.html')


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Log out current user"""
    session.clear()  # remove all session data
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Serve the main dashboard"""
    return render_template('dashboard.html', user=session.get('user'))


@app.route('/api/jobs')
def get_jobs_api():
    """API endpoint to get quantum jobs"""
    limit = int(request.args.get('limit', 50))
    start_simulator_once()
    jobs = simulator.get_jobs(limit)
    return jsonify({'jobs': jobs, 'success': True})


@app.route('/api/job/<job_id>')
def get_job_api(job_id):
    """Get details of a single job"""
    start_simulator_once()
    job = simulator.get_job(job_id)
    if job:
        return jsonify({'job': job, 'success': True})
    return jsonify({'error': 'Job not found', 'success': False}), 404


@app.route('/api/create_job', methods=['POST'])
def create_job_api():
    """Manually create a job"""
    start_simulator_once()
    job = simulator.create_job(manual=True)
    return jsonify({'job': job, 'success': True})


@app.route('/api/clear_completed', methods=['POST'])
def clear_completed_api():
    """Clear all completed jobs"""
    start_simulator_once()
    removed_count = simulator.clear_completed()
    return jsonify({
        'success': True,
        'message': f'Cleared {removed_count} completed jobs',
        'removed_count': removed_count
    })


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': now_iso()})


@app.route('/api/sim_status')
def sim_status():
    """Return basic simulator status for debugging (worker-local)."""
    start_simulator_once()
    return jsonify({
        'running': bool(simulator and simulator.running),
        'jobs_count': len(simulator.jobs) if simulator else 0,
        'sample_job': simulator.jobs[-1] if (simulator and simulator.jobs) else None,
    })


@app.route('/api/auth/google', methods=['POST'])
def auth_google():
    """Receive Google ID token from the client and create a session.

    WARNING: This endpoint is a development helper. It does NOT verify the
    token unless you implement proper verification with Google's OAuth2
    token verification in production. For local testing we accept the token
    when `app.debug` is True or when env `ALLOW_DEV_GOOGLE_UNVERIFIED=1`.
    """
    payload = request.get_json(silent=True) or {}
    id_token = payload.get('id_token')
    if not id_token:
        return jsonify({'success': False, 'error': 'missing id_token'}), 400

    allow_dev = app.debug or os.environ.get('ALLOW_DEV_GOOGLE_UNVERIFIED') == '1'
    if allow_dev:
        # WARNING: do NOT use this in production. Verify the token with
        # google.oauth2.id_token.verify_oauth2_token and check audience.
        session['user'] = 'google_user'
        return jsonify({'success': True, 'redirect': url_for('index')})

    return jsonify({
        'success': False,
        'error': 'server not configured to verify Google tokens. Implement verification or set ALLOW_DEV_GOOGLE_UNVERIFIED=1 for dev'
    }), 501


if __name__ == '__main__':
    print("Starting BlueQubit Quantum Job Tracker...")
    # start simulator for local dev server
    start_simulator_once()
    app.run(debug=True, host='0.0.0.0', port=5003)
