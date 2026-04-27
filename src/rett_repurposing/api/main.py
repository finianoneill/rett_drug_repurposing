"""FastAPI app factory.

Registered routes live in `routes.py`. CORS is permissive for `localhost:3000`
because that is where the Next.js dev server runs in host-mode workflows; in
the Docker Compose path the browser only ever talks to the frontend container,
so CORS is moot.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rett_repurposing.api.routes import router
from rett_repurposing.logging import configure_logging

configure_logging()

app = FastAPI(title="Rett Repurposing API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
