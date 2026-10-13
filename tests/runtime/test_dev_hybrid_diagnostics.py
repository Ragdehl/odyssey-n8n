"""DEV-only exception breadcrumbs never expose exception values to logs."""

from odyssey_runtime.server import _log_dev_hybrid_error_category


def _raise_secret() -> None:
    raise ValueError("TEST_SECRET_MUST_NOT_APPEAR")


def test_bounded_hybrid_log_is_dev_only_and_never_logs_exception_message(
    monkeypatch, capsys
) -> None:
    try:
        _raise_secret()
    except ValueError as error:
        monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
        monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", "1")
        _log_dev_hybrid_error_category(error)
        assert capsys.readouterr().err == ""

        monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
        monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", "0")
        _log_dev_hybrid_error_category(error)
        assert capsys.readouterr().err == ""

        monkeypatch.setenv("ODYSSEY_HYBRID_DEV_ENABLED", "1")
        _log_dev_hybrid_error_category(error)
        marker = capsys.readouterr().err
        assert "odyssey_dev_hybrid_exception" in marker
        assert "ValueError" in marker
        assert "TEST_SECRET_MUST_NOT_APPEAR" not in marker
        assert "_raise_secret" in marker
