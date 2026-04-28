"""Smoke tests for main.py — verifies the module is importable and
run_server() can be called without starting a real server.

These tests use sys.modules tricks to prevent the module-level side effects
(ServiceRegistry(), create_app(), load_dotenv()) from hitting the real
registry / database / filesystem during the test run.
"""

from __future__ import annotations

from unittest.mock import patch

from ..mocks import import_main_fresh as _import_main_fresh


class TestMainImportable:
    """B-L1: main.py is importable without side effects."""

    def test_import_does_not_raise(self) -> None:
        """Importing ``main`` does not raise when its side effects are patched."""
        _import_main_fresh()  # should not raise

    def test_module_exposes_run_server(self) -> None:
        """``main`` exposes a callable ``run_server``."""
        main = _import_main_fresh()

        assert callable(main.run_server)

    def test_module_exposes_app(self) -> None:
        """``main`` exposes a non-None ``app`` object."""
        main = _import_main_fresh()

        assert main.app is not None

    def test_run_server_calls_uvicorn_run(self) -> None:
        """``run_server`` calls ``uvicorn.run`` once with ``"main:app"`` as the target."""
        main = _import_main_fresh()

        with patch("uvicorn.run") as mock_run:
            main.run_server()

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == "main:app"

    def test_run_server_does_not_start_real_server(self) -> None:
        """``run_server`` returns immediately when ``uvicorn.run`` is patched out."""
        main = _import_main_fresh()

        with patch("uvicorn.run"):
            # If uvicorn.run were real, this would block indefinitely.
            main.run_server()
