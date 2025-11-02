import psycopg2
import psycopg2.extras
import numpy as np

# --- DATABASE CONNECTION DETAILS ---
DB_HOST = "localhost"
DB_NAME = "Test"
DB_USER = "postgres"
DB_PASS = "1233"

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    return conn

def init_db():
    """
    Initializes the database, creating the 'trademarks' and 'users' tables.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create the trademarks table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trademarks (
            id SERIAL PRIMARY KEY,
            serial_number VARCHAR(50) UNIQUE NOT NULL,
            class_indices TEXT,
            registration_date DATE,
            description TEXT,
            applicant_name TEXT,
            agent_details TEXT,
            logo_data BYTEA,
            text_embedding BYTEA,
            logo_embedding BYTEA,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # --- NEW: Create the users table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, -- IMPORTANT: Store hashed passwords, not plaintext
            role VARCHAR(20) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully with 'trademarks' and 'users' tables.")

# ==============================================================================
# USER MANAGEMENT FUNCTIONS 
# ==============================================================================

def add_user(username, email, password_hash):
    """
    Inserts a new user into the users table.
    IMPORTANT: You must hash the password *before* calling this function.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)
        """, (username, email, password_hash))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()  # Rollback the transaction on error
        raise ValueError(f"User with username '{username}' or email '{email}' already exists.")
    except Exception as e:
        conn.rollback()
        print(f"Database error adding user: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

def get_user_by_email(email):
    """Fetches a user record by their email address."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # DictCursor is helpful for login
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user


# ==============================================================================
# TRADEMARK MANAGEMENT FUNCTIONS 
# ==============================================================================

def insert_trademark(data):
    """Inserts a single trademark record, including binary logo data, into the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    text_embedding_bytes = data['text_embedding'].tobytes()
    logo_embedding_bytes = data['logo_embedding'].tobytes() if 'logo_embedding' in data and data['logo_embedding'] is not None else None
    logo_data_bytes = data.get('logo_data')

    try:
        cur.execute("""
            INSERT INTO trademarks (serial_number, class_indices, registration_date, description, applicant_name, agent_details, logo_data, text_embedding, logo_embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (serial_number) DO NOTHING;
        """, (
            data.get('serial_number'),
            data.get('class_indices'),
            data.get('date'),
            data.get('description'),
            data.get('applicant'),
            data.get('agent'),
            logo_data_bytes,
            text_embedding_bytes,
            logo_embedding_bytes
        ))
        conn.commit()
    except Exception as e:
        print(f"Error inserting trademark {data.get('serial_number')}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_all_trademarks():
    """Fetches all trademarks, noting if a logo exists."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, serial_number, class_indices, registration_date, applicant_name, description,
               (logo_data IS NOT NULL) as has_logo
        FROM trademarks ORDER BY id DESC
    """)
    trademarks = cur.fetchall()
    cur.close()
    conn.close()
    return trademarks

def get_logo(trademark_id):
    """Fetches the binary logo data for a specific trademark ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT logo_data FROM trademarks WHERE id = %s", (trademark_id,))
    logo_data = cur.fetchone()
    cur.close()
    conn.close()
    return logo_data[0] if logo_data else None

def get_all_embeddings():
    """Fetches all embeddings and IDs to build the FAISS index."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text_embedding, logo_embedding FROM trademarks")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    db_data = {'text': [], 'logo': [], 'ids': []}
    text_dim = 384
    logo_dim = 512

    for row in rows:
        db_id, text_emb_bytes, logo_emb_bytes = row
        db_data['ids'].append(db_id)
        
        text_emb = np.frombuffer(text_emb_bytes, dtype=np.float32)
        db_data['text'].append(text_emb)
        
        if logo_emb_bytes:
            logo_emb = np.frombuffer(logo_emb_bytes, dtype=np.float32)
            db_data['logo'].append(logo_emb)
        else:
            db_data['logo'].append(np.zeros(logo_dim, dtype=np.float32))
            
    return db_data



# ==============================================================================
# SEARCH FUNCTIONS 
# ==============================================================================

# def search_trademarks(words=None, class_filter=None):
#     """
#     Fetches trademarks from the database, filtering by words and/or class.
#     """
#     conn = get_db_connection()
#     cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
#     query = """
#         SELECT id, serial_number, class_indices, registration_date, applicant_name, description,
#                (logo_data IS NOT NULL) as has_logo
#         FROM trademarks
#     """
    
#     where_clauses = []
#     params = []
    
#     if words:
#         where_clauses.append("(description ILIKE %s OR applicant_name ILIKE %s)")
#         params.extend([f'%{words}%', f'%{words}%'])
        
#     # --- THIS IS THE BLOCK TO CHANGE ---
#     if class_filter:
#         # The '\y' is a word boundary in PostgreSQL's regex.
#         # This ensures that searching for '9' matches '9' or '3, 9' but NOT '19' or '29'.
#         where_clauses.append("class_indices ~ %s")
#         # We build the regex pattern here. The \\y is needed to escape the backslash in the f-string.
#         params.append(f'\\y{class_filter}\\y')
#     # --- END OF CHANGED BLOCK ---
        
#     if where_clauses:
#         query += " WHERE " + " AND ".join(where_clauses)
        
#     query += " ORDER BY id DESC"
    
#     cur.execute(query, tuple(params))
#     trademarks = cur.fetchall()
#     cur.close()
#     conn.close()
#     return trademarks

# In database.py

def search_trademarks(words=None, class_filter=None, id_list=None):
    """
    Fetches trademarks, filtering by text, class, AND an optional list of IDs from image search.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    query = """
        SELECT id, serial_number, class_indices, registration_date, applicant_name, description,
               (logo_data IS NOT NULL) as has_logo
        FROM trademarks
    """
    
    where_clauses = []
    params = []
    
    if words:
        where_clauses.append("(description ILIKE %s OR applicant_name ILIKE %s)")
        params.extend([f'%{words}%', f'%{words}%'])
        
    if class_filter:
        where_clauses.append("class_indices ~ %s")
        params.append(f'\\y{class_filter}\\y')
        
    # --- THIS IS THE KEY ADDITION ---
    # Filter by the list of IDs from the FAISS image search
    if id_list is not None:
        # If the image search returns no IDs, we must return no results.
        if not id_list:
            id_list = [-1] # Use a dummy ID that will never match
        where_clauses.append("id = ANY(%s)")
        params.append(id_list)
        
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
        
    query += " ORDER BY id DESC"
    
    cur.execute(query, tuple(params))
    trademarks = cur.fetchall()
    cur.close()
    conn.close()
    return trademarks

# ==============================================================================
# ADMIN MANAGE USER FUNCTIONS 
# ==============================================================================
def get_all_users():
    """Fetches all users from the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, username, email, role FROM users ORDER BY id ASC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def delete_user_by_id(user_id):
    """Deletes a user from the database by their ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Database error deleting user: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

def update_user_role(user_id, new_role):
    """Updates the role for a specific user."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Database error updating role: {e}")
        raise e
    finally:
        cur.close()
        conn.close()