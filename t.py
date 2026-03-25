# t.py
from dotenv import load_dotenv
load_dotenv()  # MUST come first

from app import app  # now env variables are loaded

print("MAIL_SERVER:", app.config['MAIL_SERVER'])
print("MAIL_PORT:", app.config['MAIL_PORT'])
print("MAIL_USE_TLS:", app.config['MAIL_USE_TLS'])