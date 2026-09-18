import os
import re
import psycopg2
import psycopg2.extras
import numpy as np
from dotenv import load_dotenv

import similarity

# Get .env
load_dotenv()

# --- DATABASE CONNECTION DETAILS ---
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

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
            international_registration_date TEXT,
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

    # One-to-many logo storage: a single trademark filing can have more than
    # one logo crop (e.g. a device + a separate text_logo, or several
    # sub-elements of one composite mark). Each row is one crop; trademark_id
    # ties any number of them back to the same parent filing.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trademark_logos (
            id SERIAL PRIMARY KEY,
            trademark_id INTEGER NOT NULL REFERENCES trademarks(id) ON DELETE CASCADE,
            logo_data BYTEA NOT NULL,
            logo_embedding BYTEA,
            label TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trademark_logos_trademark_id
        ON trademark_logos(trademark_id);
    """)

    # Client Trademarks Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_trademarks (
            id SERIAL PRIMARY KEY,
            file_name TEXT,
            logo_data BYTEA,
            logo_embedding BYTEA,
            text_embedding BYTEA,
            applicant_name TEXT,
            description TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Migrates existing installs (CREATE TABLE IF NOT EXISTS above is a no-op for them)
    cur.execute("ALTER TABLE client_trademarks ADD COLUMN IF NOT EXISTS text_embedding BYTEA;")
    cur.execute("ALTER TABLE trademarks ADD COLUMN IF NOT EXISTS international_registration_date TEXT;")
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
    text_emb = data['text_embedding'].tobytes() if data.get('text_embedding') is not None else None
    try:
        cur.execute("""
            INSERT INTO client_trademarks
            (file_name, logo_data, logo_embedding, text_embedding, applicant_name, description, upload_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get('file_name'),
            psycopg2.Binary(data.get('logo_data')) if data.get('logo_data') else None,
            logo_emb,
            text_emb,
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
    cur.execute("SELECT id, logo_embedding, text_embedding FROM client_trademarks WHERE logo_embedding IS NOT NULL")
    rows = cur.fetchall()
    cur.close(); conn.close()

    db_data = {'logo': [], 'ids': [], 'text': []}
    for row in rows:
        db_id, logo_bytes, text_bytes = row
        db_data['ids'].append(db_id)
        db_data['logo'].append(np.frombuffer(logo_bytes, dtype=np.float32))
        # Legacy rows uploaded before text_embedding existed fall back to a
        # dummy zero vector (contributes 0 similarity, same as before this fix).
        if text_bytes:
            db_data['text'].append(np.frombuffer(text_bytes, dtype=np.float32))
        else:
            db_data['text'].append(np.zeros(similarity.TEXT_EMBEDDING_DIM, dtype=np.float32))
    return db_data

def insert_trademark(data, conn=None):
    """Pass an existing connection (e.g. when inserting many records in a
    loop, such as a PDF batch upload) to avoid the cost of opening a fresh
    one per call - that overhead alone can dominate a bulk-insert loop's
    total time. Callers that pass their own conn are responsible for closing
    it; this function will not close a connection it didn't open itself."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_db_connection()
    cur = conn.cursor()

    # This removes "All included in Class 11" so you get pure goods data
    raw_desc = data.get('description', '')
    if raw_desc:
        data['description'] = re.sub(r'All included in Class \d+\.?', '', raw_desc, flags=re.I).strip()

    text_emb = data['text_embedding'].tobytes() if data.get('text_embedding') is not None else None
    logo_emb = data['logo_embedding'].tobytes() if data.get('logo_embedding') is not None else None

    # Accept either key name - pdf_extractor.py's result dicts use the
    # spelled-out 'international_registration_number', while some older
    # callers may still use the column's own short name.
    int_reg_number = data.get('int_reg_number') or data.get('international_registration_number')

    try:
        cur.execute("""
            INSERT INTO trademarks (
                serial_number, int_reg_number, international_registration_date,
                class_indices, registration_date,
                trademark_name, description, disclaimer, applicant_name,
                applicant_address, agent_details, logo_data, evidence_snapshot,
                text_embedding, logo_embedding, category, is_split,
                batch_number, batch_year
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (serial_number) DO UPDATE SET
                int_reg_number = EXCLUDED.int_reg_number,
                international_registration_date = EXCLUDED.international_registration_date,
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
                batch_year = EXCLUDED.batch_year
            RETURNING id;
        """, (
            data.get('serial_number'), int_reg_number,
            data.get('international_registration_date'),
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
        trademark_id = cur.fetchone()[0]
        conn.commit()
        return trademark_id
    except Exception as e:
        print(f"Upsert Error: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        if owns_conn:
            conn.close()

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

def get_all_trademarks_manageTab():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, serial_number, trademark_name, class_indices, applicant_name, description, category, is_split,
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

def insert_trademark_logo(trademark_id, logo_data, logo_embedding=None, label=None, conn=None):
    """Inserts one logo crop as a child row of an existing trademark. A single
    trademark can have any number of these (e.g. a device + a text_logo, or
    several sub-elements of one composite mark - see trademark_logos above).
    Pass an existing connection when inserting many in a loop - see
    insert_trademark's docstring for why that matters."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_db_connection()
    cur = conn.cursor()
    logo_emb = logo_embedding.tobytes() if logo_embedding is not None else None
    try:
        cur.execute("""
            INSERT INTO trademark_logos (trademark_id, logo_data, logo_embedding, label)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (trademark_id, psycopg2.Binary(logo_data), logo_emb, label))
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        if owns_conn:
            conn.close()

def get_trademark_logos(trademark_id):
    """Fetches every logo crop belonging to one trademark (for display)."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "SELECT id, logo_data, label FROM trademark_logos WHERE trademark_id = %s ORDER BY id",
        (trademark_id,),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

def get_all_logo_variant_embeddings():
    """
    Fetches every logo embedding for FAISS indexing - both new one-to-many
    trademark_logos rows AND legacy trademarks.logo_embedding rows that
    predate this table (kept as a fallback so old data still gets indexed).
    A trademark with rows in trademark_logos is not double-counted via its
    legacy column.

    Returns {'ids': [...], 'trademark_ids': [...], 'logo': [...]} where 'ids'
    are globally-unique keys safe to use as FAISS vector ids (several ids can
    map to the same trademark_id - that's the whole point).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    entries = []  # (row_key, trademark_id, embedding_bytes)

    cur.execute("SELECT id, trademark_id, logo_embedding FROM trademark_logos WHERE logo_embedding IS NOT NULL")
    for row_id, trademark_id, emb_bytes in cur.fetchall():
        entries.append((row_id, trademark_id, emb_bytes))

    # Legacy fallback: trademarks with an old-style single logo_embedding and
    # no trademark_logos rows yet. Offset keeps these row_keys out of
    # trademark_logos' own id space (safe unless that table exceeds 1 billion rows).
    LEGACY_ID_OFFSET = 1_000_000_000
    cur.execute("""
        SELECT t.id, t.logo_embedding
        FROM trademarks t
        WHERE t.logo_embedding IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM trademark_logos tl WHERE tl.trademark_id = t.id)
    """)
    for trademark_id, emb_bytes in cur.fetchall():
        entries.append((LEGACY_ID_OFFSET + trademark_id, trademark_id, emb_bytes))

    cur.close(); conn.close()

    db_data = {'ids': [], 'trademark_ids': [], 'logo': []}
    for row_key, trademark_id, emb_bytes in entries:
        db_data['ids'].append(row_key)
        db_data['trademark_ids'].append(trademark_id)
        db_data['logo'].append(np.frombuffer(emb_bytes, dtype=np.float32))
    return db_data

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
            db_data['logo'].append(np.zeros(similarity.IMAGE_EMBEDDING_DIM, dtype=np.float32))
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
            REGEXP_REPLACE(trademark_name, '\\s+', '', 'g') ILIKE %s
        OR REGEXP_REPLACE(applicant_name, '\\s+', '', 'g') ILIKE %s
        OR REGEXP_REPLACE(serial_number, '\\s+', '', 'g') ILIKE %s
        OR REGEXP_REPLACE(description, '\\s+', '', 'g') ILIKE %s
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