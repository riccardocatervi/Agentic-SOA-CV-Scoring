class ServiceError(Exception):
    """An expected failure: bad input, missing file, unreadable CV.

    The gateway turns it into a tool error whose message the model can read,
    so keep messages short and say what to do differently.
    """
