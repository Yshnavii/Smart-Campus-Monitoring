import re


def slugify(name):
    """'Library Reading Hall' -> 'library-reading-hall'. Safe for file names and URLs."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "camera"