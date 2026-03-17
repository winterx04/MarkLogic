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

app = Flask(__name__)
app.secret_key = 'a_secure_random_secret_key'

# --- Law Firm Configuration ---
app.config['EXACT_MATCH_THRESHOLD'] = 0.05 

# --- INITIALIZE THE EMAIL (Your original config) ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'xxin589@gmail.com'  
app.config['MAIL_PASSWORD'] = 'jjxh vzax yjyj njsu' 
app.config['MAIL_DEFAULT_SENDER'] = ('MarkLogic Admin', 'xxin589@gmail.com')

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

# @app.route('/signin', methods=['GET', 'POST'])
# def signin():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         password = request.form.get('password')
#         user = db.get_user_by_email(email)

#     if user and check_password_hash(user['password_hash'], password):
#             session['logged_in'] = True
#             session['user_id'] = user['id']
#             session['username'] = user['username']
#             session['role'] = user['role']
            
#             if user['is_temporary_password']:
#                 session['force_password_change'] = True
#                 flash('Please create a new password to secure your account.', 'info')
#                 return redirect(url_for('change_password'))

#             flash(f'Welcome back, {user["username"]}!', 'success')
#             return redirect(url_for('admin_page') if user['role'].lower() == 'admin' else url_for('menu'))
#     else:
#             flash('Invalid email or password.', 'danger')
#     return render_template('signin.html')
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
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
    # Only allow initial admin registration if no users exist (Optional check)
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
# USER MANAGEMENT API (ALL ORIGINAL 8 FUNCTIONS RESTORED)
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
    data = request.get_json()
    username, email, role = data.get('name'), data.get('email'), data.get('role')

    if not all([username, email, role]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    try:
        temp_password = secrets.token_urlsafe(10)
        password_hash = generate_password_hash(temp_password)
        db.add_user(username, email, password_hash) 
        new_user = db.get_user_by_email(email)
        db.update_user_role(new_user['id'], role)

        msg = Message('Your MarkLogic Account has been Created', recipients=[email])
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
    name = data.get('name')
    email = data.get('email')

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
    data = request.get_json()
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
            
            # --- REDIRECTION LOGIC ---
            user_role = session.get('role', '').lower()
            if user_role in ['admin', 'manager']:
                return redirect(url_for('admin_page'))
            else:
                return redirect(url_for('menu'))
                
        flash('Passwords do not match.', 'danger')
    return render_template('change_password.html')

# ===============================================================================================
# DATASET & JOURNAL UPLOAD (NEW PERFECT EXTRACTOR INTEGRATION)
# ===============================================================================================

@app.route('/dataset')
def dataset():
    return render_template('dataset.html')

@app.route('/client-dataset')
def client_dataset():
    return render_template('client-dataset.html')


@app.route('/upload-journal/<category>', methods=['POST'])
@admin_required 
def upload_journal(category):
    file = request.files.get('file')
    batch = request.form.get('batch_number')
    year = request.form.get('batch_year')

    if not file or not batch or not year:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400

    file_bytes = file.read()

    def generate():
        try:
            raw_data = []
            extractor = UltraRobustExtractor() 

            # --- PHASE 1: PDF EXTRACTION ---
            # Using update.get() is safer
            for update in extractor.extract_all(io.BytesIO(file_bytes)):
                status = update.get('status')
                if status == 'extracting':
                    yield json.dumps(update) + "\n"
                elif status == 'extraction_complete':
                    raw_data = update.get('results', [])

            # --- PHASE 2: DATABASE & AI PROCESSING ---
            total_records = len(raw_data)
            if total_records == 0:
                yield json.dumps({"status": "error", "message": "No trademarks found in PDF."}) + "\n"
                return

            inserted = 0
            for tm in raw_data:
                # Normalize keys
                if tm.get("block_snapshot") and not tm.get("evidence_snapshot"):
                    tm["evidence_snapshot"] = tm["block_snapshot"]

                tm.update({'category': category, 'batch_number': batch, 'batch_year': year})

                # 1) Text embedding
                combined_text = f"{tm.get('trademark_name','')} {tm.get('description','')}".strip()
                if combined_text:
                    tm['text_embedding'] = ml_model.generate_text_embedding(combined_text)

                # 2) Logo embedding
                if tm.get('logo_data'):
                    tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))

                # 3) Insert into DB
                db.insert_trademark(tm)
                inserted += 1

                # 4) YIELD PROGRESS (Phase 2)
                db_percent = int((inserted / total_records) * 100)
                yield json.dumps({
                    "status": "inserting", 
                    "percentage": db_percent, 
                    "current": inserted, 
                    "total": total_records
                }) + "\n"

            # Rebuild index
            ml_model.build_logo_index()
            
            # Final Success Message
            yield json.dumps({
                "status": "complete", 
                "success": True, 
                "message": f"Successfully imported {inserted} records."
            }) + "\n"

        except Exception as e:
            traceback.print_exc()
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

