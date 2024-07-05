import argparse
import json
import random
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import asyncio

app = FastAPI()

# Argument parser
parser = argparse.ArgumentParser(description="FastAPI logging server")
parser.add_argument("--log-file", type=str, help="Log to a file in JSON lines format with strftime characters")
parser.add_argument("--print", action="store_true", help="Print log in human-readable format to stdout")
parser.add_argument(
    "--delay", nargs="+", type=float, help="Delay response by a fixed time or a random time between a range"
)
parser.add_argument(
    "--keep-body", nargs="?", const=True, type=int, help="Keep the full body or a specified number of bytes in the log"
)
parser.add_argument("--port", type=int, default=8000, help="Port to run the Uvicorn server on")

args = parser.parse_args()


# Logging function
def log_request(request_data, log_file=None, print_log=False):
    timestamp = datetime.utcnow().isoformat() + "Z"
    log_entry = {
        "timestamp": timestamp,
        "method": request_data["method"],
        "url": request_data["url"],
        "path": request_data["path"],
        "headers": request_data["headers"],
        "query_params": request_data["query_params"],
        "body": request_data["body"],
    }

    if log_file:
        formatted_log_file = datetime.utcnow().strftime(log_file)
        with open(formatted_log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    if print_log:
        print(f"Timestamp: {timestamp}")
        print(f"Method: {request_data['method']}")
        print(f"URL: {request_data['url']}")
        print(f"Path: {request_data['path']}")
        print(f"Headers: {json.dumps(request_data['headers'], indent=2)}")
        print(f"Query Params: {json.dumps(request_data['query_params'], indent=2)}")
        print(f"Body: {request_data['body']}")
        print("------")


# Middleware to log requests
@app.middleware("http")
async def log_middleware(request: Request, call_next):
    body = await request.body()
    if args.keep_body is True:
        body_content = body.decode("utf-8")
    elif isinstance(args.keep_body, int) and args.keep_body > 0:
        body_content = body[: args.keep_body].decode("utf-8", errors="ignore")
    else:
        body_content = "[Body logging not enabled]"

    query_params = dict(request.query_params)
    await request.form()

    request_data = {
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "headers": dict(request.headers),
        "query_params": query_params,
        "body": body_content,
    }

    log_request(request_data, log_file=args.log_file, print_log=args.print)

    if args.delay:
        if len(args.delay) == 1:
            await asyncio.sleep(args.delay[0])
        elif len(args.delay) == 2:
            await asyncio.sleep(random.uniform(args.delay[0], args.delay[1]))

    response = await call_next(request)
    return response


@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str):
    timestamp = datetime.utcnow().isoformat() + "Z"
    return JSONResponse(content={"message": "Hello World", "path": request.url.path, "timestamp": timestamp})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port)
