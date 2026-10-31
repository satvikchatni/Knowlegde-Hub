from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI,Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteException

from app.db import engine, get_db
from app.routers import auth, workspaces
from app.exceptions import AppError

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(workspaces.router)

@app.exception_handler(AppError)
async def app_error_handler(request:Request,exc:AppError):#request is mandatory even if we don't use it
    return  JSONResponse(content={"error_code":exc.code,"message":exc.message},status_code=exc.status_code,headers=exc.headers)

@app.exception_handler(StarletteException)
async def http_error_handler(request:Request,exc:StarletteException):
    return JSONResponse(content={"error_code":f"http_{exc.status_code}","message":str(exc.detail)},status_code=exc.status_code,headers=exc.headers)# if "http_404" you know Starlette/FastAPI blocked it, if "not_found" you know pythong logic blocked it.

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request:Request,exc:RequestValidationError):
    details=[
        {
            "field":".".join(str(part) for part in err["loc"]), #which input field on user interface cause the problem, ex:  body.password
            "message":err["msg"]
        }for err in exc.errors()
    ]
    return JSONResponse(
        content={
            "error_code":"validation_error",
            "message":"The request is invalid.",
            "details":details
        },
        status_code=422
    )

@app.exception_handler(Exception)
async def unexpected_error_handler(request:Request,exc:Exception):
    logger.exception("Unhandled error on %s %s",request.method,request.url.path)#replaces first one with HTTP method like POST, and second one with the URL Path /auth/login.
    return JSONResponse(content={
        "error_code":"internal_error",
        "message":"Something went wrong"
    },
    status_code=500)
#logger.exception(...) writes top-secret,highly technical details to your backend server logs while hiding them completely from the user.

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/health/db")
async def health_check_db(db: Annotated[AsyncSession, Depends(get_db)]):
    await db.execute(text("SELECT 1"))
    return {"database": "ok"}
