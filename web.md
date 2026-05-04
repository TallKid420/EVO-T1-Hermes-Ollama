You will build a RAG app with chat and doccument ingestion interfaces. config via yaml files, no admin ui.

Frontend: React, Typescript, Tailwind, shandcn/ui and vite. 

Basic Backend: Python + Fast API

Database Supabase (Postgres, pgvector, auth, storage, realtime)

LLM: I will integrate this

Observability: Langsmith

Python backend must use a venv virtual environment
No LangChain, no LangGraph - raw SDK calls only
Use Pydantic for structured LLM outputs
All tables need Row-Level Security - users only see their own data
Stream chat responses via SSE
Use Supabase Realtime for ingestion status updates
Module 2+ uses stateless completions - store and send chat history yourself
Ingestion is manual file upload only - no connectors or automated pipelines

Save all plans to .agent/plans/ folder
Naming convention: {sequence}.{plan-name}.md (e.g., 1.auth-setup.md, 2.document-ingestion.md)
Plans should be detailed enough to execute without ambiguity
Each task in the plan must include at least one validation test to verify it works
Assess complexity and single-pass feasibility - can an agent realistically complete this in one go?
Include a complexity indicator at the top of each plan:
✅ Simple - Single-pass executable, low risk
⚠️ Medium - May need iteration, some complexity
🔴 Complex - Break into sub-plans before executing

Plan - Create a detailed plan and save it to .agent/plans/
Build - Execute the plan to implement the feature
Validate - Test and verify the implementation works correctly. Use browser testing where applicable via an appropriate MCP
Iterate - Fix any issues found during validation

I want this to integrate with my already existing code. Build and focus on the fron end right now integrating with my current back end. we will change my back en later to make it better. Go.