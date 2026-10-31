"""
Start the Research Copilot.

    python run.py

Serves the API and the interface on http://127.0.0.1:8000.
"""

import sys

import uvicorn

from app import config

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    config.ensure_dirs()

    problems = config.missing_config()

    print()
    print("  Research Copilot")
    print(f"  http://{HOST}:{PORT}")
    print()

    if problems:
        # Not fatal. The app starts, /api/health reports the problem, and the
        # interface shows it — which is friendlier than refusing to boot.
        print("  Before you can ask anything:")
        for problem in problems:
            print(f"    - {problem}")
        print()

    print("  Press Ctrl+C to stop.")
    print()
    # stdout is block-buffered when piped, and uvicorn logs to stderr. Flush
    # so the URL is on screen before the server takes over the terminal.
    sys.stdout.flush()

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
