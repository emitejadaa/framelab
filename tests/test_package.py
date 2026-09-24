import framelab


def test_version_is_pep440_dev_string():
    assert framelab.__version__ == "0.0.1.dev0"
