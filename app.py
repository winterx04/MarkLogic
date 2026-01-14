from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_file, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import database as db # Import your database functions
from ml_utils import MLModel
import io
from flask_mail import Mail, Message
import secrets 

app = Flask(__name__)
app.secret_key = 'a_secure_random_secret_key'

# --- Tune this threshold for similar search  ---
app.config['EXACT_MATCH_THRESHOLD'] = 0.05 

# --- INITIALIZE THE EMAIL  ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
# IMPORTANT: Use environment variables in production for security
app.config['MAIL_USERNAME'] = 'xxin589@gmail.com'  # <-- REPLACE with your Gmail
app.config['MAIL_PASSWORD'] = 'jjxh vzax yjyj njsu' # <-- REPLACE with your App Password
app.config['MAIL_DEFAULT_SENDER'] = ('MarkLogic Admin', 'xxin589@gmail.com')

mail = Mail(app)

# --- INITIALIZE THE MODEL (add this right after app config) ---
ml_model = MLModel()
ml_model.build_logo_index() 

# --- Page Rendering Routes ---

@app.route('/')
def index():
    return render_template('index.html')

# --- Admin Routes ---

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in and if their role is 'admin'
        if 'role' not in session or session['role'].lower() != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('menu')) # Redirect non-admins
        return f(*args, **kwargs)
    return decorated_function

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            # Login successful, set up the session
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # --- THIS IS THE KEY CHECK ---
            if user['is_temporary_password']:
                session['force_password_change'] = True
                flash('Welcome! Please create a new password to secure your account.', 'info')
                return redirect(url_for('change_password')) # Force redirect

            # Regular login flow
            flash(f'Welcome back, {user["username"]}!', 'success')
            if user['role'].lower() == 'admin':
                return redirect(url_for('admin_page'))
            else:
                return redirect(url_for('menu'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
    
    return render_template('signin.html')
# ===============================================================================================
# FOR ADMIN USER REGISTRATION

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        # Hash the password before storing it
        password_hash = generate_password_hash(password)

        try:
            # Call the function from database.py file
            db.add_user(username, email, password_hash)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('signin'))
        except ValueError as e:
            # This catches the error if the username or email already exists
            flash(str(e), 'danger')
            return redirect(url_for('register'))

    # If GET request, just show the registration page
    return render_template('register.html') # You will need to create this HTML file
# ===============================================================================================
# FOR TEXT SEARCH

@app.route('/api/text_search', methods=['POST'])
def api_text_search():
    """
    Handles searches based only on words and class filters.
    """
    # Get search terms from the JSON body of the request
    data = request.get_json()
    words = data.get('words')
    class_filter = data.get('class_filter')

    # Use the existing database function without an id_list
    results = db.search_trademarks(
        words=words,
        class_filter=class_filter
    )
    
    results_list = [dict(row) for row in results]
    return jsonify(results_list)

# ===============================================================================================
# FOR VISUAL SEARCH REGISTRATION

# @app.route('/api/image_search', methods=['POST'])
# def api_image_search():
#     # --- 1. Get Inputs ---
#     # We still get text fields in case the user filled them out, to use as filters
#     words = request.form.get('words')
#     class_filter = request.form.get('class_filter')
#     image_file = request.files.get('image')

#     # Image is mandatory for this endpoint
#     if not image_file:
#         return jsonify({'error': 'No image file provided for the search.'}), 400

#     # --- 2. Perform Image Similarity Search ---
#     print(f"Performing image search for: {image_file.filename}")
#     query_embedding = ml_model.generate_image_embedding(image_file.stream)
    
#     if query_embedding is None:
#         return jsonify([]) # Image could not be processed

#     # Use FAISS to find the IDs of the most visually similar logos
#     similar_ids = ml_model.search_logo_index(query_embedding)

#     if not similar_ids:
#         return jsonify([]) # No similar images found

#     # --- 3. Fetch Full Data from Database, Applying Text Filters ---
#     # We use the text/class fields as post-filters on the image search results
#     results = db.search_trademarks(
#         words=words,
#         class_filter=class_filter,
#         id_list=similar_ids # This is the crucial filter
#     )
    
#     # --- 4. Sort and Return Results ---
#     # Preserve the similarity ranking from FAISS
#     results_dict = {row['id']: dict(row) for row in results}
#     sorted_results = [results_dict[res_id] for res_id in similar_ids if res_id in results_dict]

#     return jsonify(sorted_results)

@app.route('/api/image_search', methods=['POST'])
def api_image_search():
    # --- 1. Get Inputs ---
    words = request.form.get('words')
    class_filter = request.form.get('class_filter')
    image_file = request.files.get('image')

    if not image_file:
        return jsonify({'error': 'No image file provided for the search.'}), 400

    # --- 2. Generate Image Embedding ---
    query_embedding = ml_model.generate_image_embedding(image_file.stream)
    
    if query_embedding is None:
        return jsonify({'error': 'Could not process the provided image file.'}), 400

    # --- 3. Perform Similarity Search and Get Distances ---
    try:
        distances, similar_ids = ml_model.search_logo_index(query_embedding, return_distances=True)
    except Exception as e:
        print(f"Error during FAISS search: {e}")
        return jsonify({'error': 'An internal error occurred during the search.'}), 500

    if not similar_ids:
        return jsonify([])

    # --- 4. Filter Results by the Strict Threshold ---
    exact_match_ids = []
    # Use the threshold from the app's configuration
    threshold = app.config['EXACT_MATCH_THRESHOLD']

    for i in range(len(similar_ids)):
        dist = distances[i]
        logo_id = similar_ids[i]
        if dist <= threshold:
            exact_match_ids.append(logo_id)
            print(f"Found an exact match. ID: {logo_id}, Distance: {dist:.4f}")

    if not exact_match_ids:
        return jsonify([]) # Return empty if no logos met the strict criteria

    # --- 5. Fetch Full Data for the EXACT Matches from the Database ---
    results = db.search_trademarks(
        words=words,
        class_filter=class_filter,
        id_list=exact_match_ids
    )
    
    # --- 6. Sort and Return Results ---
    # Preserve the similarity ranking from FAISS to ensure the best match is first.
    results_dict = {row['id']: dict(row) for row in results}
    sorted_results = [results_dict[res_id] for res_id in exact_match_ids if res_id in results_dict]

    return jsonify(sorted_results)

# --- Route to serve trademark logos ---
@app.route('/logo/<int:trademark_id>')
def get_trademark_logo(trademark_id):
    """
    Fetches the binary logo data from the database for a given ID
    and returns it as an image file.
    """
    logo_data = db.get_logo(trademark_id)
    if logo_data:
        # Use io.BytesIO to wrap the binary data and send_file to serve it
        return send_file(
            io.BytesIO(logo_data),
            mimetype='image/png',  # Assuming logos are PNGs, adjust if needed
            as_attachment=False
        )
    else:
        return "Logo not found", 404
    
@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/compare')
def compare():
    return render_template('compare.html')

@app.route('/search')
def search():
    """
    Renders the search page and populates it with all trademarks from the database.
    """
    # Fetch all trademark data using the function from database.py
    all_trademarks = db.get_all_trademarks() 
    
    # Pass the list of trademarks to the template
    return render_template('search.html', trademarks=all_trademarks)

@app.route('/dataset')
def dataset():
    return render_template('dataset.html')

@app.route('/client-dataset')
def client_dataset():
    return render_template('client-dataset.html')



# --- UPDATED: Admin Page Route (loads initial data) ---
# --- UPDATED: The /admin route now renders the new menu page ---
@app.route('/admin')
@admin_required
def admin_page():
    """Renders the admin dashboard/menu page."""
    return render_template('admin.html') # Renders the new menu

# --- NEW: The /user-management route renders the user table page ---
@app.route('/user-management')
@admin_required
def user_management():
    """Renders the user management page with the table of users."""
    all_users = db.get_all_users()
    # Renders the file you renamed to user_management.html
    return render_template('user_management.html', users=all_users)


# RESET PASSWORD FUNCTIONALITY FOR ADMIN TO RESET A USER'S PASSWORD FOR ITERATION 2

@app.route('/api/users/admin_reset_password', methods=['POST'])
@admin_required
def api_admin_reset_password():
    data = request.get_json()
    user_id = data.get('id')
    new_password = data.get('password')

    if not user_id or not new_password:
        return jsonify({'success': False, 'message': 'User ID and new password are required.'}), 400

    try:
        new_password_hash = generate_password_hash(new_password)
        db.admin_reset_password(user_id, new_password_hash)
        # You would then communicate this new temp password to the user out-of-band
        return jsonify({'success': True, 'message': f'Password has been reset. Please provide the new temporary password to the user.'})
    except Exception as e:
        print(f"Error resetting password: {e}")
        return jsonify({'success': False, 'message': 'Failed to reset password.'}), 500

# --- NEW: API Route to ADD a new user ---
@app.route('/api/users/add', methods=['POST'])
@admin_required
def api_add_user():
    data = request.get_json()
    username = data.get('name')
    email = data.get('email')
    role = data.get('role') # No password from form

    if not all([username, email, role]):
        return jsonify({'success': False, 'message': 'Name, email, and role are required.'}), 400

    try:
        # 1. Generate a secure, random temporary password
        temp_password = secrets.token_urlsafe(10) # e.g., 'aBcDeFgH_123'
        password_hash = generate_password_hash(temp_password)

        # 2. Add the user to the DB with the hashed temp password
        # The add_user function should set is_temporary_password to TRUE by default
        db.add_user(username, email, password_hash) 
        new_user = db.get_user_by_email(email)
        db.update_user_role(new_user['id'], role)

        # 3. Send the temporary password email
        msg = Message('Your MarkLogic Account has been Created', recipients=[email])
        msg.body = f'''Hello {username},

An admin has created an account for you. Please sign in at the main login page using your email and the following temporary password:

Temporary Password: {temp_password}

You will be required to set a new, permanent password immediately after your first login.

Thank you,
The MarkLogic Team
'''
        mail.send(msg)

        return jsonify({'success': True, 'message': f'Invitation with temporary password sent to {email}!'})
    except ValueError as e: # Catches duplicate user error
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        print(f"ERROR sending email or creating user: {e}")
        return jsonify({'success': False, 'message': 'An internal server error occurred.'}), 500

# --- NEW: API Route to DELETE a user ---
@app.route('/api/users/delete/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    # Prevent admin from deleting themselves
    if 'user_id' in session and session['user_id'] == user_id:
        return jsonify({'success': False, 'message': 'You cannot delete your own account.'}), 403
    try:
        db.delete_user_by_id(user_id)
        return jsonify({'success': True, 'message': 'User deleted successfully!'})
    except Exception:
        return jsonify({'success': False, 'message': 'Failed to delete user.'}), 500

# --- NEW: API Route to UPDATE a user's role ---
@app.route('/api/users/update_role', methods=['POST'])
@admin_required
def api_update_role():
    data = request.get_json()
    user_id = data.get('user_id')
    new_role = data.get('role')
    try:
        db.update_user_role(user_id, new_role)
        return jsonify({'success': True, 'message': f'Role updated to {new_role}'})
    except Exception:
        return jsonify({'success': False, 'message': 'Failed to update role.'}), 500
    
# --- NEW: API Route to Edit a user's detail ---
@app.route('/api/users/edit', methods=['POST'])
@admin_required
def api_edit_user():
    data = request.get_json()
    user_id = data.get('id')
    new_name = data.get('name')
    new_email = data.get('email')

    if not all([user_id, new_name, new_email]):
        return jsonify({'success': False, 'message': 'Missing user data.'}), 400

    try:
        db.update_user_details(user_id, new_name, new_email)
        return jsonify({'success': True, 'message': 'User updated successfully!'})
    except Exception as e:
        # This can catch errors if the new email is already taken
        return jsonify({'success': False, 'message': 'Failed to update user. The email may already be in use.'}), 500
    
# --- NEW: Route for the forced password change page ---
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'force_password_change' not in session:
        return redirect(url_for('menu'))

    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if not password or password != password_confirm:
            flash('Passwords do not match or are empty.', 'danger')
            return redirect(url_for('change_password'))
        
        new_password_hash = generate_password_hash(password)
        db.update_password_and_deactivate_temp_flag(session['user_id'], new_password_hash)
        
        session.pop('force_password_change', None)
        flash('Your password has been updated successfully!', 'success')
        
        # --- DEBUGGING AND FIX ---
        user_role = session.get('role', '').lower()
        print(f"DEBUG: User role is '{user_role}'. Preparing to redirect.") # This will print in your terminal

        if user_role == 'admin':
            print("DEBUG: Redirecting to admin_page.")
            # Ensure your admin function is named 'admin_page'
            return redirect(url_for('admin')) 
        else:
            print("DEBUG: Redirecting to menu.")
            # Ensure your menu function is named 'menu'
            return redirect(url_for('menu'))
    return render_template('change_password.html')

@app.route('/logout')
def logout():
    session.clear() # Clear all session data
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('signin'))

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)