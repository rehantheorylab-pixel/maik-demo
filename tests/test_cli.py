"""Phase G tests: the CLI subcommands work end-to-end in stub mode."""
import json
import os

os.environ.setdefault("MAIK_STUB", "1")

from maik_kernel.cli import build_parser, cli


def test_cli_parse_all_subcommands():
    """Every documented subcommand must parse without error."""
    p = build_parser()
    for args in (["solve", "calculate 17 x 23"],
                 ["bench"], ["bench", "--n", "5"], ["bench", "--stub"],
                 ["status"], ["init"], ["flywheel"],
                 ["flywheel", "--revolutions", "2"]):
        ns = p.parse_args(args)
        assert callable(ns.func)


def test_cli_init_creates_encrypted_env(tmp_path, monkeypatch, capsys):
    from maik_kernel import secrets
    monkeypatch.setattr(secrets, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(secrets, "EXAMPLE_PATH", tmp_path / ".env.example")
    (tmp_path / ".env.example").write_text("OPENROUTER_API_KEY=your-key\n# keep=ok\n")
    assert cli(["init"]) == 0
    assert (tmp_path / ".env").exists()
    out = capsys.readouterr().out
    assert "Encrypted .env ready" in out


def test_cli_solve_stub(capsys):
    assert cli(["solve", "calculate 17 x 23"]) == 0
    out = capsys.readouterr().out
    assert "MAIK ANSWER" in out
    # stub provider answers arithmetic exactly
    assert "391" in out


def test_cli_bench_stub(tmp_path, monkeypatch, capsys):
    # isolate bench artifacts in a tempdir via the MAIK_DATA_DIR hook
    monkeypatch.setenv("MAIK_DATA_DIR", str(tmp_path / "data"))
    assert cli(["bench", "--stub", "--n", "4"]) == 0
    out = capsys.readouterr().out
    assert "STUB (offline)" in out
    assert "PASS" in out or "FAIL" in out
    assert "Summary" in out


def test_cli_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAIK_DATA_DIR", str(tmp_path / "data"))
    assert cli(["status"]) == 0
    out = capsys.readouterr().out
    assert "Key hygiene audit" in out
    assert "Pattern library" in out


def test_cli_flywheel_stub(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAIK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "maik_kernel.flywheel.REROUTE_RULES_PATH",
        tmp_path / "rules.json")
    assert cli(["flywheel"]) == 0
    out = capsys.readouterr().out
    assert "Revolution 1" in out
    assert (tmp_path / "rules.json").exists()
