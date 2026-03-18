# import psycopg2
# import os

# # Your DB credentials
# conn = psycopg2.connect(host="localhost", dbname="Test", user="postgres", password="1233")
# cur = conn.cursor()

# if not os.path.exists('inspect_logos'):
#     os.makedirs('inspect_logos')

# # cur.execute("SELECT id, serial_number, logo_data FROM trademarks WHERE logo_data IS NOT NULL LIMIT 50")
# # cur.execute("SELECT id, serial_number, logo_data FROM trademarks WHERE logo_data IS NOT NULL LIMIT 50")


# cur.execute("SELECT id, logo_data FROM client_trademarks WHERE logo_data IS NOT NULL LIMIT 50")
# rows = cur.fetchall()

# print(f"Exporting {len(rows)} logos for inspection...")

# for row in rows:
#     tid, serial, data = row
#     filename = f"inspect_logos/{serial}_{tid}.png"
#     with open(filename, "wb") as f:
#         f.write(data)

# print("Done! Check the 'inspect_logos' folder.")
# cur.close(); conn.close()


# BELOW ARE FOR CHECKING CLIENT LOGOS INSTEAD OF TRADEMARKS, WITH BETTER FILENAME HANDLING
import psycopg2
import os
import re

# Database credentials
DB_CONFIG = {
    "host": "localhost",
    "dbname": "Test",
    "user": "postgres",
    "password": "1233"
}

def sanitize_filename(name):
    """Removes characters that aren't allowed in Windows/Linux filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", str(name))

def export_client_logos():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Create folder
        folder = 'inspect_client_logos'
        if not os.path.exists(folder):
            os.makedirs(folder)

        # Select ID, Applicant Name (to use as filename), and the Logo Data
        # Using COALESCE to fallback to file_name if applicant_name is empty
        cur.execute("""
            SELECT id, COALESCE(applicant_name, file_name, 'no_name'), logo_data 
            FROM client_trademarks 
            WHERE logo_data IS NOT NULL 
            LIMIT 50
        """)
        
        rows = cur.fetchall()
        print(f"🔍 Found {len(rows)} logos in client_trademarks. Exporting...")

        for row in rows:
            tid, name, data = row # Unpack 3 values matching 3 selected columns
            
            clean_name = sanitize_filename(name)[:30] # Limit length
            filename = f"{folder}/ID_{tid}_{clean_name}.png"

            with open(filename, "wb") as f:
                f.write(data)
            print(f"✅ Saved: {filename}")

        print(f"\n✨ Done! Check the '{folder}' folder on your computer.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    export_client_logos()