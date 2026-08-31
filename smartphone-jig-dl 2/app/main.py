import logging
import sys

import uvicorn

from api.server import create_app
from core.config import CONFIG_FILE, load_or_exit

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

config = load_or_exit(CONFIG_FILE)
app = create_app(config, CONFIG_FILE)

if __name__ == "__main__":
    logging.info("=" * 50)
    logging.info(f" SERVIDOR ENDPOINT INICIADO EM {config.host}:{config.port} - Aguardando ordens...")
    logging.info("=" * 50)
    uvicorn.run(app, host=config.host, port=config.port, log_config=None)