# @app.route('/upload-journal/<category>', methods=['POST'])
# @admin_required
# def upload_journal(category):
#     file = request.files.get('file')
#     batch = request.form.get('batch_number')
#     year = request.form.get('batch_year')

#     if not file or not batch or not year:
#         return jsonify({'success': False, 'message': 'Missing File, Batch, or Year'}), 400


#     def looks_like_goods(s: str) -> bool:
#         s_up = (s or "").upper()
#         bad_kw = ["DETERGENT", "PREPARATIONS", "SOAP", "LAUNDRY", "DISH-WASHING", "BLEACHING", "SUBSTANCES"]
#         return any(k in s_up for k in bad_kw)

#     try:
#         print(f"📄 Starting extraction from {file.filename}...")
#         raw_data = extract_all(io.BytesIO(file.read()))
#         print(f"✅ Extracted {len(raw_data)} trademarks")

#         inserted = 0
#         warnings = []

#         for tm in raw_data:
#             # -------- normalize keys --------
#             # extractor uses block_snapshot; DB expects evidence_snapshot
#             if tm.get("block_snapshot") and not tm.get("evidence_snapshot"):
#                 tm["evidence_snapshot"] = tm["block_snapshot"]

#             tm['category'] = category
#             tm['batch_number'] = batch
#             tm['batch_year'] = year

#             # -------- sanity checks (optional but recommended) --------
#             # If applicant_name looks like goods => parsing likely wrong
#             if looks_like_goods(tm.get("applicant_name", "")):
#                 warnings.append({
#                     "serial_number": tm.get("serial_number"),
#                     "issue": "applicant_name looks like goods/description; skipped to avoid poisoning DB",
#                     "applicant_name": tm.get("applicant_name", "")[:120],
#                 })
#                 continue

#             # 1) Text embedding
#             combined_text = f"{tm.get('trademark_name','')} {tm.get('description','')}".strip()
#             tm['text_embedding'] = ml_model.generate_text_embedding(combined_text) if combined_text else None

#             # 2) Safe logo embedding
#             if tm.get('logo_data') and isinstance(tm['logo_data'], (bytes, bytearray)) and len(tm['logo_data']) > 0:
#                 tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))
#             else:
#                 tm['logo_embedding'] = None
#                 tm['logo_data'] = None

#             # 3) Insert into DB
#             db.insert_trademark(tm)
#             inserted += 1

#         ml_model.build_logo_index()

#         msg = f'Imported {inserted} records into Batch {batch}/{year}'
#         if warnings:
#             msg += f' (Skipped {len(warnings)} suspicious records)'

#         return jsonify({'success': True, 'message': msg, 'warnings': warnings})

#     except Exception as e:
#         traceback.print_exc()
#         return jsonify({'success': False, 'message': str(e)}), 500


# GET /api/trademarks  -> list or search (query params: batch_number, batch_year, q, class)
@app.route('/api/trademarks', methods=['GET'])
def api_trademarks():
    # allow only logged in users to fetch 
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    batch = request.args.get('batch_number')
    year = request.args.get('batch_year')
    q = request.args.get('q')
    class_filter = request.args.get('class')

    # If search params exist use search_trademarks, else return all
    if q or class_filter:
        rows = db.search_trademarks(words=q, class_filter=class_filter)
    else:
        rows = db.get_all_trademarks()

    results = []
    for row in rows:
        r = dict(row)  # DictCursor -> dict
        # Build a friendly display name
        if r.get('file_name'):
            display_name = r.get('file_name')
        elif r.get('batch_number') and r.get('batch_year'):
            display_name = f"{r.get('batch_number')}/{r.get('batch_year')}.pdf"
        else:
            display_name = r.get('serial_number') or f"id-{r.get('id')}"

        results.append({
            'id': r.get('id'),
            'serial_number': r.get('serial_number'),
            'display_name': display_name,
            'trademark_name': r.get('trademark_name'),
            'class_indices': r.get('class_indices'),
            'applicant_name': r.get('applicant_name'),
            'category': r.get('category'),
            'is_split': r.get('is_split'),
            'has_logo': bool(r.get('has_logo'))
        })

    return jsonify({'success': True, 'trademarks': results})

