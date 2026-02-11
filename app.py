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

# Import your updated database functions and the Perfect Extractor
import database as db 
from ml_utils import MLModel
from pdf_extractor import extract_all # This must be the stateful extractor we discussed

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
        if 'role' not in session or session['role'].lower() != 'admin':
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
            return redirect(url_for('admin_page') if user['role'].lower() == 'admin' else url_for('menu'))
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
            return redirect(url_for('admin_page') if session.get('role') == 'admin' else url_for('menu'))
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
    # Grab the extra fields from the form data
    batch = request.form.get('batch_number')
    year = request.form.get('batch_year')

    if not file or not batch or not year:
        return jsonify({'success': False, 'message': 'Missing File, Batch, or Year'}), 400

    try:
        # 1. Extract from PDF
        raw_trademarks = extract_all(io.BytesIO(file.read()))
        
        for tm in raw_trademarks:
            # 2. Add the Metadata to every extracted record
            tm['category'] = category
            tm['batch_number'] = batch
            tm['batch_year'] = year
            
            # 3. Embeddings
            combined_text = f"{tm['trademark_name']} {tm['description']}"
            tm['text_embedding'] = ml_model.generate_text_embedding(combined_text)
            tm['logo_embedding'] = ml_model.generate_image_embedding(io.BytesIO(tm['logo_data']))
            
            # 4. Save
            db.insert_trademark(tm)
            
        ml_model.build_logo_index()
        return jsonify({'success': True, 'message': f'Imported {len(raw_trademarks)} records into Batch {batch}/{year}'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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
    match_ids = [similar_ids[i] for i, d in enumerate(distances) if d <= 0.25]
    
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
    if not file: return jsonify({'error': 'No file'}), 400
    
    target = request.form.get('target', 'MYIPO')
    db_data = db.get_all_embeddings(category=target)
    if not db_data['ids']: return jsonify({'error': 'Dataset empty'}), 400

    # Local Index for this category (Normalized Cosine)
    db_logos = np.vstack(db_data['logo']).astype('float32')
    faiss.normalize_L2(db_logos)
    index = faiss.IndexFlatIP(512) 
    index.add(db_logos)

    final_results = []
    print("\n" + "#"*60 + f"\nDEBUG: SEARCH STARTED: {file.filename}\n" + "#"*60)
    sys.stdout.flush()

    try:
        # Handle Single Image Logic
        query_logo_emb = ml_model.generate_image_embedding(file.stream)
        if query_logo_emb is not None:
            query_logo_emb = query_logo_emb.reshape(1, -1).astype('float32')
            faiss.normalize_L2(query_logo_emb)

            similarities, indices = index.search(query_logo_emb, 10)
            
            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx == -1: continue
                
                raw_sim = float(similarities[0][i])
                score = round(raw_sim * 100, 2)
                db_id = db_data['ids'][idx]
                
                # Fetch details for the UI card
                conn = db.get_db_connection()
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("SELECT * FROM trademarks WHERE id = %s", (db_id,))
                tm = cur.fetchone()
                cur.close(); conn.close()

                print(f"MATCH: {tm['serial_number']} | Brand: {tm['trademark_name']} | SIM: {score}%")
                sys.stdout.flush()

                final_results.append({
                    'id': db_id,
                    'label': tm['trademark_name'] or tm['applicant_name'],
                    'imgSim': score,
                    'textSim': 0,
                    'modalTrademarkNum': tm['serial_number'],
                    'modalClass': tm['class_indices'],
                    'modalDescription': tm['description'],
                    'isSplit': tm['is_split']
                })

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({'error': str(e)}), 500
    
    print("#"*60 + "\nDEBUG: SEARCH FINISHED\n" + "#"*60)
    sys.stdout.flush()
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