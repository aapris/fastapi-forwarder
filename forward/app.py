import asyncio
import datetime
import json
import logging
import os
import time

import httpx
from fastapi import FastAPI, Request
from starlette import status
from starlette.exceptions import HTTPException

from async_database import get_db_engine, StarletteRequest

# Load configuration from a JSON file
with open(os.getenv("CONFIG_FILE"), "r") as config_file:
    config = json.load(config_file)

# Set logging level and format with timestamp
logging.basicConfig(format="%(asctime)s %(levelname)-8s %(message)s", level=getattr(logging, config["LOG_LEVEL"]))
logging.info("==============================================================================")
logging.info("Starting forwarder with logging level {}".format(config["LOG_LEVEL"]))

# List of destinations to forward the requests to, extracted from the config
destinations = [destination["url"] for destination in config["DESTINATIONS"]]
logging.info(f"Destinations: {destinations}")

app = FastAPI()
client = httpx.AsyncClient()
db_engine = None


def check_api_key(request: Request):
    """
    Check that the request has a valid API key in params or headers.
    """
    api_key = request.query_params.get("x-api-key")
    if api_key is None:
        api_key = request.headers.get("x-api-key")
    if api_key is None or api_key != config["X-API-KEY"]:
        logging.warning("Missing or invalid authentication token (x-api-key)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token (x-api-key)",
        )
    return True


@app.on_event("startup")
async def startup_event():
    """
    Initialize the database engine.
    """
    global db_engine
    db_url = config.get("SQLALCHEMY_DATABASE_URL", "")
    logging.info(f"Starting up, getting db engine: {db_url}")
    if db_url != "":
        db_engine = await get_db_engine(config["SQLALCHEMY_DATABASE_URL"])


async def write_request_to_db(request):
    """
    Write the request to the database, if configured.
    """
    if db_engine is None:  # noqa
        return
    async with db_engine.begin() as conn:  # noqa
        await conn.execute(
            StarletteRequest.insert(),
            [
                {
                    "time": datetime.datetime.now(datetime.timezone.utc),
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "params": dict(request.query_params),
                    "body": await request.body(),
                    "remote_ip": request.client.host,
                }
            ],
        )
    await db_engine.dispose()  # noqa


@app.get("/")
async def root():
    return {"message": "HTTP OK"}


async def forward_to_destination(method: str, url: str, body: bytes, headers: dict, params: dict):
    start_time = time.time()
    response = await client.request(method, url, content=body, headers=headers, params=params)
    total_time = time.time() - start_time
    logging.info(f"Response {response.status_code} in {total_time:0.3f}s from: {response.request.url}")
    logging.debug(f"{response.text}")


@app.api_route("/forward", methods=["GET", "POST", "PUT"])
async def forward_request(request: Request):
    """
    Forward the request to all destinations. Modify the request as needed.
    Store the request to the database, if configured.
    """
    asyncio.create_task(write_request_to_db(request))
    check_api_key(request)  # raises HTTPException if not ok
    body = await request.body()  # Will be sent as-is
    headers = dict(request.headers)  # Will be modified as needed
    for h in ["x-api-key", "host"]:  # Remove host header, otherwise httpx will use it as the host
        if h in headers:
            del headers[h]
    params = dict(request.query_params)
    if "x-api-key" in params:
        del params["x-api-key"]
    for url in destinations:
        asyncio.create_task(forward_to_destination(request.method, url, body, headers, params))
    return {"message": "Request forwarded to destinations"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
