"""Run with: python -B -m app.main"""
import argparse
import os

import uvicorn

from app.api import create_app


def main():
    parser = argparse.ArgumentParser(description="Excel batch runner server")
    parser.add_argument("--port", type=int, default=int(os.getenv("BATCH_PORT", "8866")))
    parser.add_argument("--host", default=os.getenv("BATCH_HOST", "127.0.0.1"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False, workers=1)


if __name__ == "__main__":
    main()
