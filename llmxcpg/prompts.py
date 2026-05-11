"""Prompt templates.

Lifted directly from Appendix E (Figures 8, 9, 10) of the paper. Do not freelance:
fine-tuning was done against these exact strings, and drift will degrade results.
"""

# ---------------------------------------------------------------------------
# LLMxCPG-Q: query generation (Figure 8 in the paper).
# ---------------------------------------------------------------------------
QUERY_GENERATION_PROMPT = """\
Instruction:
Your task is to design Precise Joern CPGQL Queries for Vulnerability Analysis.

Objective:
Develop targeted CPGQL Joern queries to:
  - Identify taint flows based on your analysis.
  - Capture potential vulnerability paths.

Constraints:
  - Queries must be executable in Joern/CPGQL
  - Use Scala language features for query construction
  - Last query must use reachableByFlows to identify vulnerable paths

Output Requirements:
Provide a JSON object with one field "queries": Sequence of CPGQL queries to detect vulnerability

Expected JSON Output Format:
{
  "queries": ["Query1", "Query2", ..., "Final Reachable Flows Query"]
}

Example Output:
{
  "queries": [
    "val freeCallsWithIdentifier = cpg.method.name(\\"(.*_)?free\\").filter(_.parameter.size == 1).callIn.where(_.argument(1).isIdentifier).l",
    "freeCallsWithIdentifier.flatMap(f => { val freedIdentifierCode = f.argument(1).code; val postDom = f.postDominatedBy.toSetImmutable; val assignedPostDom = postDom.isIdentifier.where(_.inAssignment).codeExact(freedIdentifierCode).flatMap(id => id ++ id.postDominatedBy); postDom.removeAll(assignedPostDom).isIdentifier.codeExact(freedIdentifierCode).reachableByFlows(f.argument(1)) }).l"
  ]
}

Input: <CODE>
"""


# ---------------------------------------------------------------------------
# LLMxCPG-D: vulnerability classification (Figure 10 in the paper).
# ---------------------------------------------------------------------------
#
# Worth flagging: the paper's prompt has a small inconsistency — the body asks
# for "VULNERABLE" or "BENIGN", then the closing instruction says "VULNERABLE"
# or "SAFE". We use VULNERABLE/SAFE because (a) it's what the closing line
# asserts and (b) it's what the reduced-LM-head logic in inference/classifier.py
# extracts. If you fine-tune from a different prompt, change ModelConfig.
#
DETECTION_PROMPT = """\
Instruction:
You are a security code vulnerability analyzer. Your task is to carefully analyze the provided code snippet. Note that the provided code snippet might not be complete, but it has all the important context.

Your output must be EXACTLY ONE WORD:
  - If you detect any potential security vulnerability in the specified code segment, return: VULNERABLE
  - If the code segment appears to be secure and free from obvious vulnerabilities, return: SAFE

IMPORTANT GUIDELINES:
Consider common vulnerability types such as:
  - Buffer overflows
  - Improper input validation
  - Integer Overflow
  - Memory corruption potential
  - Double free
  - Use after free

Your response must be either 'VULNERABLE' or 'SAFE' - no additional explanation

Output format:
One word: VULNERABLE or SAFE

Input: <CODE>
"""


def render_query_prompt(code: str) -> str:
    """Substitute code into the query-generation prompt."""
    return QUERY_GENERATION_PROMPT.replace("<CODE>", code)


def render_detection_prompt(code_slice: str) -> str:
    """Substitute slice into the classification prompt."""
    return DETECTION_PROMPT.replace("<CODE>", code_slice)
