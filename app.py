import io
import cv2
import secrets 
import numpy as np
import faiss
from flask import Flask, json, jsonify, render_template, request, redirect, url_for, flash, send_file, session, Response, abort
from functools import wraps
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from PIL import Image as PILImage 
import traceback
import re
import database as db 
from ml_utils import MLModel
from pdf_extractor import UltraRobustExtractor, extract_all 
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import imagehash
from difflib import SequenceMatcher
import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
print("Running script:", __file__, "CWD:", os.getcwd(), flush=True)
load_dotenv()

print("ENV LOADED:", os.getenv("FLASK_RUN_HOST"), os.getenv("FLASK_RUN_PORT"), flush=True)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_key_only_for_local_use')

# --- Law Firm Configuration ---
app.config['EXACT_MATCH_THRESHOLD'] = 0.05 

# --- INITIALIZE THE EMAIL USING ENV VARIABLES ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
#app.config['MAIL_SERVER'] = 
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'False'
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
#app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')



# Setting the default sender as a tuple
app.config['MAIL_DEFAULT_SENDER'] = (
    os.getenv('MAIL_SENDER_NAME'), 
    os.getenv('MAIL_SENDER_EMAIL')
)
mail = Mail(app)

# --- INITIALIZE THE MODELS ---
ml_model = MLModel()
ml_model.build_logo_index() 

