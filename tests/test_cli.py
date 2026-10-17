import json

from moses.cli import main


def test_offline_user_journey(tmp_path, capsys):
    args = ["--warehouse", str(tmp_path / "warehouse")]
    assert main(args + ["init"]) == 0
    capsys.readouterr()
    assert main(args + ["demo"]) == 0
    version = json.loads(capsys.readouterr().out)["version"]
    assert main(args + ["query", "SELECT count(*) AS n FROM places"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"n": 2}]
    assert main(args + ["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == version
    lock = tmp_path / "inputs.json"
    assert main(args + ["lock", str(lock)]) == 0
    capsys.readouterr()
    assert json.loads(lock.read_text()) == {"places": version}
    assert main(args + ["query", "SELECT count(*) AS n FROM places", "--lock", str(lock)]) == 0
    assert json.loads(capsys.readouterr().out) == [{"n": 2}]
    output = tmp_path / "export.parquet"
    assert main(args + ["export", "places", str(output), "--version", version]) == 0
    capsys.readouterr()
    assert output.exists()
    assert main(args + ["export", "places", str(output)]) == 1
    assert "already exists" in capsys.readouterr().err


def test_cli_invalid_file_nonzero(tmp_path, capsys):
    assert main(["-w", str(tmp_path / "warehouse"), "load", "missing.geojson", "--name", "places"]) == 1
    assert "moses:" in capsys.readouterr().err


def test_local_workflow_without_network(tmp_path, monkeypatch, capsys):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("Local workflow attempted a Python network connection")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    args = ["-w", str(tmp_path / "warehouse")]
    assert main(args + ["demo"]) == 0
    capsys.readouterr()
    assert main(args + ["query", "SELECT count(*) AS n FROM places"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"n": 2}]
