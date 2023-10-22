
import contextlib

@contextlib.contextmanager
def raises_in_groups(exc):
    try:
        yield
    except* exc:
        pass
    else:
        raise AssertionError("Did not raise expected exception")
