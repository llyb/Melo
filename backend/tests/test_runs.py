from app.sessions import SessionCatalog


def test_accept_persists_input_and_atomic_title_does_not_lose_head(tmp_path):
    store = SessionCatalog(tmp_path / "catalog.sqlite3")
    session = store.create()
    store.accept_run(session["id"], "run1", 0, "draft")
    reopened = SessionCatalog(tmp_path / "catalog.sqlite3")
    assert reopened.input("run1") == "draft"
    old = reopened.get(session["id"])
    reopened.rename(session["id"], "manual")
    old["head_checkpoint_id"] = "checkpoint"
    reopened.save(old)
    assert reopened.get(session["id"])["title"] == "manual"
