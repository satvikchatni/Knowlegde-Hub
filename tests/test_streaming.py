# transport buffers the entire response, the test client may receive the complete res only after the stream finishes
# we cant use ASGI to ptove that our events arrived at a particular time, or that cancellation works correctly
# need a diff testing approach


async def post_question(client, workspace_id, conversation_id, question, headers):
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        headers=headers,
        json={"question": question},
    )
    assert res.status_code == 200
    return list(parse_sse(res.text.splitlines()))  # returns (event,data) pairs


# yield makes this a generator produces events one at a time, instead of returning a complete list.
def parse_sse(lines):
    event, data = "message", []

    for line in lines:
        if line == "":  # empty line marks the send of a SSE event
            if data:  # checks whether there is data
                yield (
                    event,
                    "\n".join(data),
                )  # returns the event name and the data wo ending the generator
            event, data = "message", []  # resets both variables so the next SSE can be processed
        elif line.startswith(":"):
            continue  # lines beginning with : are normally SSE comments, so skip them using continue moving to next iteration
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
