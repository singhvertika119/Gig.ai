"""MCP (Model Context Protocol) server implementation for Gig.ai."""

import json
import os
import re
from datetime import date, datetime
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text
from groq import Groq

from app.config import settings
from app.db import get_sql_engine

# Initialize FastMCP Server
mcp = FastMCP("Gig.ai")

def validate_sql(sql: str) -> None:
    """Validate that the query is read-only and doesn't contain destructive commands."""
    clean_sql = sql.strip().upper()
    
    # 1. Enforce read-only keywords
    if not (clean_sql.startswith("SELECT") or clean_sql.startswith("WITH")):
        raise ValueError("Security violation: Only read-only SELECT or WITH statements are allowed.")
    
    # 2. Ban modifying keywords as discrete tokens to avoid false positives (e.g. column names)
    forbidden_keywords = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", 
        "REPLACE", "PRAGMA", "GRANT", "REVOKE", "EXEC", "EXECUTE", 
        "ATTACH", "DETACH", "RENAME"
    ]
    
    words = re.findall(r'\b[A-Z_]+\b', clean_sql)
    for keyword in forbidden_keywords:
        if keyword in words:
            raise ValueError(f"Security violation: Unauthorized keyword '{keyword}' found in query.")

async def get_db_schema() -> str:
    """Fetch all SQLite table definitions from the database."""
    engine = get_sql_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        )
        schemas = [row[0] for row in result.all() if row[0]]
        return "\n\n".join(schemas)

async def run_sql_query(sql_query: str) -> str:
    """Validate, run, and serialize the results of a SQL query."""
    validate_sql(sql_query)
    
    engine = get_sql_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql_query))
        keys = list(result.keys())
        rows = [dict(zip(keys, row)) for row in result.all()]
        
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError("Type %s not serializable" % type(obj))
            
        return json.dumps(rows, default=json_serial, indent=2)

async def generate_sql_from_question(question: str) -> str:
    """Translate natural language to SQLite query using Groq."""
    schema = await get_db_schema()
    
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY settings or environment variables not set. "
            "Please configure the key to use the natural language query tool, "
            "or use the direct sql execution tool with the schema resource."
        )
    
    client = Groq(api_key=api_key)
    
    prompt = f"""You are an expert SQLite SQL assistant. Your task is to translate the user's natural language question into a valid SQLite SELECT query based on the database schema provided.

Database Schema:
{schema}

Instructions:
1. Output ONLY the raw SQL query. Do not wrap the SQL query in markdown blocks (e.g. no ```sql), do not write any explanations or metadata.
2. The query must be a read-only SELECT or WITH statement.
3. Compare dates correctly: dates are stored as ISO-8601 strings (YYYY-MM-DD) or DATETIMEs in SQLite. You can use standard string comparison or functions like `date('now')` to check dates.
For example, to find overdue invoices, you can check where `status != 'paid'` and `due_date < date('now')`.
4. Status values are saved in lowercase in the database (e.g. 'active', 'completed', 'planning', 'sent', 'paid', 'overdue'). Always query status values in lowercase.
5. Return a query that handles the question accurately.

Question: {question}
SQL:"""

    model = settings.groq_model or "llama-3.3-70b-versatile"
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    
    sql = response.choices[0].message.content.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```(?:sql)?\n", "", sql)
        sql = re.sub(r"\n```$", "", sql)
        sql = sql.strip()
        
    return sql

@mcp.resource("schema://database")
async def get_database_schema() -> str:
    """Get the SQLite database schema details (DDL statements) to write queries."""
    return await get_db_schema()

@mcp.tool()
async def execute_sql(sql_query: str) -> str:
    """
    Execute a read-only SQL query against the SQLite database.
    Only SELECT or WITH statements are allowed.
    """
    try:
        return await run_sql_query(sql_query)
    except Exception as e:
        return f"Error executing SQL: {str(e)}"

@mcp.tool()
async def ask_database(question: str) -> str:
    """
    Query the database using a natural language question.
    Converts the question to SQL using Gemini, validates it, executes it, and returns results.
    Example: 'What is the status of the Acme Corp project?' or 'Which invoices are overdue?'
    """
    try:
        sql = await generate_sql_from_question(question)
        results = await run_sql_query(sql)
        return json.dumps({
            "generated_sql": sql,
            "results": json.loads(results)
        }, indent=2)
    except Exception as e:
        return f"Error querying database: {str(e)}"

async def summarize_results_nl(question: str, sql_query: str, results_json: str) -> str:
    """Compile a natural language answer based on the query and SQL results using Groq."""
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return f"Database Results: {results_json} (Add GROQ_API_KEY to get natural language summaries)"
        
    client = Groq(api_key=api_key)
    
    prompt = f"""You are a helpful, professional database assistant for Gig.ai.
The user asked a question, and we executed a secure SQL query to fetch the relevant data.
Based on the question, the SQL query, and the query results, generate a concise, human-friendly, and professional natural language answer.

User Question: {question}
SQL Query Executed: {sql_query}
Query Results (JSON format):
{results_json}

Instructions:
1. Provide a direct, natural language answer.
2. Avoid showing raw SQL code or raw JSON blocks to the user unless they explicitly asked for details.
3. Keep the tone professional, helpful, and concise.
4. If no rows were returned, explain that politely (e.g., "There are currently no overdue invoices in the database.").
5. Make sure numeric values like budgets, amounts, and dates are formatted cleanly for reading.

Natural Language Answer:"""

    model = settings.groq_model or "llama-3.3-70b-versatile"
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    
    return response.choices[0].message.content.strip()

@mcp.tool()
async def ask_database_nl(question: str) -> str:
    """
    Query the database using a natural language question and return a JSON structure with a natural language answer and the generated SQL query.
    Converts the question to SQL using Groq, validates it, executes it, and translates the raw results into a natural language summary.
    Example: 'How much budget do I have pending in Planning status?'
    """
    try:
        sql = await generate_sql_from_question(question)
        results = await run_sql_query(sql)
        answer = await summarize_results_nl(question, sql, results)
        return json.dumps({
            "answer": answer,
            "generated_sql": sql
        })
    except Exception as e:
        return json.dumps({
            "answer": f"Error querying database: {str(e)}",
            "generated_sql": None
        })

@mcp.tool()
def ping() -> str:
    """Health probe for MCP tooling."""
    return "pong"

if __name__ == "__main__":
    mcp.run()

