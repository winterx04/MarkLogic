import math
import fitz
import io
import sys
import secrets 
import numpy as np
import faiss
from flask import Flask, json, jsonify, render_template, request, redirect, url_for, flash, send_file, session, Response
from functools import wraps
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from PIL import Image
from flask import abort  
import traceback
import re
import database as db 
from ml_utils import MLModel
from pdf_extractor import UltraRobustExtractor, extract_all 
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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
@admin_required  # Keep your decorator
def upload_journal(category):
    file = request.files.get('file')
    batch = request.form.get('batch_number')
    year = request.form.get('batch_year')

    if not file or not batch or not year:
        return jsonify({'success': False, 'message': 'Missing File, Batch, or Year'}), 400

    # Read the file bytes once into memory so we can use it in the generator
    file_bytes = file.read()

    def generate():
        try:
            raw_data = []
            extractor = UltraRobustExtractor() # Instantiate your class

            # --- PHASE 1: PDF EXTRACTION ---
            for update in extractor.extract_all(io.BytesIO(file_bytes)):
                if update['status'] == 'extracting':
                    # Send progress string to browser
                    yield json.dumps(update) + "\n"
                else:
                    # This is the 'extraction_complete' status with results
                    raw_data = update['results']

            # --- PHASE 2: DATABASE & ML PROCESSING ---
            total_records = len(raw_data)
            inserted = 0

            for tm in raw_data:
                # Normalization
                if tm.get("block_snapshot") and not tm.get("evidence_snapshot"):
                    tm["evidence_snapshot"] = tm["block_snapshot"]

                tm.update({'category': category, 'batch_number': batch, 'batch_year': year})

                # 1) Text embedding
                combined_text = f"{tm.get('trademark_name','')} {tm.get('description','')}".strip()
                tm['text_embedding'] = ml_model.generate_text_embedding(combined_text) if combined_text else None

                # 2) Logo embedding
                if tm.get('logo_data'):
                    tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))

                # 3) Insert into DB
                db.insert_trademark(tm)
                inserted += 1

                # Send DB Progress
                db_percent = int((inserted / total_records) * 100)
                yield json.dumps({
                    "status": "inserting", 
                    "percentage": db_percent, 
                    "current": inserted, 
                    "total": total_records
                }) + "\n"

            ml_model.build_logo_index()
            
            # Final Success Message
            yield json.dumps({
                "status": "complete", 
                "success": True, 
                "message": f"Imported {inserted} records into Batch {batch}/{year}"
            }) + "\n"

        except Exception as e:
            traceback.print_exc()
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    # We use 'application/x-ndjson' to signal Newline Delimited JSON
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
# 辅助函数：智能读取并只截取左侧 Logo
# 放在路由函数上方
# ==========================================
def extract_logo_from_bytes(img_bytes, white_thresh=240):
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
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

        # 智能判定：如果找到了明显的垂直空白区(>15像素宽)，说明是带描述的截图，切除右侧！
        # 如果没有明显缝隙，说明用户上传的本身就是一张纯 Logo，保持原样。
        if max_gap_len > 15:
            left_img = img.crop((0, 0, max_gap_start, img.height))
        else:
            left_img = img

        # 紧密贴边裁剪 (Tight Crop)
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
        print(f"⚠️ 智能提取 Logo 失败 (Fallback 到原图): {e}")
        return img_bytes


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
            print("❌ Error：Accepted File have 0 bytes！")
            return jsonify({'error': 'Empty file received'}), 400

        filename = file.filename.lower()
        print(f"📥 收到上传文件: {filename}, 大小: {len(file_bytes)} bytes")
        
        if filename.endswith('.pdf'):
            query_items = extract_all(io.BytesIO(file_bytes))
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            # 自动切掉右侧文字只留 Logo
            clean_logo_bytes = extract_logo_from_bytes(file_bytes)
            query_items = [{
                'serial_number': 'IMAGE_UPLOAD',
                'trademark_name': request.form.get('words', '').strip(),
                'description': '',
                'logo_data': clean_logo_bytes
            }]
        else:
            print("❌ Error: Unsupported Format")
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
        all_texts.append(txt if txt else "n/a")
        
        # ⚠️ 修复点 3：移除 pass，把真实的报错打印出来！
        if q.get('logo_data'):
            try:
                img = Image.open(io.BytesIO(q['logo_data'])).convert("RGB")
                all_logo_images.append(img)
                logo_mapping.append(i)
            except Exception as e:
                print(f"❌ Error processing image data (Index {i}): {e}")

    # Run Text Batch
    print(f"--- Batch processing {len(all_texts)} texts ---")
    text_embeddings = ml_model.text_model.encode(all_texts, batch_size=32, convert_to_numpy=True)
    faiss.normalize_L2(text_embeddings)
    D_text, I_text = text_index.search(text_embeddings.astype('float32'), 20)

    # Run Logo Batch
    logo_results = {}
    if all_logo_images:
        print(f"--- Batch processing {len(all_logo_images)} logos ---")
        logo_embeddings = ml_model.image_model.encode(all_logo_images, batch_size=32, convert_to_numpy=True)
        faiss.normalize_L2(logo_embeddings)
        D_logo, I_logo = image_index.search(logo_embeddings.astype('float32'), 20)
        
        for i, query_idx in enumerate(logo_mapping):
            logo_results[query_idx] = (D_logo[i], I_logo[i])
    else:
        print("⚠️ Warning: No logos successfully loaded into the AI model!")

    # 4. SCORING & FINAL FORMATTING
    final_results = []
    conn = db.get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    for i, q in enumerate(query_items):
        candidate_ids = set()
        for idx in I_text[i]:
            if idx != -1: candidate_ids.add(db_data['ids'][idx])
        if i in logo_results:
            for idx in logo_results[i][1]:
                if idx != -1: candidate_ids.add(db_data['ids'][idx])

        if not candidate_ids: continue

        cur.execute("""
            SELECT id, trademark_name, serial_number, applicant_name, description, class_indices, agent_details
            FROM trademarks WHERE id = ANY(%s)
        """, (list(candidate_ids),))
        db_rows = {row['id']: row for row in cur.fetchall()}

        match_list = []
        q_name = (q.get('trademark_name') or "").strip().upper()
        
        has_text = bool(q_name or q.get('description', '').strip())
        has_image = i in logo_results

        for db_id in candidate_ids:
            row = db_rows.get(db_id)
            if not row: continue

            t_sim = 0.0
            t_row_ids = [db_data['ids'][x] for x in I_text[i]]
            if db_id in t_row_ids: t_sim = float(D_text[i][t_row_ids.index(db_id)])

            l_sim = 0.0
            if has_image:
                l_row_ids = [db_data['ids'][x] for x in logo_results[i][1]]
                if db_id in l_row_ids: l_sim = float(logo_results[i][0][l_row_ids.index(db_id)])

            db_name = (row['trademark_name'] or "").upper()
            literal = 1.0 if q_name and q_name == db_name else (0.7 if q_name and q_name in db_name else 0.0)

            # 动态权重分配机制
            if has_text and has_image:
                total = (literal * 0.4) + (t_sim * 0.4) + (l_sim * 0.2)
                threshold = 0.38
            elif has_image and not has_text:
                total = l_sim  
                threshold = 0.50 
            elif has_text and not has_image:
                total = (literal * 0.5) + (t_sim * 0.5)
                threshold = 0.38
            else:
                total, threshold = 0.0, 1.0

            if total >= threshold:
                match_list.append({
                    'id': db_id,
                    'serial': row['serial_number'],
                    'label': row['applicant_name'],
                    'totalSim': round(total * 100, 2),
                    'textSim': round(max(literal, t_sim) * 100, 2),
                    'imgSim': round(l_sim * 100, 2),
                    'description': row['description'],
                    'modalClass': row['class_indices'],
                    'modalAgent': row['agent_details']
                })

        match_list = sorted(match_list, key=lambda x: x['totalSim'], reverse=True)[:5]
        if match_list:
            final_results.append({
                'query_serial': q.get('serial_number') or q.get('trademark_name') or 'IMAGE_UPLOAD',
                'matches': match_list
            })

    cur.close()
    conn.close()
    return jsonify(final_results)