@app.route('/api/trademarks', methods=['DELETE'])
@admin_required
def api_delete_trademarks():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({'success': False, 'message': 'Provide ids list in JSON body.'}), 400

    deleted = 0
    errors = []
    for tid in ids:
        try:
            db.delete_trademark_by_id(tid)
            deleted += 1
        except Exception as e:
            errors.append({'id': tid, 'error': str(e)})

    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})

# ===============================================================================================
# SEARCH & COMPARISON API (FIXED MATH & DEBUGGING)
# ===============================================================================================


@app.route('/search')
def search():
    all_trademarks = db.get_all_trademarks() 
    return render_template('search.html', trademarks=all_trademarks)

@app.route('/api/text_search', methods=['POST'])
def api_text_search():
    if request.is_json:
        data = request.get_json()
        words = data.get('words', '')
        class_filter = data.get('class_filter', '')
    else:
        words = request.form.get('words', '')
        class_filter = request.form.get('class_filter', '')

    # HARD CLEAN
    words = re.sub(r'\s+', '', words)

    print("CLEAN WORDS:", repr(words))

    results = db.search_trademarks(words=words, class_filter=class_filter)
    return jsonify([dict(row) for row in results])


@app.route('/api/image_search', methods=['POST'])
def api_image_search():
    words = request.form.get('words')
    class_filter = request.form.get('class_filter')
    image_file = request.files.get('image')

    if not image_file:
        return jsonify({'error': 'No image provided'}), 400

    query_embedding = ml_model.generate_image_embedding(image_file.stream)
    if query_embedding is None:
        return jsonify({'error': 'AI failed to process image'}), 400

    distances, similar_ids = ml_model.search_logo_index(query_embedding, return_distances=True)

    if not similar_ids:
        return jsonify([])

    # Filter by threshold
    match_ids = [similar_ids[i] for i, d in enumerate(distances) if d <= 0.10]
    
    if not match_ids:
        return jsonify([])

    # Fetch data
    results = db.search_trademarks(words=words, class_filter=class_filter, id_list=match_ids)
    
    # Map results and ensure key names match frontend
    results_dict = {row['id']: dict(row) for row in results}
    sorted_results = []
    for rid in match_ids:
        if rid in results_dict:
            sorted_results.append(results_dict[rid])

    return jsonify(sorted_results)

@app.route('/compare')
def compare():
    return render_template('compare.html')

# Test Starts Here 3/3/2026 
#
#
#
#
#
# ==========================================
def extract_logo_from_bytes(img_bytes, white_thresh=240):
    try:
        img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
        arr = np.array(img)
        mask = np.any(arr < white_thresh, axis=2)
        col_sums = np.sum(mask, axis=0)
        
        w = img.width
        start_scan = int(w * 0.15)
        end_scan = int(w * 0.85)
        
        max_gap_len = 0
        max_gap_start = 0
        current_gap_len = 0
        current_gap_start = 0

        for x in range(start_scan, end_scan):
            if col_sums[x] == 0:
                if current_gap_len == 0: current_gap_start = x
                current_gap_len += 1
            else:
                if current_gap_len > max_gap_len:
                    max_gap_len = current_gap_len
                    max_gap_start = current_gap_start
                current_gap_len = 0

        if current_gap_len > max_gap_len:
            max_gap_start = current_gap_start

        if max_gap_len > 15:
            left_img = img.crop((0, 0, max_gap_start, img.height))
        else:
            left_img = img

        # (Tight Crop)
        left_arr = np.array(left_img)
        left_mask = np.any(left_arr < white_thresh, axis=2)
        if left_mask.any():
            ys, xs = np.where(left_mask)
            tight_crop = left_img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        else:
            tight_crop = left_img

        buf = io.BytesIO()
        tight_crop.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ AI Failed to Retrieve Logo (Fallback to Original Image): {e}")
        return img_bytes

# Test for improving similarity accuracy starts here ---------------- 14/3/2026
#
#
#
def phash_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        h1 = imagehash.phash(PILImage.open(io.BytesIO(b1)).convert('RGB'))
        h2 = imagehash.phash(PILImage.open(io.BytesIO(b2)).convert('RGB'))
        dist = (h1 - h2)
        # max bits 64 for phash -> normalize
        return max(0.0, 1.0 - dist / 64.0)
    except Exception:
        return 0.0

