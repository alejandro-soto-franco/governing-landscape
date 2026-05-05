import governing_landscape as gl


def test_version():
    assert isinstance(gl.__version__, str)
    assert gl.__version__.count(".") == 2
