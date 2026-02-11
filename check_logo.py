import psycopg2
import os

# Your DB credentials
conn = psycopg2.connect(host="localhost", dbname="Test", user="postgres", password="1233")
cur = conn.cursor()

if not os.path.exists('inspect_logos'):
    os.makedirs('inspect_logos')

cur.execute("SELECT id, serial_number, logo_data FROM trademarks WHERE logo_data IS NOT NULL LIMIT 50")
rows = cur.fetchall()

print(f"Exporting {len(rows)} logos for inspection...")

for row in rows:
    tid, serial, data = row
    filename = f"inspect_logos/{serial}_{tid}.png"
    with open(filename, "wb") as f:
        f.write(data)

print("Done! Check the 'inspect_logos' folder.")
cur.close(); conn.close()