def orb_match_score_bytes(b1: bytes, b2: bytes) -> float:
    try:
        a = cv2.imdecode(np.frombuffer(b1, np.uint8), cv2.IMREAD_GRAYSCALE)
        b = cv2.imdecode(np.frombuffer(b2, np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None or b is None: return 0.0

        orb = cv2.ORB_create(500)
        k1, d1 = orb.detectAndCompute(a, None)
        k2, d2 = orb.detectAndCompute(b, None)
        if d1 is None or d2 is None: return 0.0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good = 0
        for m_n in matches:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good += 1
        # normalize by minimum keypoints to avoid inflation
        denom = max(1, min(len(k1), len(k2)))
        return float(good) / denom
    except Exception:
        return 0.0

def orb_similarity(img_bytes1, img_bytes2):
    try:
        img1 = cv2.imdecode(np.frombuffer(img_bytes1, np.uint8), cv2.IMREAD_GRAYSCALE)
        img2 = cv2.imdecode(np.frombuffer(img_bytes2, np.uint8), cv2.IMREAD_GRAYSCALE)

        orb = cv2.ORB_create(500)

        k1, d1 = orb.detectAndCompute(img1, None)
        k2, d2 = orb.detectAndCompute(img2, None)

        if d1 is None or d2 is None:
            return 0.0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)

        good = 0
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good += 1

        return good / max(len(k1), 1)

    except:
        return 0.0

# edge filter
def edge_similarity(img_bytes1, img_bytes2):
    try:
        img1 = cv2.imdecode(np.frombuffer(img_bytes1, np.uint8), cv2.IMREAD_GRAYSCALE)
        img2 = cv2.imdecode(np.frombuffer(img_bytes2, np.uint8), cv2.IMREAD_GRAYSCALE)

        img1 = cv2.resize(img1, (128,128))
        img2 = cv2.resize(img2, (128,128))

        e1 = cv2.Canny(img1, 100, 200)
        e2 = cv2.Canny(img2, 100, 200)

        diff = np.sum(np.abs(e1.astype("float") - e2.astype("float")))
        sim = 1 - diff / (128*128*255)

        return max(sim,0)

    except:
        return 0.0
    
# Name/text similarity helpers (0..1)
def seq_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

def jaccard_tokens(a: str, b: str) -> float:
    sa = set((a or "").lower().split())
    sb = set((b or "").lower().split())
    if not sa and not sb: return 0.0
    return len(sa & sb) / len(sa | sb)
#
#
#
#
# Test for improving similarity accuracy ends here ---------------- 14/3/2026

@app.route('/api/perform_comparison', methods=['POST'])
def perform_comparison():
    file = request.files.get('file')
    source_category = request.form.get('source_category', 'UPLOAD').upper()
    target = request.form.get('target', 'MYIPO').upper()

    # 1. LOAD TARGET DATA (FAISS INDEX)
    db_data = db.get_all_embeddings(category=target)
    if not db_data['ids']:
        return jsonify({'error': 'Target database empty'}), 400

    db_logo_vectors = np.vstack(db_data['logo']).astype('float32')
    db_text_vectors = np.vstack(db_data['text']).astype('float32')
    faiss.normalize_L2(db_logo_vectors)
    faiss.normalize_L2(db_text_vectors)

    image_index = faiss.IndexFlatIP(512)
    text_index = faiss.IndexFlatIP(384)
    image_index.add(db_logo_vectors)
    text_index.add(db_text_vectors)

    # 2. EXTRACT QUERY ITEMS (LEFT SIDE)
    query_items = []
    if source_category == 'UPLOAD':
        if not file: return jsonify({'error': 'No file'}), 400
        
        file.seek(0)
        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({'error': 'Empty file received'}), 400

        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            results_from_pdf = []
            # Exhaust generator to get results
            for update in extract_all(io.BytesIO(file_bytes)):
                if update.get('status') == 'extraction_complete':
                    results_from_pdf = update.get('results', [])
            query_items = results_from_pdf 
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            clean_logo_bytes = extract_logo_from_bytes(file_bytes)
            query_items = [{
                'serial_number': 'IMAGE_UPLOAD',
                'trademark_name': request.form.get('words', '').strip(),
                'description': '',
                'logo_data': clean_logo_bytes
            }]
        else:
            return jsonify({'error': 'Unsupported file format'}), 400
    else:
        query_items = db.get_query_items_by_category(source_category)

    if not query_items:
        return jsonify([])

    # 3. BATCH AI INFERENCE 
    all_texts = []
    all_logo_images = []
    logo_mapping = [] 

    for i, q in enumerate(query_items):
        txt = f"{q.get('trademark_name','') or ''} {q.get('description','') or ''}".strip()
        all_texts.append(txt if (txt and txt.lower() != 'n/a') else "empty")
        
        if q.get('logo_data'):
            try:
                img = PILImage.open(io.BytesIO(q['logo_data'])).convert("RGB")
                all_logo_images.append(img)
                logo_mapping.append(i)
            except: pass

    # Run AI Text Batch
    text_embeddings = ml_model.text_model.encode(all_texts, batch_size=32, convert_to_numpy=True)
    faiss.normalize_L2(text_embeddings)
    D_text, I_text = text_index.search(text_embeddings.astype('float32'), 25)

    # Run AI Logo Batch
    logo_results = {}
    if all_logo_images:
        logo_embeddings = ml_model.image_model.encode(all_logo_images, batch_size=32, convert_to_numpy=True)
        faiss.normalize_L2(logo_embeddings)
        D_logo, I_logo = image_index.search(logo_embeddings.astype('float32'), 50)
        for i, query_idx in enumerate(logo_mapping):
            logo_results[query_idx] = (D_logo[i], I_logo[i])

# ===============================================================================================
# 4. ACCURATE SCORING REVAMP (FINAL VERSION)
# ===============================================================================================
    final_results = []
    conn = db.get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    all_potential_ids = set()
    for i, q in enumerate(query_items):
        for idx in I_text[i]:
            if idx != -1: all_potential_ids.add(db_data['ids'][idx])
        if i in logo_results:
            for idx in logo_results[i][1]:
                if idx != -1: all_potential_ids.add(db_data['ids'][idx])

    cur.execute("""
        SELECT id, trademark_name, serial_number, applicant_name, description, 
               class_indices, agent_details, logo_data
        FROM trademarks WHERE id = ANY(%s)
    """, (list(all_potential_ids),))
    master_db_lookup = {row['id']: row for row in cur.fetchall()}

    for i, q in enumerate(query_items):
        match_list = []
        q_name_raw = (q.get('trademark_name') or "").strip()
        q_name = q_name_raw.upper() if (len(q_name_raw) > 1 and q_name_raw.lower() != "n/a") else ""
        
        # Check if query has a valid logo
        q_logo = q.get('logo_data')
        q_has_img = False
        if q_logo:
            nparr = np.frombuffer(q_logo, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is not None and np.std(img) > 5: q_has_img = True

        # AI Result Maps
        t_sim_map = {db_data['ids'][idx]: float(D_text[i][rank]) for rank, idx in enumerate(I_text[i]) if idx != -1}
        l_sim_map = {}
        if i in logo_results:
            l_sim_map = {db_data['ids'][idx]: float(logo_results[i][0][rank]) for rank, idx in enumerate(logo_results[i][1]) if idx != -1}

        candidate_ids = set(t_sim_map.keys()) | set(l_sim_map.keys())

        for db_id in candidate_ids:
            if q.get('id') == db_id: continue # Skip self
            row = master_db_lookup.get(db_id)
            if not row: continue

            # --- TEXT SCORE ---
            db_name = (row['trademark_name'] or "").strip().upper()
            t_ai = t_sim_map.get(db_id, 0.0)
            literal = 1.0 if (q_name and q_name == db_name) else (0.8 if (q_name and q_name in db_name) else 0.0)
            fuzzy = seq_ratio(q_name, db_name) if (q_name and db_name) else 0.0
            
            text_sim_final = max(literal, t_ai, fuzzy)

            # --- IMAGE SCORE (The Accuracy Fix) ---
            l_ai = l_sim_map.get(db_id, 0.0) if q_has_img else 0.0
            
            # Double check with PHash (Structural check)
            pixel_sim = 0.0
            if q_has_img and row['logo_data']:
                pixel_sim = phash_score_bytes(q_logo, row['logo_data'])
            
            # Combine AI and Pixels:
            # If AI is high but pixels are low, it's a false positive background match.
            if pixel_sim < 0.25 and l_ai > 0.70:
                img_sim_final = l_ai * 0.4 # Penalize background noise
            else:
                img_sim_final = max(l_ai, pixel_sim)
            
            # Boost 92%+ matches to 100%
            if img_sim_final > 0.92: img_sim_final = 1.0

            # --- TOTAL ---
            if q_name and q_has_img:
                total = (text_sim_final * 0.45 + img_sim_final * 0.55)
                threshold = 0.35
            elif q_has_img:
                total = img_sim_final
                threshold = 0.45
            elif q_name:
                total = text_sim_final
                threshold = 0.35
            else:
                total, threshold = 0.0, 1.0

            if total >= threshold:
                match_list.append({
                    'id': db_id,
                    'serial': row['serial_number'],
                    'label': row['trademark_name'] or row['applicant_name'],
                    'totalSim': round(total * 100, 2),
                    'textSim': round(text_sim_final * 100, 2),
                    'imgSim': round(img_sim_final * 100, 2),
                    'description': row['description'],
                    'modalClass': row['class_indices'],
                    'modalAgent': row['agent_details']
                })

        match_list = sorted(match_list, key=lambda x: x['totalSim'], reverse=True)[:5]
        if match_list:
            final_results.append({
                'query_serial': q.get('serial_number') or q_name_raw or f"Item {i+1}",
                'matches': match_list
            })

    cur.close()
    conn.close()
    return jsonify(final_results)
# ===============================================================================================
# DOWNLOAD REPORT AS PDF FORMAT
# ===============================================================================================
@app.route('/api/generate_pdf', methods=['POST'])
def generate_pdf():
    data = request.get_json()
    trademark_id = data.get('id')
    top_matches = data.get("topMatches", [])
    
    # Fetch original logo from DB
    logo_bytes = db.get_logo(trademark_id)
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # 1. Header
    elements.append(Paragraph(f"Trademark Analysis Report", styles['Title']))
    elements.append(Spacer(1, 12))

    # 2. Add Logo Image
    if logo_bytes:
        img_data = io.BytesIO(logo_bytes)
        img = RLImage(img_data, width=150, height=150)
        logo_table = Table([[img]], colWidths=[500])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER')
        ]))

        elements.append(logo_table)
    
    elements.append(Spacer(1, 20))

    # 3. Main Info Table
    table_data = [
        [Paragraph("<b>Trademark Name:</b>", styles['Normal']), Paragraph(str(data.get('label', '')), styles['Normal'])],
        [Paragraph("<b>Serial Number:</b>", styles['Normal']), Paragraph(str(data.get('serial', '')), styles['Normal'])],
        [Paragraph("<b>Class:</b>", styles['Normal']), Paragraph(str(data.get('modalClass', '')), styles['Normal'])],
        [Paragraph("<b>Agent:</b>", styles['Normal']), Paragraph(str(data.get('modalAgent', '')), styles['Normal'])],
        [Paragraph("<b>Image Similarity:</b>", styles['Normal']), Paragraph(f"{data.get('imgSim')}%", styles['Normal'])],
        [Paragraph("<b>Text Similarity:</b>", styles['Normal']), Paragraph(f"{data.get('textSim')}%", styles['Normal'])],
    ]
    
    t = Table(table_data, colWidths=[120, 350])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # 4. Description
    elements.append(Paragraph("<b>Description:</b>", styles['Heading3']))
    elements.append(Paragraph(data.get('description', 'N/A'), styles['Normal']))

    # 5 . Top Matches
    elements.append(Spacer(1, 25))
    elements.append(Paragraph("Top 3 Similar Trademarks", styles['Heading2']))
    elements.append(Spacer(1, 10))

    for match in top_matches:
        logo_bytes = db.get_logo(match["id"])

        row = []

        # logo
        if logo_bytes:
            img_data = io.BytesIO(logo_bytes)
            img = RLImage(img_data, width=60, height=60)
            img._restrictSize(60, 60)
            row.append(img)
        else:
            row.append("No Image")

        # info
        info = f"""
        <b>{match.get('label','')}</b><br/>
        Serial: {match.get('serial','')}<br/>
        Similarity: {match.get('totalSim','')}%
        """

        row.append(Paragraph(info, styles['Normal']))

        table = Table([row], colWidths=[80, 390])
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('PADDING',(0,0),(-1,-1),6)
        ]))

        elements.append(table)
        elements.append(Spacer(1,10))

    # Build and Return
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Report_{data.get('serial')}.pdf"
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
    app.run(debug=True)