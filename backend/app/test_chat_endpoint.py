import asyncio
import os
from httpx import AsyncClient, ASGITransport
from app.main import app, lifespan
from app.config import settings

async def run_chat_tests():
    print("=== Starting Chat Endpoint Tests ===")
    
    # Verify API key is present
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Skipping chat integration tests because GROQ_API_KEY is not set.")
        return

    # Use the app lifespan context manager to initialize the database
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            
            # Test 1: Simple query about Acme project status
            print("\nTest 1: Asking 'What is the status of the Acme Portal Integration project?'")
            payload = {"message": "What is the status of the Acme Portal Integration project?"}
            response = await client.post("/api/chat", json=payload)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "generated_sql" in data
            assert "active" in data["answer"].lower() or "active" in data["generated_sql"].lower()
            print("Test 1 Passed.")
            
            # Test 2: Query about pending/planning budget
            print("\nTest 2: Asking 'How much budget do I have pending in Planning status?'")
            payload = {"message": "How much budget do I have pending in Planning status?"}
            response = await client.post("/api/chat", json=payload)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "15" in data["answer"] or "15,000" in data["answer"] or "planning" in data["generated_sql"].lower()
            print("Test 2 Passed.")
            
            # Test 3: Query with empty message (should error)
            print("\nTest 3: Asking empty message")
            payload = {"message": ""}
            response = await client.post("/api/chat", json=payload)
            print(f"Status Code: {response.status_code}")
            assert response.status_code == 400
            print("Test 3 Passed.")

    print("\n=== All Chat Endpoint Tests Passed ===")

if __name__ == "__main__":
    asyncio.run(run_chat_tests())
