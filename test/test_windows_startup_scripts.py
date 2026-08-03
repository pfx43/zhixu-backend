import json
import os
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def health_server(payload: dict):
    encoded_payload = json.dumps(payload).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded_payload)))
            self.end_headers()
            self.wfile.write(encoded_payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_powershell(script: Path, *arguments: str, environment=None):
    return subprocess.run(
        [
            "pwsh.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script.relative_to(REPOSITORY_ROOT)),
            *arguments,
        ],
        cwd=str(REPOSITORY_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_api_contract_verifier_rejects_missing_onboarding_paths():
    with health_server(
        {"api_contract": {"status": "invalid", "missing_paths": ["/missing"]}}
    ) as port:
        result = run_powershell(
            REPOSITORY_ROOT / "verify_api_contract.ps1",
            "-HealthUrl",
            f"http://127.0.0.1:{port}/health",
            "-TimeoutSeconds",
            "2",
        )

    assert result.returncode != 0
    assert "missing required API paths: /missing" in result.stderr


def test_start_script_rejects_an_already_occupied_port():
    with health_server({"api_contract": {"status": "ok"}}) as port:
        environment = os.environ.copy()
        environment["ZHISHI_BACKEND_PORT"] = str(port)
        environment["ZHISHI_STARTUP_TIMEOUT_SECONDS"] = "2"
        result = run_powershell(
            REPOSITORY_ROOT / "start_server.ps1",
            environment=environment,
        )

    assert result.returncode != 0
    assert "is already in use" in result.stderr
