"""
Ask Acme - LangGraph orchestrator.

Coordinates between vector search, SQL agent, and MCP tools
to answer questions about Acme Corp.
"""

from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import chat_model, settings
from vector_search import vector_search
from sql_agent import sql_query
from mcp_tools import jira_search, slack_search


# All available tools
TOOLS = [vector_search, sql_query, jira_search, slack_search]


# Default system prompt for the agent
DEFAULT_SYSTEM_PROMPT = """You are Ask Acme, an AI assistant that helps employees find information about Acme Corp.

You have access to the following tools:

1. vector_search - Search internal documents (policies, procedures, engineering docs, product info)
   Use for: "What's our PTO policy?", "How do I handle incidents?", "What's on the roadmap?"

2. sql_query - Query business metrics from the analytics database
   Use for: "How many customers?", "What's our MRR?", "How many refunds last quarter?"

3. jira_search - Search Jira tickets for bugs and project work
   Use for: "What P0 bugs are open?", "What's in the current sprint?", "Status of auth issues?"

4. slack_search - Search Slack conversations for discussions and decisions
   Use for: "What did engineering decide about X?", "Any customer feedback on Y?"

Guidelines:
- Use the most appropriate tool(s) for each question
- For questions that span multiple domains, use multiple tools
- Always cite your sources (document names, ticket IDs, channel names)
- If you can't find information, say so honestly
- Be concise but complete in your answers
- Format your response as plain text, NOT markdown. Do not use ** for bold or other markdown syntax.

Current context: January 2025, Acme Corp is a B2B project management company with ~200 employees and 2,400+ customers.
"""


class AgentState(dict):
    """State for the agent graph."""
    messages: Annotated[list, add_messages]


def create_agent(
    model: str = None,
    temperature: float = None,
    system_prompt: str = None
):
    """Create the LangGraph agent with configurable parameters.
    
    Args:
        model: LLM model to use (default: from settings)
        temperature: Sampling temperature (default: 0)
        system_prompt: Custom system prompt (default: DEFAULT_SYSTEM_PROMPT)
    
    Returns:
        Compiled LangGraph agent
    """
    # Use settings defaults if not specified
    model = model or settings.openai_model
    temperature = temperature if temperature is not None else 0
    
    # Initialize the LLM with tools (reasoning models ignore temperature)
    llm = chat_model(model, temperature).bind_tools(TOOLS)
    
    # Store the system prompt for this agent
    agent_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    
    # Create tool node
    tool_node = ToolNode(TOOLS)
    
    def should_continue(state: AgentState) -> str:
        """Decide whether to continue with tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If there are tool calls, continue to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        # Otherwise, end
        return END
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM to decide next action."""
        messages = state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        }
    )
    workflow.add_edge("tools", "agent")
    
    # Compile and attach system prompt for reference
    compiled = workflow.compile()
    compiled.system_prompt = agent_system_prompt
    return compiled


# Create the default agent
agent = create_agent()


def ask_acme(question: str) -> str:
    """
    Ask a question to the Acme knowledge base.
    
    Args:
        question: The question to ask
        
    Returns:
        The agent's response
    """
    # Initialize state with system prompt
    initial_state = {
        "messages": [
            SystemMessage(content=DEFAULT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
    }
    
    # Run the agent
    result = agent.invoke(initial_state)
    
    # Extract the final response
    messages = result["messages"]
    
    # Find the last AI message that isn't just tool calls
    # (.text, not .content: Responses API replies are lists of content blocks)
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.text:
            return str(msg.text)
    
    return "I couldn't generate a response. Please try rephrasing your question."


def ask_acme_with_trace(question: str) -> dict[str, Any]:
    """
    Ask a question and return full trace for debugging.
    
    Args:
        question: The question to ask
        
    Returns:
        Dictionary with response and trace information
    """
    initial_state = {
        "messages": [
            SystemMessage(content=DEFAULT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
    }
    
    result = agent.invoke(initial_state)
    
    # Extract trace info
    messages = result["messages"]
    tool_calls = []
    
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "tool": tc["name"],
                    "args": tc["args"],
                })
    
    # Get final response
    response = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.text:
            response = str(msg.text)
            break
    
    return {
        "question": question,
        "response": response,
        "tool_calls": tool_calls,
        "message_count": len(messages),
    }


# For direct testing
if __name__ == "__main__":
    print("Ask Acme - Interactive Demo")
    print("="*60)
    print("Type 'quit' to exit\n")
    
    while True:
        question = input("You: ").strip()
        
        if question.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        
        if not question:
            continue
        
        print("\nAsk Acme: ", end="")
        try:
            response = ask_acme(question)
            print(response)
        except Exception as e:
            print(f"Error: {e}")
        
        print()
