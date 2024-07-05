import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict

import httpx
import structlog
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from starlette.responses import Response


# Configuration models


class ForwardTarget(BaseModel):
    url: HttpUrl
    extra_headers: Dict[str, str] = {}
    extra_params: Dict[str, str] = {}


class PathConfig(BaseModel):
    original_app_url: ForwardTarget
    forward_urls: List[ForwardTarget]


class ProxyConfig(BaseModel):
    paths: Dict[str, PathConfig]
    log_file: str = "request_response_log.jsonl"
    forward_timeout: float = 5.0  # Default timeout for forward requests in seconds


# Initialize structured logger
logger = structlog.get_logger()

# Global config and HTTP client
config: ProxyConfig = None
client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global config, client
    # Load configuration from JSON file
    config_filename = os.getenv("CONFIG_FILE", "proxy_config.json")
    with open(config_filename) as config_file:
        config_data = json.load(config_file)
    config = ProxyConfig(**config_data)
    client = httpx.AsyncClient()

    yield

    # Shutdown
    await client.aclose()


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)


async def log_request(request: Request):
    body = await request.body()
    # Try to decode the body as UTF-8, if it fails replace with a placeholder
    try:
        body = body.decode("utf-8")
    except UnicodeDecodeError:
        body = "<binary data>"
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "request",
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "body": body,
    }
    write_log(log_entry)


async def log_response(url: str, response: httpx.Response, execution_time: float):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "response",
        "service": str(url),
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text,
        "execution_time": execution_time,
    }
    write_log(log_entry)


def write_log(log_entry: dict):
    # add %Y%m%d to the log file name to create a new log file every day
    log_file = config.log_file.replace(".jsonl", f"_{datetime.utcnow().strftime('%Y%m%d')}.jsonl")
    with open(log_file, "a") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")


async def send_request(dest_url: ForwardTarget, method: str, headers: dict, body: bytes):
    start_time = time.time()
    url = str(dest_url.url)
    try:
        response = await client.request(method, url, content=body, headers=headers, timeout=config.forward_timeout)
        execution_time = time.time() - start_time
        await log_response(url, response, execution_time)
    except Exception as e:
        logger.error(f"Failed to forward request to {url}", exc_info=e)


async def forward_requests(forward_urls: List[ForwardTarget], method: str, headers: dict, body: bytes):
    tasks = [send_request(url, method, headers, body) for url in forward_urls]
    await asyncio.gather(*tasks)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"])
async def proxy(request: Request, background_tasks: BackgroundTasks):
    # If request contains query parameter `test`, return a test response
    if "test" in request.query_params and request.query_params["test"] == "1":
        return Response(content="Test OK", status_code=200)
    path = request.url.path
    path_config = next((config.paths[k] for k in config.paths if path.startswith(k)), None)

    if not path_config:
        return Response(status_code=404)  # Not Found if no matching path configuration

    await log_request(request)

    # Forward to original app
    body = await request.body()
    headers = dict(request.headers)
    method = request.method

    start_time = time.time()
    try:
        url = path_config.original_app_url.url
        original_response = await client.request(
            method, str(url), content=body, headers=headers, timeout=config.forward_timeout
        )
        execution_time = time.time() - start_time
        await log_response(url, original_response, execution_time)
    except Exception as e:
        logger.error(f"Failed to forward request to original app {path_config.original_app_url}", exc_info=e)
        return Response(status_code=502)  # Bad Gateway if original app doesn't respond

    # Schedule forward requests to run in the background
    background_tasks.add_task(forward_requests, path_config.forward_urls, method, headers, body)

    # Return the response from the original app immediately
    return Response(
        content=original_response.content,
        status_code=original_response.status_code,
        headers=dict(original_response.headers),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
