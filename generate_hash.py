# generate_hash.py
from werkzeug.security import generate_password_hash

# Ganti 'mhs123' dengan password yang diinginkan
password = "pass123"
hashed_password = generate_password_hash(password)

print(f"Password: {password}")
print(f"Hash: {hashed_password}")