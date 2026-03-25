import os
from dotenv import load_dotenv
from pathlib import Path

# 👇 Force absolute path to .env
env_path = Path(__file__).resolve().parent / ".env"

print("USING ENV PATH:", env_path)
print("EXISTS:", env_path.exists())

load_dotenv(dotenv_path=env_path)

print("FINAL CONFIG:", {
    "DB_HOST": os.getenv("DB_HOST"),
    "DB_NAME": os.getenv("DB_NAME"),
    "DB_USER": os.getenv("DB_USER"),
    "DB_PASS": os.getenv("DB_PASS"),
})