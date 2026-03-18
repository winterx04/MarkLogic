import re
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
    Includes law-firm specific columns.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create the trademarks table with NEW columns for the Perfect Extractor
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trademarks (
            id SERIAL PRIMARY KEY,
            serial_number VARCHAR(50) UNIQUE NOT NULL,
            int_reg_number VARCHAR(50),
            class_indices TEXT,
            registration_date TEXT,
            trademark_name TEXT,
            description TEXT,
            disclaimer TEXT,
            applicant_name TEXT,
            applicant_address TEXT,
            agent_details TEXT,
            logo_data BYTEA,
            evidence_snapshot BYTEA,
            text_embedding BYTEA,
            logo_embedding BYTEA,
            batch_number VARCHAR(10),
            batch_year VARCHAR(10),
            category VARCHAR(50) DEFAULT 'MYIPO',
            is_split BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create the users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) NOT NULL,
            is_temporary_password BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Client Trademarks Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_trademarks (
            id SERIAL PRIMARY KEY,
            file_name TEXT,
            logo_data BYTEA,
            logo_embedding BYTEA,
            applicant_name TEXT,
            description TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close(); conn.close()
    
    print("Database initialized successfully.")

# ==============================================================================
# USER MANAGEMENT FUNCTIONS 
# ==============================================================================

def get_user_by_email(email):
    """Fetches a user record by their email address."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close(); conn.close()
    return user

def get_all_users():
    """Fetches all users from the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, username, email, role FROM users ORDER BY id ASC")
    users = cur.fetchall()
    cur.close(); conn.close()
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
        raise e
    finally:
        cur.close(); conn.close()

def update_user_role(user_id, new_role):
    """Updates the role for a specific user."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close(); conn.close()

def update_user_details(user_id, new_name, new_email):
    """Updates a user's name and email address."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET username = %s, email = %s WHERE id = %s", (new_name, new_email, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close(); conn.close()

def add_user(username, email, password_hash):
    """Inserts a new user and marks their password as temporary."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (username, email, password_hash, role, is_temporary_password) 
            VALUES (%s, %s, %s, 'viewer', TRUE)
        """, (username, email, password_hash))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise ValueError(f"User with username '{username}' or email '{email}' already exists.")
    finally:
        cur.close(); conn.close()

def admin_reset_password(user_id, new_password_hash):
    """Resets a user's password and forces change on next login."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = %s, is_temporary_password = TRUE WHERE id = %s", (new_password_hash, user_id))
    conn.commit()
    cur.close(); conn.close()

def update_password_and_deactivate_temp_flag(user_id, new_password_hash):
    """Updates a user's password and sets the temporary flag to FALSE."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = %s, is_temporary_password = FALSE WHERE id = %s", (new_password_hash, user_id))
    conn.commit()
    cur.close(); conn.close()

# ==============================================================================
# TRADEMARK MANAGEMENT FUNCTIONS (EXPANDED FOR PERFECT EXTRACTOR)
# ==============================================================================

