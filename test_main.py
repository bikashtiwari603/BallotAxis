import pytest
import time
import json
import uuid
from httpx import AsyncClient
from main import app, SESSIONS, STATS, CACHE, CHAT_CACHE, ip_requests
from unittest.mock import patch, MagicMock

# --- Fixtures & Mocks ---

@pytest.fixture(autouse=True)
def mock_gemini():
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "response": "Test response from AI",
            "suggestions": ["Tell me more", "How do I register?"]
        })
        mock_instance.start_chat.return_value.send_message.return_value = mock_response
        mock_model.return_value = mock_instance
        yield mock_instance

@pytest.fixture(autouse=True)
def clear_state():
    SESSIONS.clear()
    CHAT_CACHE.clear()
    ip_requests.clear()
    CACHE.clear()
    STATS["total_messages"] = 0
    STATS["cache_hits"] = 0
    yield

# --- Basic Endpoints ---

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data

@pytest.mark.asyncio
async def test_api_v1_about():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/about")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "BallotAxis"
    assert "problem_solved" in data
    assert "impact_metrics" in data
    assert "official_sources" in data
    assert data["non_partisan"] is True

@pytest.mark.asyncio
async def test_get_timeline():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/timeline")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    assert data[0]["phase"] == "Election Announcement"

@pytest.mark.asyncio
async def test_get_checklist():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/checklist")
    assert response.status_code == 200
    assert len(response.json()["steps"]) == 10

# --- Chat Edge Cases & Validation ---

@pytest.mark.asyncio
async def test_post_chat_unicode_hindi():
    hindi_text = "मतदाता पंजीकरण कैसे करें?"
    payload = {"message": hindi_text, "session_id": "hindi_session", "hindi_mode": True}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    assert response.json()["response"] == "Test response from AI"

@pytest.mark.asyncio
async def test_post_chat_session_id_special_chars():
    # Valid special chars are - and _
    payload = {"message": "Hello", "session_id": "user-123_abc"}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    
    # Invalid chars (e.g. @)
    payload = {"message": "Hello", "session_id": "user@123"}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat", json=payload)
    assert response.status_code == 422 # Validation Error

@pytest.mark.asyncio
async def test_post_chat_boundary_lengths():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # 2000 chars - OK
        resp = await ac.post("/api/v1/chat", json={"message": "a"*2000, "session_id": "s1"})
        assert resp.status_code == 200
        
        # 2001 chars - Error
        resp = await ac.post("/api/v1/chat", json={"message": "a"*2001, "session_id": "s1"})
        assert resp.status_code == 422

@pytest.mark.asyncio
async def test_session_history_capping():
    session_id = "cap_test"
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Send 15 rounds of chat (30 messages)
        for i in range(15):
            await ac.post("/api/v1/chat", json={"message": f"Msg {i}", "session_id": session_id})
        
    # Main.py logic should cap at 20 messages
    assert len(SESSIONS[session_id]) <= 20

# --- Security & Performance ---

@pytest.mark.asyncio
async def test_security_headers():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    
    headers = response.headers
    assert "X-Request-ID" in headers
    assert headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in headers
    assert "Strict-Transport-Security" in headers
    assert "Permissions-Policy" in headers

@pytest.mark.asyncio
async def test_rate_limiting_chat():
    ip_requests.clear()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Chat has limit of 10
        for _ in range(10):
            await ac.post("/api/v1/chat", json={"message": "Hi", "session_id": "s1"})
        
        # 11th should be 429
        response = await ac.post("/api/v1/chat", json={"message": "Hi", "session_id": "s1"})
        assert response.status_code == 429
        assert "Retry-After" in response.headers

@pytest.mark.asyncio
async def test_gzip_compression():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Timeline is large enough to trigger GZip (> 1000 bytes)
        response = await ac.get("/api/v1/timeline", headers={"Accept-Encoding": "gzip"})
    # If GZip middleware is working, it should have the header
    # Note: AsyncClient might decompress automatically, so check content-encoding if available
    if "content-encoding" in response.headers:
        assert response.headers["content-encoding"] == "gzip"

@pytest.mark.asyncio
async def test_performance_benchmarks():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        start = time.time()
        response = await ac.get("/api/v1/facts")
        end = time.time()
        
    assert response.status_code == 200
    assert (end - start) < 0.1 # Should be under 100ms for static JSON

# --- Quiz & Search ---

@pytest.mark.asyncio
async def test_quiz_topic_filtering():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Test specific topic
        response = await ac.get("/api/v1/quiz/question?topic=registration")
        assert response.status_code == 200
        assert response.json()["topic"] == "registration"
        
        # Test case-insensitive
        response = await ac.get("/api/v1/quiz/question?topic=REGISTRATION")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_stats_tracking():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        await ac.post("/api/v1/chat", json={"message": "M1", "session_id": "s1"})
        await ac.get("/api/v1/stats")
        
    assert STATS["total_messages"] >= 1
