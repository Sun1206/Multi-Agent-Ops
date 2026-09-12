from app.main import create_app


def test_first_slice_exposes_existing_frontend_paths() -> None:
    app = create_app(initialize_database=False)
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/auth/login/"]
    assert "post" in paths["/api/auth/logout/"]
    assert "get" in paths["/api/auth/me/"]
    assert "post" in paths["/api/auth/sync/"]
    assert {"get", "put", "patch"} <= set(paths["/api/module-settings/"])