def insert_client_trademark(data):
    conn = get_db_connection()
    cur = conn.cursor()
    logo_emb = data['logo_embedding'].tobytes() if data.get('logo_embedding') is not None else None
    try:
        cur.execute("""
            INSERT INTO client_trademarks 
            (file_name, logo_data, logo_embedding, applicant_name, description, upload_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get('file_name'),
            psycopg2.Binary(data.get('logo_data')) if data.get('logo_data') else None,
            logo_emb,
            data.get('applicant_name'),
            data.get('description'),
            data.get('custom_date') # This maps to the date the user selected
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close(); conn.close()

def get_client_query_items():
    """Fetches items from the client table to be used as search queries."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Note: We use applicant_name as trademark_name for consistency in the search loop
    cur.execute("""
        SELECT id, applicant_name as trademark_name, description, logo_data 
        FROM client_trademarks
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_client_logo(client_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT logo_data FROM client_trademarks WHERE id = %s", (client_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None

def get_all_client_embeddings():
    """Fetches embeddings specifically from the client table for FAISS."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, logo_embedding FROM client_trademarks WHERE logo_embedding IS NOT NULL")
    rows = cur.fetchall()
    cur.close(); conn.close()

    db_data = {'logo': [], 'ids': [], 'text': []} # Text is empty for client usually
    for row in rows:
        db_id, logo_bytes = row
        db_data['ids'].append(db_id)
        db_data['logo'].append(np.frombuffer(logo_bytes, dtype=np.float32))
        # Provide dummy text embedding to keep FAISS index logic consistent
        db_data['text'].append(np.zeros(384, dtype=np.float32)) 
    return db_data

def insert_trademark(data):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # This removes "All included in Class 11" so you get pure goods data
    raw_desc = data.get('description', '')
    if raw_desc:
        data['description'] = re.sub(r'All included in Class \d+\.?', '', raw_desc, flags=re.I).strip()

    text_emb = data['text_embedding'].tobytes() if data.get('text_embedding') is not None else None
    logo_emb = data['logo_embedding'].tobytes() if data.get('logo_embedding') is not None else None

    try:
        cur.execute("""
            INSERT INTO trademarks (
                serial_number, int_reg_number, class_indices, registration_date, 
                trademark_name, description, disclaimer, applicant_name, 
                applicant_address, agent_details, logo_data, evidence_snapshot, 
                text_embedding, logo_embedding, category, is_split,
                batch_number, batch_year
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (serial_number) DO UPDATE SET
                trademark_name = EXCLUDED.trademark_name,
                class_indices = EXCLUDED.class_indices,
                description = EXCLUDED.description,
                applicant_name = EXCLUDED.applicant_name,
                applicant_address = EXCLUDED.applicant_address,
                agent_details = EXCLUDED.agent_details,
                logo_data = EXCLUDED.logo_data,
                evidence_snapshot = EXCLUDED.evidence_snapshot,
                text_embedding = EXCLUDED.text_embedding,
                logo_embedding = EXCLUDED.logo_embedding,
                batch_number = EXCLUDED.batch_number,
                batch_year = EXCLUDED.batch_year;
        """, (
            data.get('serial_number'), data.get('int_reg_number'),
            data.get('class_indices'), data.get('registration_date'),
            data.get('trademark_name'), data.get('description'),
            data.get('disclaimer'), data.get('applicant_name'),
            data.get('applicant_address'), data.get('agent_details'),
            data.get('logo_data'), data.get('evidence_snapshot'),
            text_emb, logo_emb, data.get('category', 'MYIPO'),
            data.get('is_split', False),
            data.get('batch_number'),
            data.get('batch_year')
        ))
        conn.commit()
    except Exception as e:
        print(f"Upsert Error: {e}")
        conn.rollback()
    finally:
        cur.close(); conn.close()

def get_all_trademarks():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, serial_number, trademark_name, class_indices, applicant_name, category, is_split,
               (logo_data IS NOT NULL) as has_logo,
               batch_number, batch_year
        FROM trademarks
        ORDER BY id DESC
    """)
    trademarks = cur.fetchall()
    cur.close(); conn.close()
    return trademarks

def get_logo(trademark_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT logo_data FROM trademarks WHERE id = %s", (trademark_id,))
    logo_data = cur.fetchone()
    cur.close(); conn.close()
    return logo_data[0] if logo_data else None

def get_evidence(trademark_id):
    """Fetches the full block evidence snapshot."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT evidence_snapshot FROM trademarks WHERE id = %s", (trademark_id,))
    data = cur.fetchone()
    cur.close(); conn.close()
    return data[0] if data else None

def get_all_embeddings(category=None):
    """Fetches embeddings for building the FAISS index."""
    conn = get_db_connection()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT id, text_embedding, logo_embedding FROM trademarks WHERE category = %s", (category,))
    else:
        cur.execute("SELECT id, text_embedding, logo_embedding FROM trademarks")
    rows = cur.fetchall()
    cur.close(); conn.close()

    db_data = {'text': [], 'logo': [], 'ids': []}
    for row in rows:
        db_id, text_bytes, logo_bytes = row
        db_data['ids'].append(db_id)
        if text_bytes:
            db_data['text'].append(np.frombuffer(text_bytes, dtype=np.float32))
        if logo_bytes:
            db_data['logo'].append(np.frombuffer(logo_bytes, dtype=np.float32))
        else:
            db_data['logo'].append(np.zeros(512, dtype=np.float32))
    return db_data

def delete_trademark_by_id(trademark_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM trademarks WHERE id = %s", (trademark_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
# ==============================================================================
# SEARCH FUNCTIONS 
# ==============================================================================

def search_trademarks(words=None, class_filter=None, id_list=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query = """
        SELECT id, 
               serial_number, 
               class_indices, 
               applicant_name, 
               agent_details, 
               description,
               (logo_data IS NOT NULL) as has_logo 
        FROM trademarks
    """
    # Allow Serial Number Search
    where_clauses = []
    params = []

    if words and words.strip():
        clean_words = words.strip().replace(" ", "")
        term = f"%{clean_words}%"

        where_clauses.append("""
        (
            trademark_name ILIKE %s
        OR applicant_name ILIKE %s
        OR REGEXP_REPLACE(serial_number, '\\s+', '', 'g') ILIKE %s
        OR description ILIKE %s
        )
        """)
        params.extend([term, term, term, term])

    if class_filter and class_filter.strip():
        where_clauses.append("class_indices ILIKE %s")
        params.append(f"%{class_filter.strip()}%")

    if id_list:
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
# GET QUERY (COMPARE)
# ==============================================================================
def get_query_items_by_category(category):
    """Fetches full trademark data to be used as query items for comparison."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT serial_number, trademark_name, description, logo_data 
        FROM trademarks 
        WHERE category = %s
    """, (category,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    # Format to match what the search loop expects
    return [dict(r) for r in rows]