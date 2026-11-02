def chunk_text(text:str,size:int,overlap:int)->list[str]:
    if size<=0:
        raise ValueError("chunk size must be positive")
    if not 0<=overlap<size:
        raise ValueError("overlap must be atleast zero and strictly smaller than size")
    text=text.strip()
    if not text:
        return []
    step=size-overlap
    chunks=[]
    start=0
    while start<len(text):
        chunks.append(text[start:start+size])
        if start+size>=len(text):
            break
        start+=step
    return chunks

