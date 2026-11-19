
from arq.connections import ArqRedis
import logging
import json

logger=logging.getLogger("progress")

#status provides what stage of ingestion we're currently at (reading,chunking,embedding,done)
#detail provides extra information, such as 1/2 for embedding batches
# message=f"""Doc id:-{document_id} #JSON is easier to  parse
#             Progress:-{status}:{detail}
#                               """
async def publish_progress(channel:str,document_id:str,status:str,detail:str,client:ArqRedis): #client(connection to redis) is the redis client, client gives helper ability to send the status update while channel tells Redis where to send that message  
    try:
        message={
            "document_id":document_id,
            "status":status,
            "detail":detail,
        }
        await client.publish(channel,json.dumps(message)) #json.dumps() converts python dict into a JSON string, websocket endpoint has to convert it back to python dict using json.loads()
    except Exception as e: #a redis hiccup must never fail ingestion, just log the error don't re-raise it.
        logger.warning(f"ran into error:{str(e)} while progress update",exc_info=True) #to include exception traceback easier for debugging
