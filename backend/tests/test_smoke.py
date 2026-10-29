import cvscore


def test_package_is_importable():
    assert cvscore.__file__ is not None