# --- Replace your scoring loop with this ---  (Image Only)
# for db_id in candidate_ids:
#     row = db_rows.get(db_id)
#     if not row: continue

#     t_sim = 0.0
#     t_row_ids = [db_data['ids'][x] for x in I_text[i]]
#     if db_id in t_row_ids:
#         t_sim = float(D_text[i][t_row_ids.index(db_id)])

#     l_sim = 0.0
#     if i in logo_results:
#         l_row_ids = [db_data['ids'][x] for x in logo_results[i][1]]
#         if db_id in l_row_ids:
#             l_sim = float(logo_results[i][0][l_row_ids.index(db_id)])

#     db_name = (row['trademark_name'] or "").upper()
#     literal = 1.0 if q_name and q_name == db_name else (0.7 if q_name and q_name in db_name else 0.0)

#     # NEW DYNAMIC SCORING LOGIC
#     if q.get('logo_data') and not q_name:
#         # If user ONLY uploaded an image (like your screenshot)
#         total = l_sim 
#         threshold = 0.35 # Lower threshold for pure visual search
#     elif q_name and not q.get('logo_data'):
#         # If user ONLY provided text
#         total = max(literal, t_sim)
#         threshold = 0.40
#     else:
#         # Combined search (Both text and image exist)
#         total = (max(literal, t_sim) * 0.6) + (l_sim * 0.4)
#         threshold = 0.38

#     if total >= threshold:
#         match_list.append({
#             'id': db_id,
#             'serial': row['serial_number'],
#             'label': row['applicant_name'],
#             'totalSim': round(total * 100, 2),
#             'textSim': round(max(literal, t_sim) * 100, 2),
#             'imgSim': round(l_sim * 100, 2),
#             'description': row['description'],
#             'modalClass': row['class_indices'],
#             'modalAgent': row['agent_details']
#         })

# ===============================================================================================
# DOWNLOAD REPORT AS PDF FORMAT
# ===============================================================================================
@app.route('/api/generate_pdf', methods=['POST'])
def generate_pdf():
    data = request.get_json()
    trademark_id = data.get('id')
    
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
        img = Image(img_data, width=150, height=150)
        img.hAlign = 'LEFT'
        elements.append(img)
    
    elements.append(Spacer(1, 20))

    # 3. Main Info Table
    table_data = [
        [Paragraph("<b>Trademark Name:</b>", styles['Normal']), data.get('label')],
        [Paragraph("<b>Serial Number:</b>", styles['Normal']), data.get('serial')],
        [Paragraph("<b>Class:</b>", styles['Normal']), data.get('modalClass')],
        [Paragraph("<b>Agent:</b>", styles['Normal']), data.get('modalAgent')],
        [Paragraph("<b>Image Similarity:</b>", styles['Normal']), f"{data.get('imgSim')}%"],
        [Paragraph("<b>Text Similarity:</b>", styles['Normal']), f"{data.get('textSim')}%"],
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