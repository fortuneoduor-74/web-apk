# 👑 CRITICAL FOR EVENTLET: Monkey patch MUST be the absolute first two lines of execution!
import eventlet
eventlet.monkey_patch()

import os
import secrets
import random  
import time
import logging
from functools import wraps
from concurrent.futures import ThreadPoolExecutor 
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename 
from flask_socketio import SocketIO, emit 

from models import db, User, Ad, Job, JobSubmission

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

# 👑 DATABASE SELECTION ENGINE: Supports Render Postgres or scales down to SQLite smoothly
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:///' + os.path.join(app.instance_path, 'platform.db') + '?timeout=30'
)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(app.instance_path, 'proofs')
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  

ADMIN_USERNAME = os.environ.get('DEFAULT_ADMIN_USER', 'fabian')
ADMIN_EMAIL = os.environ.get('DEFAULT_ADMIN_EMAIL', 'fortuneoduor@gmail.com')

# 🛡️ RENDERING THREAD PROTECTION: Built-in pool prevents HTTP gateway request timeouts
bg_executor = ThreadPoolExecutor(max_workers=2)

# 🛫 WEBSOCKET INITIALIZER: Left dynamic for Eventlet runtime binding auto-detection
socketio = SocketIO(app, cors_allowed_origins="*")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Unauthorized access node.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def game_rate_limit(seconds=1.5):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            endpoint = request.endpoint
            now = time.time()
            last_action_key = f"rate_{endpoint}_{current_user.id}"
            last_action = session.get(last_action_key, 0)
            if now - last_action < seconds:
                return jsonify({"success": False, "message": f"Please wait {seconds}s before retrying."})
            session[last_action_key] = now
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Seed Structural Tables
with app.app_context():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    db.create_all()
    if not Ad.query.first():
        db.session.bulk_save_objects([
            Ad(title="Premium Node Advertisement 101", reward=15.50, video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            Ad(title="High-Yield Network Stream Alpha", reward=22.00, video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        ])
        db.session.commit()
    if not Job.query.first():
        db.session.bulk_save_objects([
            Job(title="Verify Platform Smart Node Connection", description="Submit a PDF proof demonstrating complete connection link setup.", reward=120.00),
            Job(title="System Stress Test Data Submission", description="Provide complete output logs showing low-latency data arrays.", reward=350.00)
        ])
        db.session.commit()

    target_admin = User.query.filter((User.username == ADMIN_USERNAME) | (User.email == ADMIN_EMAIL)).first()
    if not target_admin:
        db.session.add(User(
            username=ADMIN_USERNAME, email=ADMIN_EMAIL,
            password_hash=generate_password_hash("admin123", method='scrypt'),
            referral_code="ADMINNODE", balance=1000.0, is_activated=True, is_admin=True
        ))
        db.session.commit()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        ref_by = request.form.get('ref')
        
        if len(password) < 8:
            flash('Registration failed: Password string must be at least 8 characters long.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Registration failed: User credentials matching configuration already mapped.', 'danger')
            return redirect(url_for('register'))
            
        try:
            new_user = User(username=username, email=email, password_hash=generate_password_hash(password, method='scrypt'), referral_code=secrets.token_hex(4).upper(), balance=0.0, is_activated=False)
            if ref_by and User.query.filter_by(referral_code=ref_by).first():
                new_user.referred_by = ref_by
            db.session.add(new_user)
            db.session.commit()
            flash('Registration complete. Sign in below.', 'success')
            return redirect(url_for('login'))
        except Exception:
            db.session.rollback()
            flash('Database busy. Try again.', 'danger')
    return render_template('register.html', ref=request.args.get('ref', ''))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', ads=Ad.query.all(), jobs=Job.query.all(), completed_job_ids=[s.job_id for s in JobSubmission.query.filter_by(user_id=current_user.id).all()])

# ==============================================================================
# 📲 SANDBOXED M-PESA DARAJA WEBHOOK HANDLER
# ==============================================================================
def simulate_mpesa_daraja_webhook(app_context, user_id):
    time.sleep(4) 
    with app_context:
        try:
            user_db = db.session.query(User).filter(User.id == user_id).with_for_update().first()
            if user_db and not user_db.is_activated:
                user_db.is_activated = True
                if user_db.referred_by:
                    inviter = db.session.query(User).filter(User.referral_code == user_db.referred_by).with_for_update().first()
                    if inviter:
                        inviter.balance += 300.00
                        inviter.referral_count += 1
                db.session.commit()
        except Exception as e:
            db.session.rollback()

@app.route('/activate-account', methods=['POST'])
@login_required
def activate_account():
    if current_user.is_activated:
        return redirect(url_for('dashboard'))
    bg_executor.submit(simulate_mpesa_daraja_webhook, app.app_context(), current_user.id)
    flash('📲 Lipa Na M-PESA STK Push Sim Sent! Enter any dummy PIN string. Simulating verification...', 'info')
    return redirect(url_for('dashboard'))

@app.route('/api/v1/mpesa/check-status')
@login_required
def mpesa_check_status():
    return jsonify({"activated": current_user.is_activated})

# ==============================================================================
# REWARDS MATRIX
# ==============================================================================
@app.route('/watch-ad/<int:ad_id>')
@login_required
def watch_ad(ad_id):
    if not current_user.is_activated:
        flash('Please activate your node connection first.', 'warning')
        return redirect(url_for('dashboard'))
    return render_template('watch.html', ad=Ad.query.get_or_404(ad_id))

@app.route('/claim-reward/<int:ad_id>', methods=['POST'])
@login_required
@game_rate_limit(seconds=2.0)
def claim_reward(ad_id):
    if not current_user.is_activated: return redirect(url_for('dashboard'))
    target_ad = Ad.query.get_or_404(ad_id)
    try:
        user_db = db.session.query(User).filter(User.id == current_user.id).with_for_update().first()
        user_db.balance += target_ad.reward
        db.session.commit()
        flash(f'Successfully claimed {target_ad.reward} KSH view payout.', 'success')
    except Exception:
        db.session.rollback()
    return redirect(url_for('dashboard'))

# ==============================================================================
# COINFLIP ARCADE ENGINE
# ==============================================================================
@app.route('/play/coinflip', methods=['POST'])
@login_required
@game_rate_limit(seconds=1.0)
def play_coinflip():
    if not current_user.is_activated: return jsonify({"success": False, "message": "Activate account first."})
    data = request.get_json() or {}
    try: stake = round(float(data.get('bet_amount', 0)), 2)
    except ValueError: return jsonify({"success": False, "message": "Invalid format."})
    prediction = str(data.get('chosen_side', '')).lower()
    
    if stake <= 0 or current_user.balance < stake: return jsonify({"success": False, "message": "Insufficient balance."})
    result = random.choice(['heads', 'tails'])
    
    try:
        user_db = db.session.query(User).filter(User.id == current_user.id).with_for_update().first()
        if prediction == result:
            user_db.balance += stake
            msg = f" landed on {result.upper()}! You won {stake} KSH!"
        else:
            user_db.balance -= stake
            msg = f" landed on {result.upper()}. You lost {stake} KSH."
        db.session.commit()
        return jsonify({"success": True, "message": msg, "new_balance": float(user_db.balance)})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Database busy."})

# ==============================================================================
# AVIATOR WEB-SOCKET CONTROLLER
# ==============================================================================
active_flights = {}

@socketio.on('join_aviator')
def on_join(data):
    user_id = data.get('user_id')
    if not user_id: return
    if user_id in active_flights: active_flights[user_id]['active'] = False
    
    crash_point = 1.00 if random.random() < 0.12 else round(1.01 + (0.05 / (1.0 - random.uniform(0.01, 0.98))**1.35), 2)
    if crash_point > 40.0: crash_point = 40.0
    
    active_flights[user_id] = {
        'crash_point': crash_point, 'start_time': time.time(), 'active': True, 'stake': round(float(data.get('stake', 0)), 2)
    }
    emit('flight_started', {'status': 'launched'})

@socketio.on('request_multiplier_tick')
def on_tick(data):
    user_id = data.get('user_id')
    flight = active_flights.get(user_id)
    if not flight or not flight['active']: return
    
    elapsed = time.time() - flight['start_time']
    current_mult = round(1.00 + (elapsed * 0.15), 2)
    
    if current_mult >= flight['crash_point']:
        flight['active'] = False
        emit('flight_crashed', {'crash_point': flight['crash_point']})
    else:
        emit('tick_update', {'multiplier': current_mult})

@socketio.on('claim_cashout')
def on_cashout(data):
    user_id = data.get('user_id')
    flight = active_flights.get(user_id)
    if not flight or not flight['active']: return
    
    flight['active'] = False
    elapsed = time.time() - flight['start_time']
    final_mult = round(1.00 + (elapsed * 0.15), 2)
    
    if final_mult >= flight['crash_point']:
        emit('cashout_result', {'success': False, 'message': 'Too late! Plane burst.'})
        return
        
    winnings = round(flight['stake'] * final_mult, 2)
    try:
        user_db = db.session.query(User).filter(User.id == int(user_id)).with_for_update().first()
        user_db.balance += winnings
        db.session.commit()
        emit('cashout_result', {'success': True, 'winnings': winnings, 'new_balance': float(user_db.balance), 'message': f"🛫 Clean Cashout at {final_mult}x! Earned {winnings} KSH."})
    except Exception:
        db.session.rollback()

# ==============================================================================
# ESCROW MODULE & ADMINISTRATION PANEL
# ==============================================================================
@app.route('/submit-job-proof/<int:job_id>', methods=['POST'])
@login_required
def submit_job_proof(job_id):
    if not current_user.is_activated: return redirect(url_for('dashboard'))
    job = Job.query.get_or_404(job_id)
    if JobSubmission.query.filter_by(user_id=current_user.id, job_id=job_id).first(): return redirect(url_for('dashboard'))
    
    proof_text = request.form.get('proof_text', '').strip()
    file_saved_name = None
    
    if 'proof_file' in request.files:
        file = request.files['proof_file']
        if file and file.filename != '' and allowed_file(file.filename):
            file_saved_name = f"{secrets.token_hex(4)}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_saved_name))
            
    db.session.add(JobSubmission(user_id=current_user.id, job_id=job.id, proof_text=proof_text or None, file_path=file_saved_name))
    db.session.commit()
    flash('Verification proof sent. Awaiting review.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/panel')
@login_required
@admin_required
def admin_panel():
    page = request.args.get('page', 1, type=int)
    pag = User.query.order_by(User.id.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('admin_dashboard.html', users=pag.items, pagination=pag, pending_submissions=JobSubmission.query.filter_by(status='Pending').all(), ads=Ad.query.all())

def background_file_purge(file_path):
    if file_path and os.path.exists(file_path):
        try: os.remove(file_path)
        except Exception: pass

@app.route('/admin/reject-submission/<int:sub_id>', methods=['POST'])
@login_required
@admin_required
def reject_submission(sub_id):
    sub = JobSubmission.query.get_or_404(sub_id)
    if sub.status == 'Pending':
        sub.status = 'Rejected'
        if sub.file_path:
            bg_executor.submit(background_file_purge, os.path.join(app.config['UPLOAD_FOLDER'], sub.file_path))
        db.session.commit()
        flash('Submission dropped.', 'info')
    return redirect(url_for('admin_panel'))

@app.route('/admin/approve-submission/<int:sub_id>', methods=['POST'])
@login_required
@admin_required
def approve_submission(sub_id):
    sub = JobSubmission.query.get_or_404(sub_id)
    if sub.status == 'Pending':
        sub.status = 'Approved'
        user_db = db.session.query(User).filter(User.id == sub.user_id).with_for_update().first()
        user_db.balance += Job.query.get(sub.job_id).reward
        db.session.commit()
        flash('Payout approved.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user_activation(user_id):
    u = User.query.get_or_404(user_id)
    if u.id != current_user.id:
        u.is_activated = not u.is_activated
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/download-proof/<string:filename>')
@login_required
@admin_required
def download_proof(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
