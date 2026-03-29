## Context

Structured companyfacts are strong for numeric metrics but weak for management language. SEC archive documents already linked from submissions metadata are free and authoritative, so the missing layer is a deterministic text extraction pass that can pull guidance and outlook snippets without introducing paid providers.

## Goals / Non-Goals

**Goals:**
- Extract compact filing text highlights from free SEC filing documents.
- Persist guidance and filing excerpts in the existing financial report store.
- Surface those highlights in prompt and report contexts.

**Non-Goals:**
- Full-text indexing of every SEC filing.
- LLM-based filing summarization in the ingestion path.
- Paid earnings-call transcript coverage.

## Decisions

### Decision: extract keyword-focused snippets instead of storing full filing text
The report only needs a few high-signal sentences. We will scan filing text for guidance, outlook, capex, repurchase, and demand-language keywords, then store the best snippets.

### Decision: keep extraction deterministic and HTML-based
The filing archive documents are HTML or HTML-like text. We will extract visible paragraph text and derive snippets with simple ranking rules so the pipeline remains free, testable, and predictable.

## Risks / Trade-offs

- [Risk] Some filings contain weak or generic guidance wording. → Mitigation: keep snippets optional and only persist when they cross a minimum quality threshold.
- [Risk] Archive HTML varies across issuers. → Mitigation: rely on broad HTML paragraph extraction plus keyword ranking, not document-specific selectors.
