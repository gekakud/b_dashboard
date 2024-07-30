import bcrypt

# The password to hash
password = "Booggii2024".encode()

# Generating a salt and hash the password
salt = bcrypt.gensalt(rounds=12)  # You can adjust the cost factor according to your security requirement
hashed_password = bcrypt.hashpw(password, salt)

print(hashed_password.decode())
