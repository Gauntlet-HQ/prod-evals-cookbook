"""
SQL agent for querying business metrics.

Converts natural language questions to SQL and executes against PostgreSQL.
"""

from typing import Any

import psycopg2
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import chat_model, settings


# Database schema for the LLM
SCHEMA_DESCRIPTION = """
Available tables in the Acme Corp analytics database:

1. customers
   - id (int, primary key)
   - name (varchar) - company name
   - domain (varchar) - company domain
   - plan_tier (varchar) - 'free', 'starter', 'professional', 'enterprise'
   - industry (varchar)
   - employee_count (int)
   - signup_date (date)
   - status (varchar) - 'active', 'churned', 'trial'
   - mrr (decimal) - monthly recurring revenue
   - region (varchar)

2. monthly_revenue
   - month (date) - first day of month
   - mrr (decimal) - total MRR
   - new_mrr (decimal) - new business MRR
   - expansion_mrr (decimal) - expansion MRR
   - contraction_mrr (decimal) - contraction MRR
   - churned_mrr (decimal) - churned MRR
   - customer_count (int)

3. support_tickets
   - id (int, primary key)
   - customer_id (int, foreign key)
   - created_at (timestamp)
   - resolved_at (timestamp)
   - category (varchar) - 'Technical', 'Billing', 'Account', 'Feature Request'
   - priority (varchar) - 'P1', 'P2', 'P3', 'P4'
   - status (varchar) - 'open', 'in_progress', 'resolved', 'closed'
   - subject (varchar)
   - csat_score (int) - 1-5 rating
   - first_response_minutes (int)
   - resolution_minutes (int)

4. refunds
   - id (int, primary key)
   - customer_id (int, foreign key)
   - amount (decimal)
   - reason (varchar)
   - processed_at (timestamp)
   - approved_by (varchar)
   - quarter (varchar) - e.g., '2024-Q4'

5. employees
   - id (int, primary key)
   - name (varchar)
   - email (varchar)
   - department (varchar)
   - role (varchar)
   - start_date (date)
   - manager_id (int, foreign key)
   - status (varchar)

Helpful views:
- v_active_customers_by_tier: customer_count, total_mrr, avg_mrr by plan_tier
- v_refunds_by_quarter: refund_count, total_amount, avg_amount by quarter
"""


SQL_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL expert. Convert the user's question into a PostgreSQL query.

{schema}

Rules:
1. Only generate SELECT queries (no INSERT, UPDATE, DELETE)
2. Use appropriate aggregations (COUNT, SUM, AVG) when asked for totals or averages
3. Use proper date filtering for time-based questions
4. Limit results to 20 rows unless asked for more
5. Return ONLY the SQL query, no explanations

Current date context: January 2025 (Q4 2024 just ended)
"""),
    ("human", "{question}"),
])


def get_postgres_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )


def generate_sql(question: str) -> str:
    """Generate SQL from natural language question."""
    llm = chat_model()
    
    chain = SQL_GENERATION_PROMPT | llm | StrOutputParser()
    
    sql = chain.invoke({
        "schema": SCHEMA_DESCRIPTION,
        "question": question,
    })
    
    # Clean up the SQL (remove markdown code blocks if present)
    sql = sql.strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[1]  # Remove first line
    if sql.endswith("```"):
        sql = sql.rsplit("```", 1)[0]  # Remove last part
    sql = sql.strip()
    
    return sql


def execute_sql(sql: str) -> list[dict[str, Any]]:
    """Execute SQL query and return results."""
    conn = get_postgres_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        results = [dict(zip(columns, row)) for row in rows]
        return results
    finally:
        cursor.close()
        conn.close()


@tool
def sql_query(question: str) -> str:
    """
    Query business metrics and analytics data from the Acme Corp database.
    
    Use this tool for questions about:
    - Customer counts and segments
    - Revenue metrics (MRR, growth, churn)
    - Support ticket statistics
    - Refund data
    - Employee information
    
    Args:
        question: A natural language question about business metrics
        
    Returns:
        Query results with the generated SQL for transparency
    """
    try:
        # Generate SQL
        sql = generate_sql(question)
        
        # Execute query
        results = execute_sql(sql)
        
        # Format response (plain text, no markdown)
        if not results:
            return f"Query executed successfully but returned no results.\n\nSQL: {sql}"
        
        # Format results as plain text table
        output_lines = [f"SQL Query:\n{sql}\n", "Results:\n"]
        
        # Create simple text table
        if results:
            headers = list(results[0].keys())
            
            # Calculate column widths
            col_widths = {h: len(h) for h in headers}
            for row in results[:20]:
                for h in headers:
                    val_len = len(str(row.get(h, "NULL")))
                    col_widths[h] = max(col_widths[h], val_len)
            
            # Header row
            header_row = "  ".join(h.ljust(col_widths[h]) for h in headers)
            output_lines.append(header_row)
            output_lines.append("-" * len(header_row))
            
            # Data rows
            for row in results[:20]:
                values = [str(v) if v is not None else "NULL" for v in row.values()]
                row_str = "  ".join(v.ljust(col_widths[h]) for v, h in zip(values, headers))
                output_lines.append(row_str)
            
            if len(results) > 20:
                output_lines.append(f"\n({len(results) - 20} more rows not shown)")
        
        return "\n".join(output_lines)
        
    except Exception as e:
        return f"Error executing query: {str(e)}"


# For direct testing
if __name__ == "__main__":
    test_questions = [
        "How many active customers do we have?",
        "What's our current MRR?",
        "How many refunds were processed in Q4 2024?",
    ]
    
    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print("="*60)
        result = sql_query.invoke({"question": question})
        print(result)
