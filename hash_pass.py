from werkzeug.security import generate_password_hash

# The plaintext password you want to hash
plain_password = "password@skrine"

# Generate the secure, salted hash
hashed_password = generate_password_hash(plain_password)

# Print the result so you can copy it
print(f"Plaintext password: {plain_password}")
print(f"Hashed password for database: {hashed_password}")