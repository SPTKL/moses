from moses.cli import main


def test_serve_missing_token_fails_without_creating_warehouse(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MOSES_TOKEN", raising=False)
    root = tmp_path / "absent"
    assert main(["-w", str(root), "serve"]) == 1
    assert "bearer token" in capsys.readouterr().err
    assert not root.exists()


def test_serve_uses_loopback_and_environment_token_then_closes(tmp_path, monkeypatch, capsys):
    from moses import service

    calls = {}
    token = "test-secret-never-print-this"
    monkeypatch.setenv("MOSES_TEST_SESSION", token)

    class Server:
        server_port = 8123

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls["closed"] = True

        def serve_forever(self):
            raise KeyboardInterrupt

    def create(root, supplied_token, **kwargs):
        calls.update(root=root, token=supplied_token, **kwargs)
        return Server()

    monkeypatch.setattr(service, "create_server", create)
    root = str(tmp_path / "warehouse")
    assert main(["-w", root, "serve", "--port", "0", "--token-env", "MOSES_TEST_SESSION"]) == 0
    assert calls == {"root": root, "token": token, "host": "127.0.0.1", "port": 0, "closed": True}
    output = capsys.readouterr()
    assert "http://127.0.0.1:8123/v1" in output.out
    assert token not in output.out + output.err
