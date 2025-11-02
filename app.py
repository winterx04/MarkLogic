from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import database as db # Import your database functions
import io

app = Flask(__name__)
app.secret_key = 'a_secure_random_secret_key'

# --- Page Rendering Routes ---

@app.route('/')
def index():
    return render_template('index.html')

# # --- Backup In-Case (Hardcoded) ---
# @app.route('/signin', methods=['GET', 'POST'])
# def signin():
#     # This single function now handles both showing the page and processing the form.
    
#     # If the form was submitted (method is POST)
#     if request.method == 'POST':
#         email = request.form.get('email')
#         password = request.form.get('password')

#         # --- Your authentication logic ---
#         if email == 'admin@marklogic.com' and password == 'password':
#             flash('You were successfully logged in!', 'success')
#             return redirect(url_for('menu'))
#         else:
#             flash('Invalid email or password. Please try again.', 'danger')
#             # No need to redirect, just render the template again with the error.
#             return render_template('signin.html')

#     # If the request was GET (just visiting the page), just show the page.
#     return render_template('signin.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # --- NEW DATABASE-DRIVEN AUTHENTICATION ---
        user = db.get_user_by_email(email) # Fetch user from DB

        # Check if user exists and if the password hash matches
        if user and check_password_hash(user['password_hash'], password):
            # The user['password_hash'] comes from the database
            # The 'password' is the plain text from the form
            
            flash('You were successfully logged in!', 'success')
            # Here you would typically set up a user session
            # session['user_id'] = user['id']
            return redirect(url_for('menu'))
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

@app.route('/admin-menu')
def compare():
    return render_template('admin-menu.html')

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

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)