from app.services.base_embedder import BaseEmbedder
import hashlib
from app.config import settings
import numpy as np
from redis.exceptions import RedisError
import logging
import asyncio

logger=logging.getLogger("cached_embedder")
class CachedEmbedder(BaseEmbedder):
    def __init__(self,inner,redis,ttl):
        self.inner=inner #the existing embedder
        self.redis=redis #redis conn
        self.ttl=ttl #Time To live: expiration time of the cached embedding
        self.in_flight={} #single-flight,20 same requests at one time,embed one and return the res to other 19. asyncio.Future():the first req creates a Future,it generates a embedding and puts the res into Future, so other requests await that same future and receive the res
        
        #only one coroutine can access the section of code at a time
        self.lock=asyncio.Lock() #need asyncio.Lock to protect in_flight dict cause many requests can access it in concurrently, don't want thos reqs to modify it


    async def embed_documents(self,texts:list[str],is_query:bool=False):
        if not texts:
            return []
        if not is_query: #is_query=False
            return await self.inner.embed_documents(texts=texts,is_query=is_query)

        #before single-flight,below code was valid
        # results=[None]*len(texts)
        # misses=[]
        # for i,text in enumerate(texts):
        #     normalized=" ".join(text.split()) #"  HOW  WAS UR DAY? "becomes "HOW WAS UR DAY?"
        #     key=f"{settings.embedding_model}:{is_query}:{normalized}"
        #     #.encode() converts it into bytes, hexdigest() converts it into readable hexadecimal string
        #     hashed_key=hashlib.sha256(key.encode()).hexdigest() #hashing it so redis keys stays short no matter how long the query is
                    
        #     cache_key=f"embedding:{hashed_key}"
        #     try:
        #         cached=await self.redis.get(cache_key)
        #     except RedisError:
        #         cached=None
        #     if cached:
        #         vector=np.frombuffer(cached,dtype=np.float32).tolist()#cause redis returns bytes,np.frombuffer() reads the bytes as float32 numbers, .tolist() converts the np array into a regular python list                
        #         results[i]=vector
        #     else: #if not in redis(not cached)
        #         misses.append((i,text,cache_key))
        # if misses:
        #     missing_texts=[miss[1] for miss in misses]
        #     vectors=await self.inner.embed_documents(texts=missing_texts,is_query=is_query)

        #     for miss,vec in zip(misses,vectors):

        #         results[miss[0]]=vec #put vec into results at pos i
        #         value=np.asarray(vec,dtype=np.float32).tobytes() #dtype stands for data type, converting to bytes so redis can store it
        #         try:
        #             await self.redis.set(miss[2],value,ex=self.ttl) #miss[2]=cache_key, storing generated embedding in redis with expiration time(ex)
        #         except RedisError:
        #             logger.warning("Redis is unavailable, not able to store embeddings")

        # return results

        return await asyncio.gather(*(self._embed_one(text=text) for text in texts))
    async def _embed_one(self,text:str)->list[float]:
            normalized=" ".join(text.split()) #"  HOW  WAS UR DAY? "becomes "HOW WAS UR DAY?"
            key=f"{settings.embedding_model}:True:{normalized}" #only handles query embeddings is_query=True
            #.encode() converts it into bytes, hexdigest() converts it into readable hexadecimal string
            hashed_key=hashlib.sha256(key.encode()).hexdigest() #hashing it so redis keys stays short no matter how long the query is
                    
            cache_key=f"embedding:{hashed_key}"
            try:
                cached=await self.redis.get(cache_key)
            except RedisError:
                cached=None
            if cached:
                vector=np.frombuffer(cached,dtype=np.float32).tolist()#cause redis returns bytes,np.frombuffer() reads the bytes as float32 numbers, .tolist() converts the np array into a regular python list                
                return vector
            else: #if not in redis(not cached)
                async with self.lock: #prevents 2 reqs from checking the dict and creating a task
                    task=self.in_flight.get(cache_key)

                    if task is None: #other req is not generating the embedding, this req becomes responsible for gnerating the embedding
                        task=asyncio.create_task(
                            self._do_embedding(text=normalized,cache_key=cache_key)
                        )
                        self.in_flight[cache_key]=task
                return await asyncio.shield(task) #prevents cancellation of one waiting request from cancelling the shared task,  the other requests can still receieve the embedding

                    
    async def _do_embedding(self,text:str,cache_key):
        try:
            vectors=await self.inner.embed_documents(texts=[text],is_query=True)
            value=np.asarray(vectors[0],dtype=np.float32).tobytes()
            try:
                await self.redis.set(cache_key,value,ex=self.ttl)
            except RedisError:
                logger.warning("Redis is unavailable, not able to store embeddings")

            return vectors[0]
        finally:
            async with self.lock:
                if self.in_flight.get(cache_key) is asyncio.current_task():
                    del self.in_flight[cache_key] #remove the task after it finishes


                
        









