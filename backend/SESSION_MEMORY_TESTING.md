Session memory verification snippets

Use one UUID per browser tab/session:

```bash
SESSION_ID="11111111-1111-1111-1111-111111111111"
```

Allowed profile setup:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"My name is Rohan. Remember this.\"}"
```

Allowed and stored:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"My dog's name is Tommy. Remember this.\"}"
```

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"My dog is scared of fireworks. Remember this.\"}"
```

Out-of-scope refusal:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"message\":\"Write a Java program\"}"
```

Check what was stored:

```bash
docker compose exec db psql -U nanu -d nanu -c \
"SELECT role, content, created_at FROM chat_messages WHERE session_id='$SESSION_ID' ORDER BY created_at ASC;"
```

Session expiry simulation:

```bash
docker compose exec db psql -U nanu -d nanu -c \
"UPDATE chat_messages SET created_at = now() - interval '25 hours' WHERE session_id='$SESSION_ID';"
```

Then call `/chat` with the same `session_id`. Expected response:

`Your session has been expired. Please consider refreshing the window for a new session`
