"""Start the gateway: `python -m cvscore.mcp_server`."""

import logging
from urllib.parse import urlparse

from cvscore.config import get_service_settings
from cvscore.mcp_server.server import mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    url = urlparse(get_service_settings().mcp_gateway_url)
    mcp.run(
        "streamable-http",
        host=url.hostname or "127.0.0.1",
        port=url.port or 8765,
        streamable_http_path=url.path or "/mcp",
    )


if __name__ == "__main__":
    main()
