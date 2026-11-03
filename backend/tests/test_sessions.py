import pytest

from app.sessions import SessionCatalog


def test_catalog_reopens_renames_and_deletes_without_message_storage(tmp_path):
    catalog = SessionCatalog(tmp_path / "catalog.sqlite3")
    session = catalog.create()
    catalog.rename(session["id"], "独立会话")
    reopened = SessionCatalog(tmp_path / "catalog.sqlite3")
    assert reopened.get(session["id"])["title"] == "独立会话"
    assert len(reopened.list(50, 0)["items"]) == 1
    reopened.mark_deleting(session["id"])
    assert reopened.list(50, 0)["items"] == []
    reopened.remove(session["id"])
    with pytest.raises(KeyError):
        reopened.get(session["id"])