# ===============================================================================================
# AUTHENTICATION DECORATORS & BASIC ROUTES
# ===============================================================================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed_roles = ['admin', 'manager']
        if 'role' not in session or session['role'].lower() not in allowed_roles:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('menu'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/menu')
def menu():
    if not session.get('logged_in'):
        return redirect(url_for('signin'))
    return render_template('menu.html')

# ===============================================================================================
# SIGN-IN / REGISTRATION / LOGOUT
# ===============================================================================================

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')
        user     = db.get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['user_id']   = user['id']
            session['username']  = user['username']
            session['role']      = user['role']
            
            if user['is_temporary_password']:
                session['force_password_change'] = True
                flash('Please create a new password to secure your account.', 'info')
                return redirect(url_for('change_password'))

            flash(f'Welcome back, {user["username"]}!', 'success')
            
            user_role = user['role'].lower()
            if user_role in ['admin', 'manager']:
                return redirect(url_for('admin_page'))
            else:
                return redirect(url_for('menu'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('signin.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username, email, password = request.form.get('username'), request.form.get('email'), request.form.get('password')
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        try:
            db.add_user(username, email, password_hash)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('signin'))
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out.', 'info')
    return redirect(url_for('signin'))

# ===============================================================================================
# USER MANAGEMENT API
# ===============================================================================================

@app.route('/admin')
@admin_required
def admin_page():
    return render_template('admin.html')

@app.route('/user-management')
@admin_required
def user_management():
    all_users = db.get_all_users()
    return render_template('user_management.html', users=all_users)

@app.route('/api/users/add', methods=['POST'])
@admin_required
def api_add_user():
    data                  = request.get_json()
    username, email, role = data.get('name'), data.get('email'), data.get('role')

    if not all([username, email, role]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    try:
        temp_password = secrets.token_urlsafe(10)
        password_hash = generate_password_hash(temp_password)
        db.add_user(username, email, password_hash) 
        new_user = db.get_user_by_email(email)
        db.update_user_role(new_user['id'], role)

        msg      = Message('Your MarkLogic Account has been Created', recipients=[email])
        msg.body = f"Hello {username},\n\nYour temporary password is: {temp_password}\n\nPlease change it on login."
        mail.send(msg)
        return jsonify({'success': True, 'message': f'Invitation sent to {email}!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/edit', methods=['POST'])
@admin_required
def api_edit_user():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid JSON body'}), 400

    user_id = data.get('id')
    name    = data.get('name')
    email   = data.get('email')

    if not user_id or not name or not email:
        return jsonify({'success': False, 'message': 'ID, name, and email are required.'}), 400

    try:
        db.update_user_details(user_id, name, email)
        return jsonify({'success': True, 'message': 'User updated successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/delete/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    if session.get('user_id') == user_id:
        return jsonify({'success': False, 'message': 'Cannot delete yourself.'}), 403
    try:
        db.delete_user_by_id(user_id)
        return jsonify({'success': True, 'message': 'User deleted.'})
    except Exception:
        return jsonify({'success': False, 'message': 'Failed to delete user.'}), 500

@app.route('/api/users/update_role', methods=['POST'])
@admin_required
def api_update_role():
    data = request.get_json()
    try:
        db.update_user_role(data.get('user_id'), data.get('role'))
        return jsonify({'success': True, 'message': 'Role updated.'})
    except Exception:
        return jsonify({'success': False, 'message': 'Update failed.'}), 500

@app.route('/api/users/admin_reset_password', methods=['POST'])
@admin_required
def api_admin_reset_password():
    data                  = request.get_json()
    user_id, new_password = data.get('id'), data.get('password')
    try:
        db.admin_reset_password(user_id, generate_password_hash(new_password))
        return jsonify({'success': True, 'message': 'Password reset. Inform the user.'})
    except Exception:
        return jsonify({'success': False, 'message': 'Reset failed.'}), 500

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'force_password_change' not in session:
        return redirect(url_for('menu'))
    if request.method == 'POST':
        pw, conf = request.form.get('password'), request.form.get('password_confirm')
        if pw == conf:
            db.update_password_and_deactivate_temp_flag(session['user_id'], generate_password_hash(pw))
            session.pop('force_password_change', None)
            flash('Password updated!', 'success')
            user_role = session.get('role', '').lower()
            if user_role in ['admin', 'manager']:
                return redirect(url_for('admin_page'))
            else:
                return redirect(url_for('menu'))
        flash('Passwords do not match.', 'danger')
    return render_template('change_password.html')

# ===============================================================================================
# DATASET & JOURNAL UPLOAD
# ===============================================================================================

@app.route('/dataset')
def dataset():
    return render_template('dataset.html')

@app.route('/client-dataset')
def client_dataset():
    return render_template('client-dataset.html')

# ==============================================================================
# MYIPO TRADEMARK UPLOAD
# ==============================================================================

@app.route('/upload-journal/<category>', methods=['POST'])
@admin_required 
def upload_journal(category):
    file  = request.files.get('file')
    batch = request.form.get('batch_number')
    year  = request.form.get('batch_year')

    if not file or not batch or not year:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400

    file_bytes = file.read()

    def generate():
        try:
            raw_data  = []
            extractor = UltraRobustExtractor() 

            for update in extractor.extract_all(io.BytesIO(file_bytes)):
                status = update.get('status')
                if status == 'extracting':
                    yield json.dumps(update) + "\n"
                elif status == 'extraction_complete':
                    raw_data = update.get('results', [])

            total_records = len(raw_data)
            if total_records == 0:
                yield json.dumps({"status": "error", "message": "No trademarks found in PDF."}) + "\n"
                return

            inserted = 0
            for tm in raw_data:
                if tm.get("block_snapshot") and not tm.get("evidence_snapshot"):
                    tm["evidence_snapshot"] = tm["block_snapshot"]

                tm.update({'category': category, 'batch_number': batch, 'batch_year': year})

                combined_text = f"{tm.get('trademark_name','')} {tm.get('description','')}".strip()
                if combined_text:
                    tm['text_embedding'] = ml_model.generate_text_embedding(combined_text)

                if tm.get('logo_data'):
                    tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))

                db.insert_trademark(tm)
                inserted += 1

                db_percent = int((inserted / total_records) * 100)
                yield json.dumps({
                    "status":     "inserting", 
                    "percentage": db_percent, 
                    "current":    inserted, 
                    "total":      total_records
                }) + "\n"

            ml_model.build_logo_index()
            yield json.dumps({
                "status":  "complete", 
                "success": True, 
                "message": f"Successfully imported {inserted} records."
            }) + "\n"

        except Exception as e:
            traceback.print_exc()
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

# ==============================================================================
# CLIENT TRADEMARK UPLOAD
# ==============================================================================

@app.route('/upload-client-dataset', methods=['POST'])
@admin_required
def upload_client_dataset():
    file           = request.files.get('file')
    user_file_name = request.form.get('user_file_name', 'Unnamed')
    user_date      = request.form.get('user_date')

    if not file:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400

    file_bytes = file.read()
    filename   = file.filename.lower()

    def generate():
        try:
            if filename.endswith('.pdf'):
                extractor = UltraRobustExtractor()
                
                for update in extractor.extract_all(io.BytesIO(file_bytes), start_page=1):
                    if update.get('status') == 'extraction_complete':
                        results = update.get('results', [])
                        total   = len(results)
                        
                        for idx, tm in enumerate(results):
                            emb = None
                            if tm.get('logo_data'):
                                emb = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))
                            
                            db.insert_client_trademark({
                                'file_name':      user_file_name,
                                'logo_data':      tm.get('logo_data'),
                                'logo_embedding': emb,
                                'applicant_name': tm.get('applicant_name') or user_file_name,
                                'description':    tm.get('description') or "Extracted from PDF",
                                'custom_date':    user_date
                            })

                            yield json.dumps({
                                "status":     "inserting", 
                                "percentage": int(((idx+1)/total)*100)
                            }) + "\n"
                    else:
                        yield json.dumps(update) + "\n"

            else:
                yield json.dumps({"status": "extracting", "percentage": 50}) + "\n"
                clean_logo = extract_logo_from_bytes(file_bytes)
                emb        = ml_model.generate_image_embedding(io.BytesIO(clean_logo))
                
                db.insert_client_trademark({
                    'file_name':      user_file_name,
                    'logo_data':      clean_logo,
                    'logo_embedding': emb,
                    'applicant_name': user_file_name,
                    'description':    "Manual Image Upload",
                    'custom_date':    user_date
                })
                yield json.dumps({"status": "complete", "success": True, "message": "Image saved to client dataset."}) + "\n"
                return

            yield json.dumps({"status": "complete", "success": True, "message": "Dataset updated successfully."}) + "\n"

        except Exception as e:
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

# ==============================================================================
# CLIENT TRADEMARKS — Manage Tab API
# ==============================================================================

@app.route('/api/client-trademarks', methods=['GET'])
@admin_required
def api_get_client_trademarks():
    search_query = request.args.get('q', '').strip()
    
    conn = db.get_db_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if search_query:
        sql = """
            SELECT id, applicant_name, description, upload_date 
            FROM client_trademarks 
            WHERE applicant_name ILIKE %s OR description ILIKE %s 
            ORDER BY upload_date DESC
        """
        cur.execute(sql, (f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute("SELECT id, applicant_name, description, upload_date FROM client_trademarks ORDER BY upload_date DESC")
    
    rows    = cur.fetchall()
    results = []
    for r in rows:
        results.append({
            'id':             r['id'],
            'applicant_name': r['applicant_name'],
            'description':    r['description'],
            'upload_date':    str(r['upload_date']) if r['upload_date'] else "N/A"
        })
        
    cur.close()
    conn.close()
    return jsonify(results)

@app.route('/api/client-trademarks', methods=['DELETE'])
@admin_required
def api_delete_client_trademarks():
    data = request.get_json()
    ids  = data.get('ids', [])
    if not ids:
        return jsonify({'success': False}), 400
    
    conn = db.get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM client_trademarks WHERE id = ANY(%s)", (ids,))
    conn.commit()
    deleted = cur.rowcount
    cur.close(); conn.close()
    return jsonify({'success': True, 'deleted': deleted})

@app.route('/client-logo/<int:client_id>')
def get_client_logo_route(client_id):
    logo_data = db.get_client_logo(client_id)
    if logo_data:
        return send_file(io.BytesIO(logo_data), mimetype='image/png')
    return "Not found", 404

# ==============================================================================
# TRADEMARKS — Search & Manage API
# ==============================================================================

@app.route('/api/trademarks', methods=['GET'])
def api_trademarks():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    batch        = request.args.get('batch_number')
    year         = request.args.get('batch_year')
    q            = request.args.get('q')
    class_filter = request.args.get('class')

    if q or class_filter:
        rows = db.search_trademarks(words=q, class_filter=class_filter)
    else:
        rows = db.get_all_trademarks_manageTab()

    results = []
    for row in rows:
        r = dict(row)

        if batch and str(r.get('batch_number', '')) != str(batch):
            continue
        if year and str(r.get('batch_year', '')) != str(year):
            continue

        if r.get('file_name'):
            display_name = r.get('file_name')
        elif r.get('batch_number') and r.get('batch_year'):
            display_name = f"{r.get('batch_number')}/{r.get('batch_year')}.pdf"
        else:
            display_name = r.get('serial_number') or f"id-{r.get('id')}"

        results.append({
            'id':             r.get('id'),
            'serial_number':  r.get('serial_number'),
            'display_name':   display_name,
            'trademark_name': r.get('trademark_name'),
            'class_indices':  r.get('class_indices'),
            'applicant_name': r.get('applicant_name'),
            'description':    r.get('description'),
            'batch_number':   r.get('batch_number'),
            'batch_year':     r.get('batch_year'),
            'category':       r.get('category'),
            'is_split':       r.get('is_split'),
            'has_logo':       bool(r.get('has_logo'))
        })

    return jsonify({'success': True, 'trademarks': results})

@app.route('/api/trademarks', methods=['DELETE'])
@admin_required
def api_delete_trademarks():
    data = request.get_json(silent=True) or {}
    ids  = data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({'success': False, 'message': 'Provide ids list in JSON body.'}), 400

    deleted = 0
    errors  = []
    for tid in ids:
        try:
            db.delete_trademark_by_id(tid)
            deleted += 1
        except Exception as e:
            errors.append({'id': tid, 'error': str(e)})

    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})

# ===============================================================================================
# SEARCH & TEXT/IMAGE SEARCH
# ===============================================================================================

@app.route('/search')
def search():
    all_trademarks = db.get_all_trademarks() 
    return render_template('search.html', trademarks=all_trademarks)

@app.route('/api/text_search', methods=['POST'])
def api_text_search():
    if request.is_json:
        data         = request.get_json()
        words        = data.get('words', '')
        class_filter = data.get('class_filter', '')
    else:
        words        = request.form.get('words', '')
        class_filter = request.form.get('class_filter', '')

    words = re.sub(r'\s+', '', words)
    print("CLEAN WORDS:", repr(words))

    results = db.search_trademarks(words=words, class_filter=class_filter)
    return jsonify([dict(row) for row in results])

@app.route('/api/image_search', methods=['POST'])
def api_image_search():
    words        = request.form.get('words')
    class_filter = request.form.get('class_filter')
    image_file   = request.files.get('image')

    if not image_file:
        return jsonify({'error': 'No image provided'}), 400

    query_embedding = ml_model.generate_image_embedding(image_file.stream)
    if query_embedding is None:
        return jsonify({'error': 'AI failed to process image'}), 400

    distances, similar_ids = ml_model.search_logo_index(query_embedding, return_distances=True)

    if not similar_ids:
        return jsonify([])

    match_ids = [similar_ids[i] for i, d in enumerate(distances) if d <= 0.10]
    if not match_ids:
        return jsonify([])

    results        = db.search_trademarks(words=words, class_filter=class_filter, id_list=match_ids)
    results_dict   = {row['id']: dict(row) for row in results}
    sorted_results = []
    for rid in match_ids:
        if rid in results_dict:
            sorted_results.append(results_dict[rid])

    return jsonify(sorted_results)

@app.route('/compare')
def compare():
    return render_template('compare.html')

# ==============================================================================
# SIMILARITY HELPERS
# ==============================================================================

def extract_logo_from_bytes(img_bytes, white_thresh=240):
    try:
        img      = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
        arr      = np.array(img)
        mask     = np.any(arr < white_thresh, axis=2)
        col_sums = np.sum(mask, axis=0)
        
        w          = img.width
        start_scan = int(w * 0.15)
        end_scan   = int(w * 0.85)
        
        max_gap_len       = 0
        max_gap_start     = 0
        current_gap_len   = 0
        current_gap_start = 0

        for x in range(start_scan, end_scan):
            if col_sums[x] == 0:
                if current_gap_len == 0:
                    current_gap_start = x
                current_gap_len += 1
            else:
                if current_gap_len > max_gap_len:
                    max_gap_len   = current_gap_len
                    max_gap_start = current_gap_start
                current_gap_len = 0

        if current_gap_len > max_gap_len:
            max_gap_start = current_gap_start

        left_img  = img.crop((0, 0, max_gap_start, img.height)) if max_gap_len > 15 else img
        left_arr  = np.array(left_img)
        left_mask = np.any(left_arr < white_thresh, axis=2)

        if left_mask.any():
            ys, xs     = np.where(left_mask)
            tight_crop = left_img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        else:
            tight_crop = left_img

        buf = io.BytesIO()
        tight_crop.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ AI Failed to Retrieve Logo (Fallback to Original Image): {e}")
        return img_bytes

def normalize(text):
    return re.sub(r'[^A-Z0-9]', '', text.upper())

def phash_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        h1   = imagehash.phash(PILImage.open(io.BytesIO(b1)).convert('RGB'))
        h2   = imagehash.phash(PILImage.open(io.BytesIO(b2)).convert('RGB'))
        dist = (h1 - h2)
        return max(0.0, 1.0 - dist / 64.0)
    except Exception:
        return 0.0

def orb_match_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        a = cv2.imdecode(np.frombuffer(b1, np.uint8), cv2.IMREAD_GRAYSCALE)
        b = cv2.imdecode(np.frombuffer(b2, np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None or b is None: return 0.0

        orb    = cv2.ORB_create(500)
        k1, d1 = orb.detectAndCompute(a, None)
        k2, d2 = orb.detectAndCompute(b, None)
        if d1 is None or d2 is None: return 0.0

        bf      = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good    = 0
        for m_n in matches:
            if len(m_n) < 2: continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good += 1
        denom = max(1, min(len(k1), len(k2)))
        return float(good) / denom
    except Exception:
        return 0.0

def orb_similarity(img_bytes1, img_bytes2):
    try:
        img1   = cv2.imdecode(np.frombuffer(img_bytes1, np.uint8), cv2.IMREAD_GRAYSCALE)
        img2   = cv2.imdecode(np.frombuffer(img_bytes2, np.uint8), cv2.IMREAD_GRAYSCALE)
        orb    = cv2.ORB_create(500)
        k1, d1 = orb.detectAndCompute(img1, None)
        k2, d2 = orb.detectAndCompute(img2, None)
        if d1 is None or d2 is None: return 0.0
        bf      = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good    = 0
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good += 1
        return good / max(len(k1), 1)
    except:
        return 0.0

def edge_similarity(img_bytes1, img_bytes2):
    try:
        img1 = cv2.imdecode(np.frombuffer(img_bytes1, np.uint8), cv2.IMREAD_GRAYSCALE)
        img2 = cv2.imdecode(np.frombuffer(img_bytes2, np.uint8), cv2.IMREAD_GRAYSCALE)
        img1 = cv2.resize(img1, (128, 128))
        img2 = cv2.resize(img2, (128, 128))
        e1   = cv2.Canny(img1, 100, 200)
        e2   = cv2.Canny(img2, 100, 200)
        diff = np.sum(np.abs(e1.astype("float") - e2.astype("float")))
        sim  = 1 - diff / (128 * 128 * 255)
        return max(sim, 0)
    except:
        return 0.0

def seq_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

def jaccard_tokens(a: str, b: str) -> float:
    sa = set((a or "").lower().split())
    sb = set((b or "").lower().split())
    if not sa and not sb: return 0.0
    return len(sa & sb) / len(sa | sb)

# ===============================================================================================
# COMPARISON API
# ===============================================================================================

@app.route('/api/perform_comparison', methods=['POST'])
def perform_comparison():
    file            = request.files.get('file')
    source_category = request.form.get('source_category', 'UPLOAD').upper()
    target          = request.form.get('target', 'MYIPO').upper()
    words_field     = request.form.get('words', '').strip()

    if target == 'CLIENT':
        db_data       = db.get_all_client_embeddings()
        table_name    = "client_trademarks"
        query_columns = """
            id,
            applicant_name as trademark_name,
            file_name as serial_number,
            applicant_name,
            description,
            NULL as class_indices,
            'Client Record' as agent_details,
            logo_data
        """
    else:
        db_data       = db.get_all_embeddings(category=target)
        table_name    = "trademarks"
        query_columns = """
            id, trademark_name, serial_number, applicant_name, description,
            class_indices, agent_details, logo_data
        """

    if not db_data or not db_data['ids']:
        return jsonify({'error': f'Target {target} database is empty'}), 400

    db_logo_vectors = np.vstack(db_data['logo']).astype('float32')
    db_text_vectors = np.vstack(db_data['text']).astype('float32')
    faiss.normalize_L2(db_logo_vectors)
    faiss.normalize_L2(db_text_vectors)

    image_index = faiss.IndexFlatIP(512)
    text_index  = faiss.IndexFlatIP(384)
    image_index.add(db_logo_vectors)
    text_index.add(db_text_vectors)

    query_items = []
    if source_category == 'UPLOAD':
        if not file:
            return jsonify({'error': 'No file provided'}), 400
        file.seek(0)
        file_bytes = file.read()
        filename   = file.filename.lower()

        if filename.endswith('.pdf'):
            results_from_pdf = []
            extractor        = UltraRobustExtractor()
            for update in extractor.extract_all(io.BytesIO(file_bytes), start_page=1):
                if update.get('status') == 'extraction_complete':
                    results_from_pdf = update.get('results', [])
            query_items = results_from_pdf
        else:
            clean_logo_bytes = extract_logo_from_bytes(file_bytes)
            query_items = [{
                'serial_number':  'IMAGE_UPLOAD',
                'trademark_name': words_field,
                'description':    '',
                'logo_data':      clean_logo_bytes if clean_logo_bytes else file_bytes
            }]
    elif source_category == 'CLIENT':
        query_items = db.get_client_query_items()
    else:
        query_items = db.get_query_items_by_category(source_category)

    if not query_items:
        return jsonify({'error': 'No items found in the selected source'}), 400

    all_texts       = []
    all_logo_images = []
    logo_mapping    = []

    for i, q in enumerate(query_items):
        txt = f"{q.get('trademark_name','') or ''} {q.get('description','') or ''}".strip()
        all_texts.append(txt if (txt and txt.lower() != 'n/a') else "empty")
        if q.get('logo_data'):
            try:
                img = PILImage.open(io.BytesIO(q['logo_data'])).convert("RGB")
                all_logo_images.append(img)
                logo_mapping.append(i)
            except:
                pass

    text_embeddings = ml_model.text_model.encode(all_texts, batch_size=32, convert_to_numpy=True)
    faiss.normalize_L2(text_embeddings)
    D_text, I_text = text_index.search(text_embeddings.astype('float32'), 10)

    logo_results = {}
    if all_logo_images:
        logo_embeddings = ml_model.image_model.encode(all_logo_images, batch_size=32, convert_to_numpy=True)
        faiss.normalize_L2(logo_embeddings)
        D_logo, I_logo = image_index.search(logo_embeddings.astype('float32'), 20)
        for i, query_idx in enumerate(logo_mapping):
            logo_results[query_idx] = (D_logo[i], I_logo[i])

    final_results = []
    conn = db.get_db_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    all_potential_ids = set()
    for i, _ in enumerate(query_items):
        for idx in I_text[i]:
            if idx != -1: all_potential_ids.add(db_data['ids'][idx])
        if i in logo_results:
            for idx in logo_results[i][1]:
                if idx != -1: all_potential_ids.add(db_data['ids'][idx])

    master_db_lookup = {}
    if all_potential_ids:
        cur.execute(
            f"SELECT {query_columns} FROM {table_name} WHERE id = ANY(%s)",
            (list(all_potential_ids),)
        )
        master_db_lookup = {row['id']: row for row in cur.fetchall()}

    for i, q in enumerate(query_items):
        match_list = []
        q_name_raw = (
            q.get('trademark_name') or
            q.get('applicant_name') or
            q.get('serial_number') or
            ""
        ).strip()
        q_name = normalize(q_name_raw)

        q_logo    = q.get('logo_data')
        q_has_img = False
        if q_logo:
            nparr = np.frombuffer(q_logo, np.uint8)
            img   = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is not None and np.std(img) > 5:
                q_has_img = True

        t_sim_map = {
            db_data['ids'][idx]: float(D_text[i][rank])
            for rank, idx in enumerate(I_text[i]) if idx != -1
        }
        l_sim_map = {}
        if i in logo_results:
            l_sim_map = {
                db_data['ids'][idx]: float(logo_results[i][0][rank])
                for rank, idx in enumerate(logo_results[i][1]) if idx != -1
            }

        candidate_ids = set(t_sim_map.keys()) | set(l_sim_map.keys())

        for db_id in candidate_ids:
            row = master_db_lookup.get(db_id)
            if not row: continue
            if not q_name and not q_has_img: continue

            db_name = normalize(row['trademark_name'] or "")
            t_ai    = t_sim_map.get(db_id, 0.0)
            l_ai    = l_sim_map.get(db_id, 0.0)

            if q_has_img:
                if t_ai < 0.3 and l_ai < 0.3: continue
            else:
                if t_ai < 0.3: continue

            if not q_name or not db_name:
                literal = 0.0
            elif q_name == db_name:
                literal = 1.0
            elif q_name in db_name or db_name in q_name:
                literal = 0.85
            else:
                literal = 0.0

            fuzzy          = seq_ratio(q_name, db_name) if (q_name and db_name) else 0.0
            text_sim_final = max(literal, t_ai * 0.9, fuzzy * 0.95)

            pixel_sim     = phash_score_bytes(q_logo, row['logo_data']) if (q_has_img and row['logo_data']) else 0.0
            img_sim_final = l_ai * 0.4 if (pixel_sim < 0.25 and l_ai > 0.70) else max(l_ai, pixel_sim)
            if img_sim_final > 0.92:
                img_sim_final = 1.0

            if q_name and q_has_img:
                total, threshold = (text_sim_final * 0.45 + img_sim_final * 0.55), 0.35
            elif q_has_img:
                total, threshold = img_sim_final, 0.45
            elif q_name:
                total, threshold = text_sim_final, 0.35
            else:
                total, threshold = 0.0, 1.0

            if total >= threshold:
                match_list.append({
                    'id':          db_id,
                    'serial':      row['serial_number'],
                    'label':       row['trademark_name'] or row['applicant_name'],
                    'totalSim':    round(total          * 100, 2),
                    'textSim':     round(text_sim_final * 100, 2),
                    'imgSim':      round(img_sim_final  * 100, 2),
                    'description': row['description'],
                    'modalClass':  row['class_indices'],
                    'modalAgent':  row['agent_details']
                })

        # Sort all matches by score
        match_list = sorted(
            match_list,
            key=lambda x: (x['totalSim'], x['textSim'], x['imgSim']),
            reverse=True
        )

        if match_list:
            final_results.append({
                'query_serial': q.get('serial_number') or q_name_raw or f"Item {i+1}",
                'matches':      match_list[:3],   # top 3 for UI display
                'all_matches':  match_list[:20]   # up to {n} for PDF
            })

    cur.close()
    conn.close()
    return jsonify(final_results)

# ===============================================================================================
# DOWNLOAD REPORT AS PDF FORMAT
# ===============================================================================================

@app.route('/api/generate_pdf', methods=['POST'])
def generate_pdf():
    data         = request.get_json()
    trademark_id = data.get('id')
    is_client    = data.get('isClient', False)

    # Use allMatches (full list for PDF) if provided, fall back to topMatches (UI top 3)
    all_matches = data.get("allMatches") or data.get("topMatches", [])

    if is_client:
        logo_bytes = db.get_client_logo(trademark_id)
    else:
        logo_bytes = db.get_logo(trademark_id)

    # Split into two tiers
    high_matches  = [m for m in all_matches if float(m.get('totalSim', 0)) >= 70]
    other_matches = [m for m in all_matches if 30 <= float(m.get('totalSim', 0)) < 70]

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    high_heading = ParagraphStyle(
        'HighHeading',
        parent=styles['Heading2'],
        fontSize=13,
        spaceAfter=8,
        spaceBefore=16,
        textColor=colors.HexColor('#c0392b'),
    )
    other_heading = ParagraphStyle(
        'OtherHeading',
        parent=styles['Heading2'],
        fontSize=13,
        spaceAfter=8,
        spaceBefore=16,
        textColor=colors.HexColor('#2471a3'),
    )

    elements = []

    # Title
    elements.append(Paragraph("Trademark Analysis Report", styles['Title']))
    elements.append(Spacer(1, 12))

    # Query logo
    if logo_bytes:
        img_data   = io.BytesIO(logo_bytes)
        img        = RLImage(img_data, width=150, height=150)
        logo_table = Table([[img]], colWidths=[500])
        logo_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        elements.append(logo_table)

    elements.append(Spacer(1, 20))

    # Query metadata table
    table_data = [
        [Paragraph("<b>Trademark Name:</b>",   styles['Normal']), Paragraph(str(data.get('label', '')),      styles['Normal'])],
        [Paragraph("<b>Serial Number:</b>",    styles['Normal']), Paragraph(str(data.get('serial', '')),     styles['Normal'])],
        [Paragraph("<b>Class:</b>",            styles['Normal']), Paragraph(str(data.get('modalClass', '')), styles['Normal'])],
        [Paragraph("<b>Agent:</b>",            styles['Normal']), Paragraph(str(data.get('modalAgent', '')), styles['Normal'])],
        [Paragraph("<b>Image Similarity:</b>", styles['Normal']), Paragraph(f"{data.get('imgSim')}%",        styles['Normal'])],
        [Paragraph("<b>Text Similarity:</b>",  styles['Normal']), Paragraph(f"{data.get('textSim')}%",       styles['Normal'])],
    ]
    t = Table(table_data, colWidths=[120, 350])
    t.setStyle(TableStyle([
        ('GRID',    (0, 0), (-1, -1), 0.5, colors.grey),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # Description
    elements.append(Paragraph("<b>Description:</b>", styles['Heading3']))
    elements.append(Paragraph(data.get('description', 'N/A'), styles['Normal']))
    elements.append(Spacer(1, 25))

    # Helper: render a single match row
    def render_match_row(match):
        # Try trademarks table first, fall back to client_trademarks
        match_logo = db.get_logo(match["id"]) or db.get_client_logo(match["id"])
        row = []

        if match_logo:
            img_data = io.BytesIO(match_logo)
            img      = RLImage(img_data, width=60, height=60)
            img._restrictSize(60, 60)
            row.append(img)
        else:
            row.append(Paragraph("<i>No Image</i>", styles['Normal']))

        info_text = (
            f"<b>{match.get('label', '')}</b><br/>"
            f"Serial: {match.get('serial', '')}<br/>"
            f"Similarity: {match.get('totalSim', '')}%<br/>"
            f"Image: {match.get('imgSim', '')}% &nbsp;|&nbsp; Text: {match.get('textSim', '')}%"
        )
        row.append(Paragraph(info_text, styles['Normal']))

        match_table = Table([row], colWidths=[80, 390])
        match_table.setStyle(TableStyle([
            ('GRID',    (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN',  (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        return match_table

    def render_rule(hex_color):
        rule = Table([['']], colWidths=[470])
        rule.setStyle(TableStyle([
            ('LINEBELOW',     (0, 0), (-1, -1), 1.5, colors.HexColor(hex_color)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return rule

    # High similarity section (>= 70%)
    elements.append(Paragraph("⚠ High Similarity Matches (70% and above)", high_heading))
    elements.append(render_rule('#c0392b'))
    elements.append(Spacer(1, 6))

    if high_matches:
        for match in high_matches:
            elements.append(render_match_row(match))
            elements.append(Spacer(1, 8))
    else:
        elements.append(Paragraph("No high similarity matches found.", styles['Normal']))

    elements.append(Spacer(1, 20))

    # Other similarity section (30 - 69%)
    elements.append(Paragraph("Other Similar Matches (30% – 69%)", other_heading))
    elements.append(render_rule('#2471a3'))
    elements.append(Spacer(1, 6))

    if other_matches:
        for match in other_matches:
            elements.append(render_match_row(match))
            elements.append(Spacer(1, 8))
    else:
        elements.append(Paragraph("No other similar matches found.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    label_clean = re.sub(r'[\\/*?:"<>|]', '', data.get('label', 'unknown')).strip()
    filename = f"Report_{label_clean}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

# ===============================================================================================
# IMAGE SERVING (LOGOS & LEGAL EVIDENCE)
# ===============================================================================================

@app.route('/logo/<int:trademark_id>')
def get_trademark_logo(trademark_id):
    logo_data = db.get_logo(trademark_id)
    if logo_data:
        return send_file(io.BytesIO(logo_data), mimetype='image/png')
    return "Not found", 404

@app.route('/evidence/<int:trademark_id>')
def get_evidence(trademark_id):
    data = db.get_evidence(trademark_id)
    if data:
        return send_file(io.BytesIO(data), mimetype='image/png')
    return "Not found", 404

if __name__ == '__main__':
    db.init_db()
        # Get host and port from environment, fallback to defaults
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_RUN_PORT", 5000))
    print(f"Starting Flask on {host}:{port}")

    app.run(host=host, port=port, debug=True)
    