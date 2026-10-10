import os
import random
import time
from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate

# Mock LLM for validation testing without real API calls
class MockChatModel:
    def __init__(self, mock_response=None):
        self.mock_response = mock_response

    def with_structured_output(self, schema):
        def bound_mock(messages):
            return self.mock_response
        return bound_mock

class RouterState(TypedDict):
    query_id: str
    ticker: str
    year: str
    gold_evidence_keys: List[str]
    question: str
    estimated_selectivity: float
    correlation_level: str
    chosen_route: str
    final_answer: str
    sub_queries: List[str]  # Item 10: track sub-queries

import json
import os
from src.phase_b_router.policy import get_routing_decision

# Item 7 & 8: Decision Matrix with Hysteresis
# Node: Decision Matrix Router (Item 6 & 7)
def create_decision_matrix_router_node(thresholds_dict: dict):
    def route_node_decision_matrix(state: RouterState):
        route = get_routing_decision(state['correlation_level'], state['estimated_selectivity'], thresholds_dict)
        return {"chosen_route": route}
    return route_node_decision_matrix

import psycopg2
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src import db_settings
from src.utils.finqa_utils import get_embedding_client

def execute_vector_search(state: RouterState, route: str) -> str:
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    
    # Generate query embedding using the shared client
    embeddings = get_embedding_client()
    if embeddings is None:
        raise RuntimeError("No embedding client configured. Set AI_API_KEY and AI_MODEL.")
    query_vector = embeddings.embed_query(state["question"])
    
    if len(query_vector) != 768:
        raise ValueError(f"Embedding dimension mismatch: expected 768, got {len(query_vector)}. Are you using the correct embedding model?")
    print(f"[LOG] Used embedding model matching 768 dimensions.")

    with conn.cursor() as cur:
        if route == "iterative-scan":
            # iterative-scan: rely on pgvector's HNSW iterative scan with metadata filter
            cur.execute("SET enable_indexscan = on;")
            cur.execute("SET enable_seqscan = off;")
            cur.execute("SET hnsw.iterative_scan = 'relaxed_order';")
            cur.execute("""
                SELECT content, evidence_key 
                FROM finqa_evidence 
                WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s
                ORDER BY embedding <-> %s::vector
                LIMIT 6;
            """, (state["ticker"], state["year"], query_vector))
            results = cur.fetchall()
            
        elif route in {"post-filter", "post-filter-indexscan"}:
            cur.execute("SET enable_indexscan = on;")
            cur.execute("SET enable_seqscan = off;")
            cur.execute("SET hnsw.iterative_scan = off;")
            cur.execute("""
                SELECT content, evidence_key
                FROM finqa_evidence 
                WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s
                ORDER BY embedding <-> %s::vector
                LIMIT 6;
            """, (state["ticker"], state["year"], query_vector))
            results = cur.fetchall()

        elif route == "post-filter-app-top40":
            cur.execute("SET enable_indexscan = on;")
            cur.execute("SET enable_seqscan = off;")
            cur.execute("SET hnsw.iterative_scan = off;")
            cur.execute("""
                SELECT content, evidence_key, metadata->>'ticker', metadata->>'year'
                FROM finqa_evidence 
                ORDER BY embedding <-> %s::vector
                LIMIT 40;
            """, (query_vector,))
            
            raw_results = cur.fetchall()
            results = [(r[0], r[1]) for r in raw_results if r[2] == state["ticker"] and r[3] == state["year"]][:6]

        else:
            # pre-filter: exact search / fallback to seqscan
            cur.execute("SET enable_indexscan = off;")
            cur.execute("SET enable_seqscan = on;")
            cur.execute("""
                SELECT content, evidence_key 
                FROM finqa_evidence 
                WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s
                ORDER BY embedding <-> %s::vector
                LIMIT 6;
            """, (state["ticker"], state["year"], query_vector))
            results = cur.fetchall()
            
    conn.close()
    
    # Format evidence
    evidence_text = "\n".join([f"[{r[1]}] {r[0]}" for r in results])
    
    # Call LLM to solve the FinQA question
    ai_model = os.environ.get("AI_MODEL", "").strip()
    ai_api_key = os.environ.get("AI_API_KEY", "").strip()
    ai_api_base = os.environ.get("AI_API_BASE", "").strip()
    
    if not ai_model or not ai_api_key:
        raise RuntimeError("AI_MODEL and AI_API_KEY environment variables must be configured to generate an answer.")
        
    llm = ChatOpenAI(
        model=ai_model, 
        api_key=ai_api_key,
        base_url=ai_api_base if ai_api_base else None,
        temperature=0.0
    )
    
    messages = [
        SystemMessage(content="You are a financial analyst. Read the retrieved financial report excerpts and answer the user's question. Your final output must be ONLY the numeric answer (e.g. '1.5', '20%', '3/4') or boolean (e.g. 'yes', 'no'), with no surrounding text or explanations."),
        HumanMessage(content=f"Context:\n{evidence_text}\n\nQuestion: {state['question']}")
    ]
    
    response = llm.invoke(messages)
    return response.content.strip()

