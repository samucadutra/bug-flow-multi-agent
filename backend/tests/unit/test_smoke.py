from importlib.metadata import version


def test_package_imports():
    import bugflow  # noqa: F401


def test_version_matches_metadata():
    import bugflow

    assert bugflow.__version__
    assert bugflow.__version__ == version("bugflow")
