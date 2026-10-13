from app.security import hash_password, verify_password

def test_hash_is_not_the_password():
    hashed = hash_password("Correct horse battery")
    assert hashed != "Correct horse battery"
    assert hashed.startswith("$argon2id$")

def test_verify_password():
    password ="SecretPassword123!"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword", hashed)

def test_hash_with_empty_password():
    hashed = hash_password("")
    assert hashed != ""
    assert hashed.startswith("$argon2id$")
    assert verify_password("", hashed)
    assert not verify_password("NotEmpty", hashed)

def  test_hash_with_special_characters():
    password = "P@$$w0rd!#%&*()_+-=[]{}|;:',.<>?/~`"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)

def test_salt_uniqueness():
    password = "UniqueSaltTest"
    hashed1 = hash_password(password)
    hashed2 = hash_password(password)
    assert hashed1 != hashed2
    assert verify_password(password, hashed1)
    assert verify_password(password, hashed2)
