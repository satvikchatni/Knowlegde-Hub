import asyncio
import json

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

        cr = await client.post(
            f"/workspaces/{workspace_id}/conversations",
            headers=headers,
            json={"title": "manual streaming test"},
        )
        cr.raise_for_status()

        convo_id = cr.json()["id"]
        print("Conversation created:", convo_id)

        files = {"file": ("omg.txt", b"this is soo tiring", "text/plain")}
        dr = await client.post(
            f"/workspaces/{workspace_id}/documents", files=files, headers=headers
        )

        dr.raise_for_status()
        print("document uploaded")
        document_id = dr.json()["id"]
        while True:
            ds = await client.get(
                f"/workspaces/{workspace_id}/documents/{document_id}", headers=headers
            )
            ds.raise_for_status()
            status = ds.json()["status"]

            if status == "done":
                break
            if status == "error":
                raise RuntimeError("doc processing failed")

            await asyncio.sleep(2)  # checks every 2secs until processing finishes
        print("doc processing completed")
        print("starting stream...")

        async with client.stream(
            "POST",
            f"/workspaces/{workspace_id}/conversations/{convo_id}/stream",
            headers=headers,
            json={"question": "what does uploaded doc say?"},
        ) as response:
            response.raise_for_status()
            print("connected to stream")

            async for line in response.aiter_lines():
                print("RAW:", repr(line), flush=True)
                if line.startswith("event:"):
                    event_type = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    data = json.loads(line.removeprefix("data:").strip())

                    if event_type == "token":
                        print(data["text"], end="", flush=True)
                    elif event_type == "error":
                        print("\nError:", data)


if __name__ == "__main__":
    asyncio.run(main())
