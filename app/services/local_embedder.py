#Real implementation + asyncio.to_thread cause local models are CPU work
import re
import hashlib
import math
import asyncio
from app.services.base_embedder import BaseEmbedder
from app.exceptions import EmbedderDimMismatchError
from fastembed import TextEmbedding
#fastembed specialized engine which converts plain text into a list of numbers.

#model_name=the name of the AI model has to use

class LocalEmbedder(BaseEmbedder):
    def __init__(self,model_name:str="BAAI/bge-small-en",expected_dim_size:int=384): #setup code that runs once when your machine is turned on.
        self.expected_dim_size=expected_dim_size

        self.model=TextEmbedding(model_name=model_name)
    def _embed_sync(self,texts:list[str],is_query:bool):#leading _ indicates internal helper function
        
            if is_query:#uses special question formatting
                embeddings_generator=self.model.query_embed(texts)
            else:#uses document storage formatting
                embeddings_generator=self.model.passage_embed(texts)
            #generator:if we give an AI many docs at once it will crash my computers RAM,instead of giving it everything at once we give it one by one,streams the data safely.
            vectors=[]
            #actual computation happens when we iterate over the generator
            for vector in embeddings_generator:#looks at the conveyor belt(generator) and pulls off a item from Fastembeds stream and names it vector
                # vector_list=list(vector),vector is a numpy array(highly compact,machine-code style list of numbers),pythons std web utils cant read directly
                vector_list=[float(x) for x in vector]#convert numpys float to std python float type,Note:not necessary can use one above too.
                #convert it into a list(from raw machine code style list of nos to a std python list)
                if len(vector_list)!=self.expected_dim_size:
                    raise EmbedderDimMismatchError(f"Model has generated a vector length:{len(vector_list)} but we require length:{self.expected_dim_size}")
    
                vectors.append(vector_list)
    
            return vectors
    async def embed_documents(self,texts:list[str],is_query:bool)->list[list[float]]:#a worker fn it expects a list of strings and a T/F is_query, and returns a list containing a list of decimal pt numbers. 
        if not texts:#if you pass empty list with no text in it, it returns []
            return []
        #ran in asyncio.to_thread bcz CPU matrix math is heavy load
        vectors=await asyncio.to_thread(self._embed_sync,texts=texts,is_query=is_query)
        return vectors


class FakeEmbedder(BaseEmbedder):
    def __init__(self,expected_dim_size:int=384):
        self.expected_dim_size=expected_dim_size
        self.batch_sizes=[]

    async def embed_documents(self,texts:list[str],is_query:bool)->list[list[float]]:
        self.batch_sizes.append(len(texts))

        if not texts:
            return []

        vectors=[]
        for  text in texts:
            vec=[0.0]*self.expected_dim_size
            for word in re.findall(r"[a-z]+",text.lower()):
                h=int(hashlib.md5(word.encode()).hexdigest(),16)
                vec[h%self.expected_dim_size]+= 1.0 if (h>>8) & 1 else -1.0
            norm=math.sqrt(sum(x*x for x in vec)) or 1.0
            vectors.append([x/norm for x in vec])

        return vectors

class FailingEmbedder(BaseEmbedder):#for tests
    async def embed_documents(self,texts:list[str],is_query:bool=False):
        raise RuntimeError("OOPS") #this will mimic and embedder failure and should give "error" with no chunks

class WrongDimEmbedder(BaseEmbedder):#for tests again
    async def embed_documents(self,texts:list[str],is_query:bool=False):
        return [[0.1]*381 for _ in texts]
    