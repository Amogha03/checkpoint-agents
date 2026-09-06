# Codebase Analysis Service

## Problem Statement (Codebase Analysis)

Technical analysts and security auditors at a professional services firm spend significant time on tedious early-stage research: cloning repositories, tracing execution flows, and reading raw code to answer technical questions such as, "Where is authentication handled, and are there exposed endpoints?" This service is intended to automate that work and produce accurate, source-backed codebase analysis reports.

## State Graph Sketch

```mermaid
stateDiagram-v2
	[*] --> UserRequest
	UserRequest: ResearchState\nrepo_url\nquery\nsubtasks\nresults\nfinal_report
	UserRequest --> PlannerNode
	PlannerNode: Planner Node
	PlannerNode --> AnalyzerNodes
	AnalyzerNodes: Analyzer Node(s)
	AnalyzerNodes --> LocalFileSystem
	LocalFileSystem: Local File System
	LocalFileSystem --> AnalyzerNodes
	AnalyzerNodes --> SynthesizerNode
	SynthesizerNode: Synthesizer Node
	SynthesizerNode --> FinalReport
	FinalReport: Final Report
	FinalReport --> [*]
```
