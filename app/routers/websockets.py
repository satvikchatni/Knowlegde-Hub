from fastapi import APIRouter
import uuid
from fastapi import WebSocket
import asyncio
from app.security import decode_access_token
import jwt
from app.db import SessionFactory
from app.models import Membership, Document
from sqlalchemy import select
from arq.connections import ArqRedis
import json
import logging


router = APIRouter(prefix="/ws", tags=["websockets"])

logger=logging.getLogger("ws")

#two concurrent(run simultaneously) tasks
async def wait_for_disconnect(websocket:WebSocket):
    while True:
        message=await websocket.receive()
        if message["type"]=="websocket.disconnect": #if the client disconnects ,it returns 
            return 

async def relay_loop(pubsub,websocket:WebSocket):
        #relay loop
        while True:
            message=await pubsub.get_message(ignore_subscribe_messages=True,timeout=1.0)
            if message is not None:
                data=json.loads(message["data"])
                await websocket.send_json(data)

@router.websocket("/workspaces/{workspace_id}/progress")
async def progress(workspace_id:uuid.UUID,websocket:WebSocket,session_factory:SessionFactory):
    await websocket.accept() #browser sends websocket handshake request, FastAPI accepts it using websocket.accept()
    pubsub=None
    try:
        try:
            token = await asyncio.wait_for(websocket.receive_text(),timeout=5.0) #server waits up to 5s
        except TimeoutError:#no token received
            await websocket.close(code =1008) #1008:policy violation,the client didn't follow server's rules
            return
        user_id= decode_access_token(token)
        async with session_factory() as db_session:
            membership=(await db_session.execute(select(Membership).where(Membership.workspace_id==workspace_id,Membership.user_id==user_id))).scalar_one_or_none()
            if membership is None:
                await websocket.close(code=1008)
                return
            documents=(await db_session.execute(select(Document).where(Document.workspace_id==workspace_id))).scalars().all()
        
        list_of_channel_names=[]
        for document in documents:
            list_of_channel_names.append(f"document:{document.id}:progress")
        r:ArqRedis=websocket.app.state.redis_pool

        if r is None: #check if the redis pool exists
            await websocket.close(code=1011)
            return


        pubsub=r.pubsub()
        for channel in list_of_channel_names:
            await pubsub.subscribe(channel)
        count=0
        while True:
            if len(list_of_channel_names)==0: #if no documents
                break
            message=await pubsub.get_message(timeout=5)

            if message is None:
                
                raise TimeoutError("Redis never confirmed the subscription")
            if message["type"]=="subscribe":
                count+=1
            if count==len(list_of_channel_names):
                break       
        snapshots=[] #the current status even if some progress happened before it
        async with session_factory() as  db_session: #snapshot
            docs=(await db_session.execute(select(Document).where(Document.workspace_id==workspace_id))).scalars().all()
            for doc in docs:
                snapshots.append({"document_id":str(doc.id),"status":doc.status,"error_message":doc.error_message})
        await websocket.send_json({"event":"snapshot","documents":snapshots}) #sends snapshots to the browser, sends the data as JSON so the front end can parse it easily, initial snapshots
        #task1 listens to redis status updates
        #task2 listens to browser disconnecting
        tasks={
            asyncio.create_task(relay_loop(pubsub,websocket)),
            asyncio.create_task(wait_for_disconnect(websocket))
        }
        #waits until atleast task completes
        #done contains the task that is completed, pending the task which is still running
        done,pending=await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

        await asyncio.gather(*pending,return_exceptions=True) #waits for the pending task to cancelled

        #t.cancelled() checks whether a task was cancelled or nor
        for t in done:
            if  not t.cancelled() and t.exception() is not None: #check not t.cancelled() cause a task in done could have finished through cancellation rather than noormal completion
                logger.error("websocket task failed:%s",t.exception())
                await websocket.close(code=1011) # 1011= server errors
    except jwt.InvalidTokenError:
        await websocket.close(code=1008) #1008 policy violation, invalid token received
    except TimeoutError:
        logger.exception("Redis timed out")
        await websocket.close(code=1011)

    finally: #resource cleanup
        if pubsub is not None:
            await pubsub.unsubscribe(*list_of_channel_names) #unsubscribes from all the doc channels
            await pubsub.aclose() #closes the pub/sub connection




    




    