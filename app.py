from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_file, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import database as db # Import your database functions
import io

app = Flask(__name__)
app.secret_key = 'a_secure_random_secret_key'

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

# # --- Backup In-Case (Hardcoded) ---
# @app.route('/signin', methods=['GET', 'POST'])
# def signin():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         password = request.form.get('password')

#         # --- NEW DATABASE-DRIVEN AUTHENTICATION ---
#         user = db.get_user_by_email(email) # Fetch user from DB

#         # Check if user exists and if the password hash matches
#         if user and check_password_hash(user['password_hash'], password):
#             # The user['password_hash'] comes from the database
#             # The 'password' is the plain text from the form
            
#             flash('You were successfully logged in!', 'success')
#             # Here you would typically set up a user session
#             # session['user_id'] = user['id']
#             return redirect(url_for('menu'))
#         else:
#             flash('Invalid email or password. Please try again.', 'danger')
#             return render_template('signin.html')

#     return render_template('signin.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = db.get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            # --- SESSION MANAGEMENT ---
            # Store user info in the session to remember them
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role'] # Store the role!
            
            flash(f'Welcome back, {user["username"]}!', 'success')

            # --- ROLE-BASED REDIRECTION ---
            if user['role'].lower() == 'admin':
                return redirect(url_for('admin_page')) # Redirect admins to the admin page
            else:
                return redirect(url_for('menu')) # Redirect regular users to the menu
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('signin.html')

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

# In app.py, replace the old '/api/search' route with this new one.

@app.route('/api/combined_search', methods=['POST'])
def api_combined_search():
    """
    Handles a combined search request containing text fields and optionally an image file.
    """
    # Get text data from the form part of the request
    words = request.form.get('words')
    class_filter = request.form.get('class_filter')
    
    # Get image data from the file part of the request
    image_file = request.files.get('image')

    # --- Placeholder for Image Search Logic ---
    if image_file:
        # In a real application, you would do the following:
        # 1. Read the image_file.read() bytes
        # 2. Pre-process the image (resize, normalize)
        # 3. Generate an embedding vector using your ML model
        # 4. Use the vector to perform a similarity search with FAISS
        # 5. Get a list of IDs from the similarity search to filter the text search results.
        print(f"Received image: {image_file.filename}") # For now, just print that we got it

    # Perform the text-based search using your existing database function
    # In the future, you would combine the results from the image search here.
    results = db.search_trademarks(words=words, class_filter=class_filter)
    
    # Convert results to a JSON-friendly format and return
    results_list = [dict(row) for row in results]
    return jsonify(results_list)

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
@app.route('/admin')
@admin_required
def admin_page():
    """Renders the admin page and populates it with all users."""
    all_users = db.get_all_users()
    return render_template('admin.html', users=all_users)

# --- NEW: API Route to ADD a new user ---
@app.route('/api/users/add', methods=['POST'])
@admin_required
def api_add_user():
    data = request.get_json()
    username = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if not all([username, email, password, role]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    password_hash = generate_password_hash(password)
    try:
        db.add_user(username, email, password_hash)
        # We also need to add 'role' to the user, let's update the user after creation
        new_user = db.get_user_by_email(email)
        db.update_user_role(new_user['id'], role)
        return jsonify({'success': True, 'message': 'User added successfully!'})
    except ValueError as e: # Catches duplicate user error
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500

# --- NEW: API Route to DELETE a user ---
@app.route('/api/users/delete/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user():
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

@app.route('/logout')
def logout():
    session.clear() # Clear all session data
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('signin'))

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)