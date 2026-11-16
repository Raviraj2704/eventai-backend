def detect_image_type(data: bytes) -> str | None:
    """Return the real image type from the file's bytes, or None if it isn't JPEG, PNG, or WEBP."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None