from werkzeug.security import generate_password_hash, check_password_hash

# Your existing hash
stored_hash = "scrypt:32768:8:1$dLfvdmMWKnnNyGg0$89fde777b33297bbf9dcbbf09bca0c5e43fc8bd72e9066b81d127896ce8e06a8fafac0d645ef974af785cf6def94760c99dbda716b72335287896fd3992b396d"

# Let's verify a password against this hash
test_password = "123"  # Replace with the password you used
is_valid = check_password_hash(stored_hash, test_password)

print(f"Password verification result: {is_valid}") 