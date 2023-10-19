# FastAPI forwarder

FastAPI endpoint, which forwards all incoming requests to other destinations
in the same format in background.

# Installation

Clone this repository:

```bash
git clone
```

Build and run the container:

```bash
docker compose -f docker-compose.example.yml up --build
```

Send a POST, PUT or GET request to `http://localhost:8000/forward`, e.g.

```bash
curl -v -X POST "http://127.0.0.1:8000/forward?qp=fast&x-api-key=abcdef1234567890abcdef1234567890abcdef12" -H "Content-Type: application/json" -d '{"foo": 42}'
```

# Configuration

Copy example configuration file:

```bash
cp forward/example_config.json forward/config.json
cp docker-compose.yml docker-compose.dev.yml
```

Modify `forward/config.json` and `docker-compose.dev.yml` to suit your needs.

Run container with modified configuration:

```bash
docker compose -f docker-compose.dev.yml up --build
```
