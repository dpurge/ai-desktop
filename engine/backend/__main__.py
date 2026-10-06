import argparse
import os
import secrets
import socket
from pathlib import Path

import uvicorn

from backend.app import create_app
from backend.llm.factory import build_llm, current_model_name
from backend.parent_watch import start_from_env as exit_when_parent_dies
from backend.paths import state_dir
from backend.session_store import SessionStore
from backend.settings_service import SettingsService

TOKEN_ENV_VAR = "AD_TOKEN"
LOG_LEVEL_ENV_VAR = "AD_LOG_LEVEL"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend", description="AI Desktop engine")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--gui-dir", type=Path, default=None, help="serve this GUI folder at /")
    return parser.parse_args(argv)


def bind_socket(host: str, port: int) -> socket.socket:
    # Binding here (instead of letting uvicorn do it) lets us report the real port when port is 0.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def main() -> None:
    args = parse_args()
    # Popped so nothing the engine starts later inherits it.
    token = os.environ.pop(TOKEN_ENV_VAR, None)
    is_token_generated = not token
    if is_token_generated:
        token = secrets.token_urlsafe(32)

    sock = bind_socket(args.host, args.port)
    port = sock.getsockname()[1]
    settings = SettingsService(state_dir())
    app = create_app(
        token=token,
        session_store=SessionStore(state_dir()),
        settings=settings,
        model_name=lambda: current_model_name(settings),
        gui_dir=args.gui_dir,
        llm=build_llm(settings),
    )

    print(f"backend listening on http://{args.host}:{port}", flush=True)
    if is_token_generated:
        # Only a self-generated token is printed; one supplied by the launcher is never echoed.
        print(f"open http://{args.host}:{port}/#token={token}", flush=True)

    exit_when_parent_dies()
    log_level = os.environ.get(LOG_LEVEL_ENV_VAR, "warning")
    server = uvicorn.Server(uvicorn.Config(app, log_level=log_level))
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
