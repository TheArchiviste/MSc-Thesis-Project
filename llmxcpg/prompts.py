"""Released QCRI query prompt at fd7af0df8d2221ec196b85bc460da5cb40f6866c.

The instruction serialization is retained byte for byte. Only source insertion varies.
See rq1/REFERENCE_CONTRACT.md and NOTICE.
"""

QUERY_GENERATION_PROMPT = 'Your task is to design Precise Joern CPGQL Queries for Vulnerability Analysis.\n\nObjective:\nDevelop targeted CPGQL Joern queries to:\n1. Identify taint flows based on your analysis\n2. Capture potential vulnerability paths\n\nConstraints:\n- Queries must be executable in Joern/CPGQL\n- Use Scala language features for query construction\n- Last query must use reachableByFlows to identify vulnerable paths\n\nOutput Requirements:\n- Provide a JSON object with one field:\n  "queries": Sequence of CPGQL queries to detect vulnerability\n\nExpected JSON Output Format:\n```json\n{\n  "queries": ["Query1", "Query2", ..., "Final Reachable Flows Query"]\n}\n```\n\nExample Output:\n```json\n{\n  "queries": [\n    "val freeCallsWithIdentifier = cpg.method.name("(.*_)?free").filter(_.parameter.size == 1).callIn.where(_.argument(1).isIdentifier).l",\n    "freeCallsWithIdentifier.flatMap(f => {val freedIdentifierCode = f.argument(1).code; val postDom = f.postDominatedBy.toSetImmutable; val assignedPostDom = postDom.isIdentifier.where(_.inAssignment).codeExact(freedIdentifierCode).flatMap(id => id ++ id.postDominatedBy); postDom.removedAll(assignedPostDom).isIdentifier.codeExact(freedIdentifierCode).reachableByFlows(f.argument(1))}).l"\n  ]\n}\n```\n\nInput:\n<CODE>'


def render_query_prompt(code: str) -> str:
    return QUERY_GENERATION_PROMPT.replace("<CODE>", code)
