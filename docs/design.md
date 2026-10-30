# Knowledge-Hub

## What it does
It goes through uploaded documents and gives you an answer to your question. Answers will show what document they came from, each team's documents will be made private to that team.

## Who uses it
Individuals or teams who have many documents but not enough time to go through them and find necessary information.

## Smallest useful version
- User signs up and logs in.
- Creates separate workspace for his/her team.
- They upload a document.(Plain text or PDF only)
- Ask a question and receive an apt answer based on uploaded documents.

## Not in the first version
- Uploading pictures.
- A mobile app.

## Data model

### users
- id
- email(must be unique)
- password_hash
- created_at

### refresh_tokens
- id
- user_id (->users)
- family_id (groups every token that came from one login)
- token_hash (SHA-256 of the token, must be unique; the real token is never stored)
- expires_at
- revoked_at (empty until the token is used or revoked)
- created_at

### workspace
- id
- name
- created_at

### membership
- id
- created_at
- role
- workspace_id(->workspaces)
- user_id(->users)
 

### documents
- id
- workspace_id(->workspaces)
- filename
- status
- storage_path
- created_at
- error_message
- content_type
- size_bytes

### chunks
- id
- workspace_id(->workspaces)
- page_number
- text
- position
- document_id(->documents)
- created_at


## Decisions

### 1. ID Style
I choose UUIDs because they can't be guessed.Mistakes during permission checks won't leak another team's data.

### 2. Delete Rule
- delete a user -> their memberships are deleted(cascade), but not allowed if they are the only owner of a workspace.
- delete a workspace -> its chunks, documents and memberships are deleted(cascade); the stored files are deleted by the app.
- delete a document -> its chunks are deleted(cascade).
- Files on disk don't cascade,so the app code must delete those files itself.
- delete a user -> their refresh tokens are deleted (cascade)

### 3. Document Status
Values: uploaded -> reading-> done, or error(with error_message)
Only the app changes the status, not the user.
Retry: only a document with status 'error' can be retried (anything else gives 409 Conflict).
Retrying clears error_message, sets the status back to 'uploaded', and queues processing again.
Needs the editor role; a non-member gets 404.

### 4. Uploads
- Allowed: PDF and plain text (.pdf, .txt), compared case-insensitively. Maximum 10 MB (setting).
- The type is checked from the file's content (a PDF starts with '%PDF-', text must be valid UTF-8),
  never from the client's filename or Content-Type.
- Files are stored as '<upload_dir>/<workspace_id>/<document_id>.<ext>'. The client's filename is
  only stored as a cleaned display name.
- Upload answers 202 (processing comes later). Too large: 413. Wrong or mismatched type: 415.
  Empty file or no file: 422.
- Deleting a document deletes the row first, then the file; a missing file is fine.
- A document is only reachable through its own workspace: a mismatched id gives 404.

### 5. Pagination
Lists use 'limit' (default 20, 1 to 100) and 'offset' (default 0), newest first, optional 'status'
filter. The response is '{items, total, limit, offset}'.

## Roles
owner > editor > viewer. Each role can do anything the lower ones can.

## Tokens
- Access token: a JWT signed with SECRET_KEY, claims 'sub' (user id) and 'exp'. Lives 15 minutes.
  Sent as 'Authorization: Bearer <token>'.
- Refresh token: a random string that lives 7 days. Only its hash is stored, and it is replaced
  every time it is used (rotation).
- Reuse detection: using a refresh token that was already used or revoked ends the whole login
  session, because it may have been stolen.
- Logout revokes the whole login session and always answers 204, even for an unknown token.
- Known limits: an access token that was already issued still works until it expires (at most
  15 minutes), even after logout. Two simultaneous refreshes with the same token count as reuse
  and log the user out.

## Endpoints
| Method | Path | Lowest role | What it does | Status code |
|---|---|---|---|---|
| POST | /auth/register | anyone | creates an account | 201 |
| POST | /auth/login | anyone | checks email and password,returns an access token and a refresh token | 200 |
| GET | /auth/me | logged-in user | returns the current user(id,email,created_at) | 200 |
| POST | /auth/refresh | anyone with a valid refresh token | swaps a refresh token for a new access token and refresh token, old one stops working | 200 |
| POST | /auth/logout | anyone with a refresh token | ends that login session by revoking every refresh token for that login | 204 |
| POST | /workspaces | logged-in user | creates a workspace(creator becomes owner) | 201 |
| GET | /workspaces | logged-in user | lists workspaces user belongs to | 200 |
| GET | /workspaces/{workspace_id} | any member | lists workspace with specific id | 200 |
| POST | /workspaces/{workspace_id}/members | owner | adds members to the workspace | 201 |
| POST | /workspaces/{workspace_id}/documents | editor | uploads a document | 202 |
| GET | /workspaces/{workspace_id}/documents | any member | lists the documents in workspace | 200 |
| GET | /workspaces/{workspace_id}/documents/{document_id} | any member| shows a document and it's status | 200 |
| DELETE | /workspaces/{workspace_id}/documents/{document_id} | editor | deletes a document | 204 |
| POST | /workspaces/{workspace_id}/ask | any member | asks a question | 200 |
| POST | /workspaces/{workspace_id}/documents/{document_id}/retry | editor | runs processing again for a document whose status is 'error' | 202 |

## Errors
| Situation | Code | error | message |
|---|---|---|---|
| Not logged in. | 401 | not_authenticated | Please login first. |
| Member,but role too low. | 403 | forbidden | You don't have permission to do this. |
| Workspace or document doesn't exist. | 404 | not_found | Document/Workspace not found. |
| Request itself is wrong. | 422 | validation_error | Email is required. |
| Conflict: email already registered, user already in the workspace | 409 | conflict | Email already registered. |
| File too large | 413 | file_too_large | file exceeds fixed limit. |
| Wrong or mismatched file type | 415 | unsupported_media_type | Unsupported or mismatched file type. |



Every error looks like: {"error":"not_found","message":"Document/Workspace not found."}
A non-member gets 404, and members get 403 if their role is too low. So, non-members can't learn if a workspace exists or not.
The workspace's responses include the caller's role.
An owner may add another owner.
