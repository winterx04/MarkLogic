import math
import fitz
import io
import sys
import secrets 
import numpy as np
import faiss
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_file, session
from functools import wraps
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from PIL import Image
from flask import abort  

# Import your updated database functions and the Perfect Extractor
import database as db 
from ml_utils import MLModel
from pdf_extractor_backup import extract_all # This must be the stateful extractor we discussed

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
    import traceback

    file = request.files.get('file')
    batch = request.form.get('batch_number')
    year = request.form.get('batch_year')

    if not file or not batch or not year:
        return jsonify({'success': False, 'message': 'Missing File, Batch, or Year'}), 400

    try:
        print(f"📄 Starting extraction from {file.filename}...")  
        raw_data = extract_all(io.BytesIO(file.read()))
        print(f"✅ Extracted {len(raw_data)} trademarks")  


        for tm in raw_data:
            tm['category'] = category
            tm['batch_number'] = batch
            tm['batch_year'] = year

            # 1. Text embedding
            combined_text = f"{tm['trademark_name']} {tm['description']}"
            tm['text_embedding'] = ml_model.generate_text_embedding(combined_text)

            # 2. Safe logo embedding
            if tm.get('logo_data') and isinstance(tm['logo_data'], bytes) and len(tm['logo_data']) > 0:
                tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))
            else:
                tm['logo_embedding'] = None
                tm['logo_data'] = None  # prevent passing None to DB or ML

            # 3. Insert into DB
            db.insert_trademark(tm)

        ml_model.build_logo_index()
        return jsonify({'success': True, 'message': f'Imported {len(raw_data)} records into Batch {batch}/{year}'})

    except Exception as e:
        traceback.print_exc()  # Prints full Python error
        return jsonify({'success': False, 'message': str(e)}), 500



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
    # Support both JSON (headers) and Form Data (fetch)
    if request.is_json:
        data = request.get_json()
        words = data.get('words', '')
        class_filter = data.get('class_filter', '')
    else:
        words = request.form.get('words', '')
        class_filter = request.form.get('class_filter', '')

    results = db.search_trademarks(words=words, class_filter=class_filter)
    
    # This turns the database rows into JSON-ready format
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

