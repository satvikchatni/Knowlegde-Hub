from pathlib import Path

EVAL_DOCS=Path(__file__).resolve().parent.parent/"evaluation_docs" #__file__:current script's loc, .resolve():converts it into absolute path,.parent: scripts .parent.parent: project root, /"evaluation_docs": eval docs folder

pdf_files=list(EVAL_DOCS.glob("**.pdf")) # glob("**.pdf"): finds all files ending with .pdf inside "evaluation_docs"
print(pdf_files)




golden_dataset=[
    {
        "question":"Who founded Aravind Eye Hospital, and what motivated him to establish it?",
        "target_document":"Case-2 Eye Care.pdf",
        "target_pages":[1,2,3]
    },
    {
        "question":"How is Aravind's Eye Hospital healthcare different from a conventional hospitals?",
        "target_document":"Case-2 Eye Care.pdf",
        "target_pages":[3,4,5,6,12]
    },
    {
        "question":"What impact has Aravind's hospital had on society?",
        "target_document":"Case-2 Eye Care.pdf",
        "target_pages":[7,8,9]
    },
    {
        "question":"What are the attributes of MenuItem class?",
        "target_document":"Coffee+Machine+Classes+Documentation.pdf",
        "target_pages":[1]
    },
    {
        "question":"What does report() method of MoneyMachine Class do?",
        "target_document":"Coffee+Machine+Classes+Documentation.pdf",
        "target_pages":[2]
    },
    {
        "question":"Which method checks whether or not there are enough ingredients to make a drink?",
        "target_document":"Coffee+Machine+Classes+Documentation.pdf",
        "target_pages":[1]
    },
]


import asyncio

import httpx2

BASE_URL = "http://127.0.0.1:8000"


async def main():
    async with httpx2.AsyncClient(base_url=BASE_URL, timeout=None) as client:
        # register_res = await client.post(
        #     "/auth/register", json={"email": "maria@example.com", "password": "my-password"}
        # )
        # register_res.raise_for_status()
        response = await client.post(
            "/auth/login", data={"username": "maria@example.com", "password": "my-password"}
        )
        response.raise_for_status()  # catches login failures
        access_token = response.json()["access_token"]
        print("logged in sucessfully!")

        headers = {"Authorization": f"Bearer {access_token}"}

        wsr = await client.post("/workspaces", json={"name": "ws-name"}, headers=headers)
        wsr.raise_for_status()

        workspace_id = wsr.json()["id"]
        document_ids={}
        for pdf_path in pdf_files:
            with pdf_path.open("rb") as pdf:
                byte_content=pdf.read()
                files={"file":(pdf_path.name,byte_content,"application/pdf")}


        
            dr = await client.post(
                f"/workspaces/{workspace_id}/documents", files=files, headers=headers
            )
            dr.raise_for_status()
            print("document uploaded")
            document_id = dr.json()["id"]
            print("uploaded doc id:",document_id)
            document_ids[pdf_path.name]=document_id
            while True:
                ds = await client.get(
                    f"/workspaces/{workspace_id}/documents/{document_id}", headers=headers
                )
                ds.raise_for_status()
                status = ds.json()["status"]
                print("Current status:",status)

                if status == "done":
                    
                    break
                if status == "error":
                    raise RuntimeError("doc processing failed")

                await asyncio.sleep(2) 
            print("doc processing completed")
        hits=0
        misses=0
        for item in golden_dataset:
            response=await client.get(f"/workspaces/{workspace_id}/search",params={"q":item["question"],"limit":5},headers=headers) #recall@k, where k=5

            response.raise_for_status()
            results=response.json()

            hit=any(result["filename"]==item["target_document"] and result["page_number"] in item["target_pages"] for result in results)
            if hit:
                hits+=1
            else:
                misses+=1

            if not hit:
                print("missed question:",item["question"])
                for res in results:
                    print(
                        res["filename"],
                        res["score"],
                        res["page_number"],
                        res["text"][:300]
                    )
                
        print("Hits:",hits)
        print("Misses:",misses)
        print(f"Hit Rate@5:{hits/len(golden_dataset):.2%}") # : tells python that what follows is a format specifier, .2% displays it as a percentage with 2 decimal places 




   

if __name__ == "__main__":
    asyncio.run(main())