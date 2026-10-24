"""Start the API on the port assigned by the hosting platform."""

import os

import uvicorn


def main():
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        timeout_graceful_shutdown=15,
    )


if __name__ == "__main__":
    main()