@app.route('/api/perform_comparison', methods=['POST'])
def perform_comparison():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file uploaded'}), 400

    # ---------------- CONFIG ----------------
    DEBUG = True
    TEXT_DIM = 384
    IMG_DIM = 512

    target = request.form.get('target', 'MYIPO').upper()
    filename = file.filename.lower()

    if DEBUG:
        print("\n================ COMPARISON START ================")
        print("Target category:", target)
        print("Filename:", filename)

    # =================================================
    # 1. LOAD DATABASE EMBEDDINGS
    # =================================================
    db_data = db.get_all_embeddings(category=target)

    if not db_data['ids']:
        print("❌ No embeddings found for category:", target)
        return jsonify({'error': 'Database is empty for this category'}), 400

    db_logo_vectors = np.vstack(db_data['logo']).astype('float32')
    db_text_vectors = np.vstack(db_data['text']).astype('float32')

    faiss.normalize_L2(db_logo_vectors)
    faiss.normalize_L2(db_text_vectors)

    image_index = faiss.IndexFlatIP(IMG_DIM)
    text_index = faiss.IndexFlatIP(TEXT_DIM)

    image_index.add(db_logo_vectors)
    text_index.add(db_text_vectors)

    if DEBUG:
        print(f"✔ Loaded {len(db_data['ids'])} DB trademarks")

    # =================================================
    # 2. INPUT TYPE (PDF or IMAGE)
    # =================================================
    if filename.endswith('.pdf'):
        query_items = extract_all(io.BytesIO(file.read()))
        input_type = "PDF"
    else:
        query_items = [{
            'serial_number': 'IMAGE_UPLOAD',
            'trademark_name': request.form.get('words', '').strip(),
            'description': '',
            'logo_data': file.read()
        }]
        input_type = "IMAGE"

    if not query_items:
        print("❌ No query items extracted")
        return jsonify([])

    # =================================================
    # 3. SEARCH LOOP
    # =================================================
    final_results = []

    conn = db.get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    for q in query_items:
        print("\n--- QUERY TRADEMARK ---")
        print("Serial:", q.get('serial_number'))
        print("Name:", q.get('trademark_name'))

        # ---------------- TEXT EMBEDDING ----------------
        q_text = f"{q.get('trademark_name', '')} {q.get('description', '')}".strip()
        q_text_emb = ml_model.generate_text_embedding(q_text).reshape(1, -1)
        faiss.normalize_L2(q_text_emb)

        t_sims, t_idxs = text_index.search(q_text_emb, 20)

        # ---------------- IMAGE EMBEDDING ----------------
        l_sims, l_idxs = None, None
        if q.get('logo_data'):
            q_logo_emb = ml_model.generate_image_embedding(io.BytesIO(q['logo_data']))
            if q_logo_emb is not None:
                q_logo_emb = q_logo_emb.reshape(1, -1)
                faiss.normalize_L2(q_logo_emb)
                l_sims, l_idxs = image_index.search(q_logo_emb, 20)

        # =================================================
        # 4. MERGE CANDIDATES
        # =================================================
        candidates = {}

        for i, idx in enumerate(t_idxs[0]):
            if idx == -1:
                continue
            db_id = db_data['ids'][idx]
            candidates[db_id] = {'text': float(t_sims[0][i]), 'image': 0.0}

        if l_idxs is not None:
            for i, idx in enumerate(l_idxs[0]):
                if idx == -1:
                    continue
                db_id = db_data['ids'][idx]
                candidates.setdefault(db_id, {'text': 0.0, 'image': 0.0})
                candidates[db_id]['image'] = float(l_sims[0][i])

        # =================================================
        # 5. SCORE + DEBUG
        # =================================================
        match_list = []
        q_name_upper = q.get('trademark_name', '').upper()

        for db_id, sims in candidates.items():
            # UPDATED: Added description, class_indices, and agent_details to the SELECT
            cur.execute("""
                SELECT trademark_name, serial_number, applicant_name, 
                       description, class_indices, agent_details
                FROM trademarks WHERE id = %s
            """, (db_id,))
            row = cur.fetchone()
            if not row:
                continue

            db_name_upper = (row['trademark_name'] or "").upper()

            # Literal boost
            literal = 0.0
            if q_name_upper and db_name_upper:
                if q_name_upper == db_name_upper:
                    literal = 1.0
                elif q_name_upper in db_name_upper:
                    literal = 0.8

            # ================= SCORE FORMULA =================
            if input_type == "IMAGE":
                total = (sims['image'] * 0.8) + (sims['text'] * 0.2)
            else:
                total = (literal * 0.4) + (sims['text'] * 0.4) + (sims['image'] * 0.2)

            if DEBUG:
                print(f"""
DB ID: {db_id}
Name: {row['trademark_name']}
TextSim: {sims['text']:.3f}
ImgSim: {sims['image']:.3f}
Literal: {literal}
FINAL SCORE: {total:.3f}
                """)

            if total >= 0.40:
                match_list.append({
                    'id': db_id,
                    'serial': row['serial_number'],
                    'label': row['applicant_name'],
                    'totalSim': round(total * 100, 2),
                    'textSim': round(max(literal, sims['text']) * 100, 2),
                    'imgSim': round(sims['image'] * 100, 2),
                    'description': row['description'],
                    'modalClass': row['class_indices'],
                    'modalAgent': row['agent_details']
                })

        match_list = sorted(match_list, key=lambda x: x['totalSim'], reverse=True)[:5]

        if input_type == "PDF":
            final_results.append({
                'query_serial': q.get('serial_number'),
                'matches': match_list
            })
        else:
            final_results = match_list

    cur.close()
    conn.close()

    print("================ COMPARISON END =================\n")
    return jsonify(final_results)



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