# Nodes: Execution Branches
def pre_filter_node(state: RouterState):
    # pre-filter exact search
    ans = execute_vector_search(state, route="pre-filter")
    return {"final_answer": ans}

def post_filter_node(state: RouterState):
    # post-filter app-level search
    ans = execute_vector_search(state, route="post-filter")
    return {"final_answer": ans}

def iterative_scan_node(state: RouterState):
    # iterative scan via pgvector
    ans = execute_vector_search(state, route="iterative-scan")
    return {"final_answer": ans}

# Item 6: LangGraph Skeleton (Decision Matrix)
def build_decision_matrix_graph(thresholds_dict: dict):
    workflow = StateGraph(RouterState)
    workflow.add_node("router", create_decision_matrix_router_node(thresholds_dict))
    workflow.add_node("pre-filter", pre_filter_node)
    workflow.add_node("post-filter", post_filter_node)
    workflow.add_node("iterative-scan", iterative_scan_node)
    
    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        lambda state: state["chosen_route"],
        {
            "pre-filter": "pre-filter",
            "post-filter": "post-filter",
            "iterative-scan": "iterative-scan"
        }
    )
    workflow.add_edge("pre-filter", END)
    workflow.add_edge("post-filter", END)
    workflow.add_edge("iterative-scan", END)
    return workflow.compile()

# Item 9 & 10: Naive Router baseline with Multi-query logging
class NaiveRouteDecision(BaseModel):
    route: Literal["pre-filter", "post-filter"] = Field(description="The chosen route strategy")
    sub_queries: List[str] = Field(
        description="If the question is multi-evidence, split it into sub-queries. Otherwise empty.",
        default_factory=list
    )

def create_naive_router_node(llm):
    """
    Creates a naive routing node using the provided LLM.
    The LLM decides the route and identifies sub-queries.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intelligent router for a vector database. Choose 'pre-filter' or 'post-filter' based on the question. If the question requires multiple distinct pieces of evidence, output them as sub_queries."),
        ("user", "Question: {question}")
    ])
    
    router_chain = prompt | llm.with_structured_output(NaiveRouteDecision)
    
    def route_node_naive(state: RouterState):
        decision = router_chain.invoke({"question": state["question"]})
        
        # Log if multi-query orchestration occurred (Item 10)
        if len(decision.sub_queries) > 0:
            print(f"[LOG] Naive Router split question into {len(decision.sub_queries)} sub-queries.")
            
        return {
            "chosen_route": decision.route,
            "sub_queries": decision.sub_queries
        }
    
    return route_node_naive

def build_naive_graph(llm):
    workflow = StateGraph(RouterState)
    workflow.add_node("router", create_naive_router_node(llm))
    workflow.add_node("pre-filter", pre_filter_node)
    workflow.add_node("post-filter", post_filter_node)
    
    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        lambda state: state["chosen_route"],
        {
            "pre-filter": "pre-filter",
            "post-filter": "post-filter"
        }
    )
    workflow.add_edge("pre-filter", END)
    workflow.add_edge("post-filter", END)
    return workflow.compile()
