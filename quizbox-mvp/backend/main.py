from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .network import local_ipv4_addresses


@asynccontextmanager
async def lifespan(app: FastAPI):
    addresses = local_ipv4_addresses()
    app.state.advertised_ips = addresses
    if addresses:
        for address in addresses:
            print(f"QuizBox доступен в локальной сети: http://{address}:8000")
        print("IP-адреса определены автоматически.")
    else:
        print("Локальный IPv4 не обнаружен; HTTP-сервер всё равно запускается.")
    yield


app = FastAPI(
    title="QuizBox local HTTP server",
    description="Локальный HTTP API и автоматическое определение IPv4-адреса устройства.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "QuizBox local server", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "quizbox"}


@app.get("/api/network")
async def network_info() -> dict[str, Any]:
    addresses = getattr(app.state, "advertised_ips", [])
    return {
        "addresses": addresses,
        "port": 8000,
        "base_urls": [f"http://{address}:8000" for address in addresses],
        "source": "auto",
    }
