from typing import Optional


MAX_PASSWORD_LENGTH = 1024


def password_validation_error(
    password: object, minimum_length: int
) -> Optional[str]:
    if not isinstance(password, str):
        return "Password must be a string"
    if len(password) < minimum_length:
        return f"Password must be at least {minimum_length} characters long"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must not exceed {MAX_PASSWORD_LENGTH} characters"
    return None
