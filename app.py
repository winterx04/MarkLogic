from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'a_secure_random_secret_key'

# --- Page Rendering Routes ---

@app.route('/')
def index():
    return render_template('index.html')

# --- NEW AND IMPROVED SIGN-IN ROUTE ---
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    # This single function now handles both showing the page and processing the form.
    
    # If the form was submitted (method is POST)
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # --- Your authentication logic ---
        if email == 'admin@marklogic.com' and password == 'password':
            flash('You were successfully logged in!', 'success')
            return redirect(url_for('menu'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            # No need to redirect, just render the template again with the error.
            return render_template('signin.html')

    # If the request was GET (just visiting the page), just show the page.
    return render_template('signin.html')


@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/compare')
def compare():
    return render_template('compare.html')

@app.route('/search')
def search():
    return render_template('search.html')

@app.route('/dataset')
def dataset():
    return render_template('dataset.html')

@app.route('/client-dataset')
def client_dataset():
    return render_template('client-dataset.html')

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)