import asyncio
import json
import os
from app.db import get_sql_engine
from app.models import Base
from app.mcp_server import validate_sql, run_sql_query, get_db_schema, ask_database

async def run_tests():
    print("=== Starting Tests ===")
    
    # 1. Test database schema setup and creation
    print("\n1. Initializing and creating database tables...")
    engine = get_sql_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables initialized successfully.")
    
    # 2. Seed database if empty (simulating main.py lifespan behavior for tests)
    print("\n2. Seeding database...")
    from app.main import lifespan
    from fastapi import FastAPI
    app = FastAPI()
    async with lifespan(app):
        # Lifespan will auto-create and seed tables
        print("FastAPI lifespan run completed (initialization + seeding done).")
        
        # 3. Verify Database Schema Retrieval
        print("\n3. Testing Database Schema Resource...")
        schema = await get_db_schema()
        print("Schema retrieved:")
        print(schema)
        assert "clients" in schema
        assert "projects" in schema
        assert "milestones" in schema
        assert "invoices" in schema
        print("Schema resource test passed.")
        
        # 4. Test SQL Validation (Security check)
        print("\n4. Testing SQL Query Validation (Security Check)...")
        # Valid SQLs
        valid_queries = [
            "SELECT * FROM clients;",
            "SELECT name, status FROM projects WHERE budget > 20000",
            "WITH overdue_inv AS (SELECT * FROM invoices WHERE status != 'paid' AND due_date < date('now')) SELECT * FROM overdue_inv"
        ]
        for q in valid_queries:
            try:
                validate_sql(q)
                print(f"  [PASS] Allowed: '{q}'")
            except Exception as e:
                print(f"  [FAIL] Disallowed valid query: '{q}'. Error: {e}")
                assert False
                
        # Invalid SQLs
        invalid_queries = [
            "INSERT INTO clients (name) VALUES ('Hacker')",
            "DELETE FROM projects WHERE id = 1",
            "DROP TABLE invoices",
            "UPDATE milestones SET status = 'completed'",
            "SELECT * FROM clients; DROP TABLE projects;",
            "CREATE TABLE temp_table (id INT)",
            "SELECT name FROM projects; -- INSERT INTO clients",
        ]
        for q in invalid_queries:
            try:
                validate_sql(q)
                print(f"  [FAIL] Allowed invalid query: '{q}'")
                assert False
            except ValueError as e:
                print(f"  [PASS] Blocked: '{q}'. Reason: {e}")
                
        # 5. Test executing SQL Queries
        print("\n5. Testing SQL Query Execution Tool...")
        # Query 1: Acme project status
        acme_sql = "SELECT status FROM projects WHERE name LIKE '%Acme%';"
        res_acme = await run_sql_query(acme_sql)
        print(f"Acme project status query result:\n{res_acme}")
        acme_data = json.loads(res_acme)
        assert len(acme_data) > 0
        assert any(d.get("status") == "active" for d in acme_data)
        
        # Query 2: Overdue invoices
        overdue_sql = "SELECT i.id, p.name AS project_name, i.amount, i.due_date FROM invoices i JOIN projects p ON i.project_id = p.id WHERE i.status != 'paid' AND i.due_date < date('now');"
        res_overdue = await run_sql_query(overdue_sql)
        print(f"Overdue invoices query result:\n{res_overdue}")
        overdue_data = json.loads(res_overdue)
        assert len(overdue_data) > 0
        print("SQL execution tool test passed.")
        
        # 6. Test Text-to-SQL (Groq) if API key is present
        print("\n6. Testing Natural Language text-to-SQL Tool using Groq...")
        from app.config import settings
        api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("Skipping text-to-SQL Groq LLM integration test (no API key set).")
        else:
            print("API Key found. Querying text-to-SQL tool...")
            # Question 1: What is the status of the Acme Corp project?
            res1 = await ask_database("What is the status of the Acme Corp project?")
            print(f"Question: 'What is the status of the Acme Corp project?'\nResponse:\n{res1}")
            data1 = json.loads(res1)
            assert "results" in data1
            assert "generated_sql" in data1
            
            # Question 2: Which invoices are overdue?
            res2 = await ask_database("Which invoices are overdue?")
            print(f"Question: 'Which invoices are overdue?'\nResponse:\n{res2}")
            data2 = json.loads(res2)
            assert "results" in data2
            assert "generated_sql" in data2
            
            print("Text-to-SQL tool test passed.")
            
    print("\n=== All Tests Passed Successfully ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
