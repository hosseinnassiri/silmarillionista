# Silmarillion RAG + Agent + Vector DB + Graph — Implementation Plan

## 1. Project structure

```
silmarillion-agent/
├── data/
│   ├── raw/                      # original .txt source
│   ├── processed/                # cleaned, chunked JSON
│   └── eval/                     # test question set (JSON)
├── src/
│   ├── ingest/
│   │   ├── clean_text.py         # chapter/paragraph splitting
│   │   └── chunk.py              # chunking + metadata tagging
│   ├── vectorstore/
│   │   ├── build_index.py        # embed + write to Chroma
│   │   └── retriever.py          # query wrapper
│   ├── graph/
│   │   ├── schema.py             # allowed nodes/relationships
│   │   ├── extract.py            # LLMGraphTransformer pipeline
│   │   └── query.py              # Cypher generation/execution wrapper
│   ├── agent/
│   │   ├── state.py              # LangGraph state schema
│   │   ├── nodes.py              # router, retrieve, synthesize nodes
│   │   └── graph_app.py          # LangGraph assembly + compile
│   └── config.py                 # env vars, model names, DB URIs
├── eval/
│   ├── run_eval.py               # runs test set through agent
│   └── score.py                  # routing accuracy + answer scoring
├── .env                          # API keys, Neo4j creds
├── requirements.txt
└── main.py                       # CLI entrypoint
```

## 2. Dependencies

```
langchain
langchain-openai
langchain-anthropic
langchain-experimental      # LLMGraphTransformer
langchain-community         # Neo4jGraph, GraphCypherQAChain
langgraph
neo4j
chromadb
python-dotenv
tiktoken
```

Plus a running Neo4j instance — easiest for dev is Neo4j Desktop or the official Docker image (`docker run -p7474:7474 -p7687:7687 neo4j`).

## 3. Phase-by-phase tasks

### Phase 1 — Ingestion & chunking
- [ ] Write regex-based chapter splitter (Silmarillion has clean chapter headers — split on those first).
- [ ] Paragraph-level chunking within each chapter using `RecursiveCharacterTextSplitter` (~500 tokens, ~50 overlap).
- [ ] Attach metadata per chunk: `chapter`, `chapter_number`, `part` (Ainulindalë / Valaquenta / Quenta Silmarillion / Akallabêth / Of the Rings of Power).
- [ ] Save as `data/processed/chunks.json` — list of `{text, metadata}`.
- **Done when**: chunk count and a handful of spot-checked chunks look clean (no broken sentences, correct chapter tags).

### Phase 2 — Vector store
- [ ] Embed all chunks (`text-embedding-3-large` or equivalent).
- [ ] Write to Chroma with metadata attached, persisted to disk (`data/processed/chroma_db/`).
- [ ] Build a `retriever.py` wrapper: `vector_search(query, k=5, filters=None) -> List[Document]`.
- **Done when**: a handful of manual test queries (e.g. "the creation of the Silmarils") return relevant chunks.

### Phase 3 — Graph schema & extraction
- [ ] Define allowed node labels: `Vala, Maia, Elf, Man, Dwarf, Place, Object, Event, House`.
- [ ] Define allowed relationship types: `PARENT_OF, SPOUSE_OF, RULED, CREATED, DESTROYED, FOUGHT, ALLIED_WITH, ENEMY_OF, LOCATED_IN, PARTICIPATED_IN, ALSO_KNOWN_AS, HAPPENED_DURING`.
  - `ALSO_KNOWN_AS` matters specifically for alias/epithet questions (Beren = Erchamion, Túrin = Turambar).
  - `HAPPENED_DURING` links events to ages/periods for timeline questions.
