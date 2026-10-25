import uuid


def new_id() -> str:
    """Short random id used for videos and jobs (also used as a folder name)."""
    return uuid.uuid4().hex[:12]
