async def upload_file(upload_client,filename,content,workspace_id):
    files={"file":(filename,content,"text/plain")}
    result=await upload_client.post(f"/{workspace_id}/documents",files=files)
    return result

async def test_txt_file_upload(upload_client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    workspace=await make_workspace(workspace_name="testws",headers=owner['headers'])
    workspace_id=workspace.id
    response=await upload_file(upload_client,filename="test.txt",content=b"content",workspace_id=workspace_id)
    assert response.status_code==202