- [ ] Configure `LLMGraphTransformer` with `allowed_nodes` / `allowed_relationships` (don't leave it unconstrained).
- [ ] Run extraction over all chunks → graph documents.
- [ ] Push to Neo4j via `Neo4jGraph.add_graph_documents()`.
- [ ] **Manual QA pass**: pull 20–30 random triples, check against the text for accuracy. Expect to iterate on the schema/prompt at least once — alias resolution and multi-hop family relations are the most common failure points.
- **Done when**: spot-checked triples are accurate and key entities (Fëanor, Beren, Lúthien, Túrin, Morgoth) have reasonably complete neighborhoods in Neo4j Browser.

### Phase 4 — Graph query layer
- [ ] Wrap `GraphCypherQAChain` (or a custom Cypher-generation prompt if you want more control over multi-hop queries) as `graph_query(question) -> str/records`.
- [ ] Test directly against Neo4j Browser with a few manual Cypher queries first, to confirm the schema supports genealogy, timeline, and journey-path questions before trusting the LLM to generate them.
- **Done when**: a genealogy question and a multi-hop "allies of X's enemies" style question both return correct results.

### Phase 5 — LangGraph agent
- [ ] Define state schema (`question`, `route`, `vector_context`, `graph_context`, `answer`, `sources`).
- [ ] **Router node**: LLM classifies into `semantic` / `relational` / `both`, using the category list from Step 5 test design as few-shot guidance.
- [ ] **Vector retrieve node**.
- [ ] **Graph retrieve node**.
- [ ] **Synthesize node**: combine available context, answer, cite chapter sources, and explicitly say "not covered in this text" when appropriate (important for edge-case questions like Aragorn's lineage, which extends beyond the Silmarillion).
- [ ] Wire conditional edges from router → retrieval node(s) → synthesize.
- [ ] Compile the graph, expose a simple `ask(question) -> answer` function.
- **Done when**: you can run a question end-to-end from CLI and get a cited answer.

### Phase 6 — Eval set & scoring
- [ ] Build `data/eval/questions.json` using the schema below.
- [ ] Write `run_eval.py`: runs each question through the agent, logs `route`, `answer`, `graph_context`, `vector_context`.
- [ ] Write `score.py`: checks `route` against `expected_route`, and does a manual or LLM-assisted pass on answer quality.
- **Done when**: routing accuracy is reasonable (~80%+) and you've reviewed failure cases.

## 4. Eval question schema

```json
{
  "id": "genealogy_01",
  "category": "family_tree",
  "question": "List all descendants of Finwë.",
  "expected_route": "relational",
  "expects_multi_hop": true,
  "notes": "Tests multi-generation traversal in Neo4j."
}
```

Categories to include (from prior discussion): `alias_resolution, character_explainer, family_tree, character_comparison, event_explainer, timeline, events_between, location_description, journey_path, quotes, related_topics, relationships, allies_enemies`.

## 5. Suggested build order (milestones)

1. **M1** — Ingestion + vector RAG working end-to-end (Phases 1–2). Fastest win, validates the pipeline.
2. **M2** — Graph populated in Neo4j with spot-checked accuracy (Phase 3).
3. **M3** — Graph query layer answering genealogy/journey questions correctly in isolation (Phase 4).
4. **M4** — LangGraph agent routing and combining both (Phase 5).
5. **M5** — Full eval set run, routing accuracy measured, iterate on router prompt and graph schema based on failures (Phase 6).

## 6. Known risk areas to watch for
- **Alias collisions**: characters with multiple names/epithets can create duplicate nodes unless `ALSO_KNOWN_AS` is enforced and a resolution/merge step is added.
- **Temporal reasoning**: the Silmarillion's ages/years aren't always explicit in-text; timeline questions may need a manually curated age/event lookup rather than pure extraction.
- **Multi-hop Cypher generation**: LLM-generated Cypher can struggle with deep traversals (e.g. 3+ generation genealogies) — test these specifically and consider hand-written Cypher templates for known question patterns as a fallback.
- **Router misclassification**: "compare" and "related topics" questions often need both sources — make sure few-shot examples in the router prompt cover these ambiguous cases.

## 7. Next concrete step
Start with Phase 1 (ingestion/chunking script) — everything downstream depends on chunk quality and consistent metadata tagging.
