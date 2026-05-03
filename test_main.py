import pytest
from httpx import AsyncClient
from main import app, SESSIONS, STATS, CACHE, CHAT_CACHE
import time
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "BallotAxis"

@pytest.mark.asyncio
async def test_get_timeline():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/timeline")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 10
    for item in data:
        assert "phase" in item
        assert "timing" in item
        assert "description" in item
        assert "icon" in item
        assert "key_actions" in item
    # Test chronological order (implied by the list order in implementation)
    assert data[0]["phase"] == "Election Announcement"
    assert data[6]["phase"] == "Polling Day"

@pytest.mark.asyncio
async def test_get_checklist():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/checklist")
    assert response.status_code == 200
    data = response.json()
    assert "steps" in data
    assert len(data["steps"]) == 10
    for i, step in enumerate(data["steps"]):
        assert step["id"] == i + 1
        assert "title" in step
        assert "description" in step
        assert "icon" in step

@pytest.mark.asyncio
async def test_get_quiz_question():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/quiz/question")
    assert response.status_code == 200
    data = response.json()
    assert "question" in data
    assert "options" in data
    assert "correct" in data
    assert "explanation" in data
    assert "topic" in data
    assert len(data["options"]) == 4
    assert data["correct"] in ["A", "B", "C", "D"]

@pytest.mark.asyncio
async def test_get_quiz_question_topics():
    topics = ["registration", "process", "rights", "history", "evm"]
    async with AsyncClient(app=app, base_url="http://test") as ac:
        for topic in topics:
            response = await ac.get(f"/api/v1/quiz/question?topic={topic}")
            assert response.status_code == 200
            data = response.json()
            # If the topic filter worked, it should return a question with that topic 
            # (though the mock logic might be flexible)
            # In our main.py, it should match if possible.
            assert "question" in data

@pytest.mark.asyncio
async def test_get_facts():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/facts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 10
    assert all(isinstance(f, str) for f in data)

@pytest.mark.asyncio
async def test_post_chat_valid():
    payload = {"message": "Hello", "session_id": "test_session_1", "hindi_mode": False}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "suggestions" in data
    assert data["response"] == "Test response from AI"

@pytest.mark.asyncio
async def test_post_chat_validation_errors():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Empty message
        resp = await ac.post("/api/v1/chat", json={"message": "", "session_id": "s1"})
        assert resp.status_code == 422 # Pydantic min_length=1
        
        # Too long message
        resp = await ac.post("/api/v1/chat", json={"message": "a"*2001, "session_id": "s1"})
        assert resp.status_code == 422 # Pydantic max_length=2000
        
        # Missing session_id
        resp = await ac.post("/api/v1/chat", json={"message": "hello"})
        assert resp.status_code == 422

@pytest.mark.asyncio
async def test_post_chat_sanitization():
    payload = {"message": "Hello <script>alert(1)</script>", "session_id": "test_session_2"}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # We can't easily see the internal call to Gemini here without more mocks,
        # but we can verify it doesn't crash and returns 200.
        # The validator should have cleaned the message.
        response = await ac.post("/api/v1/chat", json=payload)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_rate_limiting():
    # Clear rate limit state
    from main import ip_requests
    ip_requests.clear()
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Send 20 requests
        for _ in range(20):
            await ac.get("/health")
        # 21st should fail
        response = await ac.get("/health")
        assert response.status_code == 429

@pytest.mark.asyncio
async def test_cors_headers():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert "access-control-allow-origin" in response.headers

@pytest.mark.asyncio
async def test_session_isolation():
    SESSIONS.clear()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Session 1
        await ac.post("/api/v1/chat", json={"message": "Msg 1", "session_id": "s1"})
        # Session 2
        await ac.post("/api/v1/chat", json={"message": "Msg 2", "session_id": "s2"})
        
    assert len(SESSIONS["s1"]) == 2 # user + model
    assert len(SESSIONS["s2"]) == 2
    assert SESSIONS["s1"][0]["content"] == "Msg 1"
    assert SESSIONS["s2"][0]["content"] == "Msg 2"

@pytest.mark.asyncio
async def test_chat_deduplication():
    CHAT_CACHE.clear()
    payload = {"message": "Repeat", "session_id": "s_repeat"}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # First call
        resp1 = await ac.post("/api/v1/chat", json=payload)
        assert resp1.headers.get("X-Cache") == "MISS"
        
        # Immediate second call
        resp2 = await ac.post("/api/v1/chat", json=payload)
        assert resp2.headers.get("X-Cache") == "HIT"

@pytest.mark.asyncio
async def test_stats_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_sessions" in data
    assert "total_messages" in data
    assert "uptime_seconds" in data
    assert "cache_hits" in data
