import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated


from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteException


from app.config import settings
from app.db import engine, get_db,SessionLocal
from app.exceptions import AppError
from app.routers import auth, documents, websockets, workspaces,usage
from app.services.local_embedder import LocalEmbedder
from app.services.local_llm import FakeLLM, GeminiLLM
from app.logging_config import setup_logging
from app.middleware import RequestIDMiddleware

# a normal context manager would be with open("exmaple.txt") as f: it opens the file,you work with it and python closes it automatically.
# @asynccontexrmanager is a decorator from contextlib which allows you to write asynchronous context managers using async and yield.

setup_logging()

logger = logging.getLogger("app")

# logger.info("logging initialized")


@asynccontextmanager  # everything before yield is setup,after yield is cleanup and yield marks the point where the appln can run.
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.llm_backend == "gemini":
        app.state.llm = GeminiLLM()
    elif settings.llm_backend == "fake":
        app.state.llm = FakeLLM()
    app.state.embedder = await asyncio.to_thread(
        LocalEmbedder
    )  # model loading can involve expensive sync work

    app.state.redis_pool = None
    try:
        app.state.redis_pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url)
        )  # dsn-data source name
    except (RedisConnectionError, RedisTimeoutError):
        logger.warning("Redis is unavailable rn, queue operations will be disabled")
    yield
    if app.state.redis_pool is not None:
        await app.state.redis_pool.aclose()

    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(websockets.router)
app.include_router(usage.router)

app.add_middleware(RequestIDMiddleware)

@app.exception_handler(AppError)
async def app_error_handler(
    request: Request, exc: AppError
):  # request is mandatory even if we don't use it
    return JSONResponse(
        content={"error_code": exc.code, "message": exc.message},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(StarletteException)
async def http_error_handler(request: Request, exc: StarletteException):
    return JSONResponse(
        content={"error_code": f"http_{exc.status_code}", "message": str(exc.detail)},
        status_code=exc.status_code,
        headers=exc.headers,
    )  # if "http_404" you know Starlette/FastAPI blocked it, if "not_found" you know pythong logic blocked it.


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(
                str(part) for part in err["loc"]
            ),  # which input field on user interface cause the problem, ex:  body.password
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        content={
            "error_code": "validation_error",
            "message": "The request is invalid.",
            "details": details,
        },
        status_code=422,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    request_id=request.state.request_id
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )  # replaces first one with HTTP method like POST, and second one with the URL Path /auth/login.
    return JSONResponse(
        content={"error_code": "internal_error", "message": "Something went wrong"}, status_code=500, headers={
            "X-Request-ID":request_id
        }
    )


# logger.exception(...) writes top-secret,highly technical details to your backend server logs while hiding them completely from the user.


@app.get("/",summary="root endpoint")
def read_root():
    return {"message": "Hello, World!"}


@app.get("/health",summary="liveness check")
def health_check():
    return {"status": "healthy"}


# @app.get("/health/db")
# async def health_check_db(db: Annotated[AsyncSession, Depends(get_db)]):
#     await db.execute(text("SELECT 1"))
#     return {"database": "ok"}

CHECK_TIMEOUT=5
async def _run(name:str,function):
    try:
        await asyncio.wait_for(function(),CHECK_TIMEOUT)

        return name, 'ok'
    except TimeoutError:
        return name, 'timeout'
    except Exception as e:

        logger.warning('rediness check %s failed: %r',name,e) #%r formats the exception e using repr(e)
        return name, 'error'

async def check_db():
    async with SessionLocal() as db:
        await db.execute(text("SELECT 1"))

async def check_redis():
    redis=app.state.redis_pool
    if redis is None:
        raise RuntimeError("Redis pool in unavailable")
    await redis.ping()


CHECKS={
    "db":check_db,"redis":check_redis
}

@app.get("/ready",summary="readiness check")
async def ready():

    results=dict(
        await asyncio.gather(
            *[_run(n,f) for n,f in CHECKS.items()]
        )
    )

    ok=all(v=='ok' for v in results.values())
    failing=[k for k,v in results.items() if v!="ok"]
    return JSONResponse(
        {
            "status":"ready" if ok else "not_ready",
            "failing":failing
        },
        status_code=200 if ok else 503
    )

