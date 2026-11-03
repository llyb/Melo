import pytest

from app.obsidian import validate_path, validate_url


@pytest.mark.parametrize("path", ["../secret.md", "/secret.md", "C:/x.md", ".obsidian/x.md", "x/../y.md", "x.txt", "x\\y.md"])
def test_note_paths_cannot_escape_vault(path):
    with pytest.raises(ValueError):
        validate_path(path)


def test_local_https_and_unicode_paths():
    assert validate_path("笔记/测试.md") == "笔记/测试.md"
    validate_url("https://127.0.0.1:27124/mcp/")
    with pytest.raises(ValueError):
        validate_url("https://example.com/mcp/")
