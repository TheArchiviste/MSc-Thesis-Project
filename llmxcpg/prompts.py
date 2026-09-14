"""Prompt templates matching the released training/inference serialization.

The Q task follows the paper prompt. D includes the upstream system prompt,
instruction text, and section markers. Drift from these strings changes the
model contract and invalidates published calibration thresholds.
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
# LLMxCPG-D: vulnerability classification.
# ---------------------------------------------------------------------------
#
# The released implementation does not feed Figure 10 directly to the model.
# It prepends this system text and appends explicit Instruction/Input/Response
# section markers. Upstream attempts a "Single word" Yes/No rewrite, but its
# dataset says "One word", so that rewrite is a no-op. The target/output head
# is nevertheless Yes/No; this intentional-looking mismatch is preserved for
# checkpoint and threshold compatibility.
# Keeping that wire format matters because the released adapter and calibrated
# thresholds were trained against it.
DETECTION_SYSTEM_PROMPT = """\
You are a specialized vulnerability analyzer with deep expertise in taint analysis and secure coding practices.

Core Functions:
- Process sequential taint paths that show data flow from source to sink
- Analyze each transformation's security implications
- Detect missing input validations and sanitization
- Identify potential memory, buffer, and integer vulnerabilities
- Assess DMA operation safety
- Evaluate resource management

Behavioral Guidelines:
- Focus exclusively on the provided taint path sequence
- Track how data transforms through each step
- Consider implicit type conversions and edge cases
- Look for validation gaps between transformations
- Evaluate final sink operation safety
- Provide deterministic VULNERABLE/BENIGN classification

Vulnerability Categories:
- Buffer/Integer Operations
- Overflow/Underflow potential
- Sign conversion issues
- Boundary checks
- Memory Management
- Use-after-free
- Double free
- Memory corruption
- Uninitialized access
- DMA Operations
- Address validation
- Boundary checking
- Translation safety
- Size verification
- Input Processing
- Validation completeness
- Sanitization effectiveness
- Type safety
- Range checking

Analysis Method:
- Parse source-to-sink flow
- Identify critical transformations
- Detect validation gaps
- Evaluate sink safety
- Consider edge cases
- Make binary decision

Output: Exactly one word - VULNERABLE or BENIGN
"""

DETECTION_INSTRUCTION = """\
You are a security code vulnerability analyzer. Your task is to carefully analyze the provided code snippet. Note that the provided code snippet might not be complete, but it has all the important context.
Your output must be EXACTLY ONE WORD:

If you detect any potential security vulnerability in the specified code segment, return: VULNERABLE
If the code segment appears to be secure and free from obvious vulnerabilities, return: BENIGN

IMPORTANT GUIDELINES:

Consider common vulnerability types such as:

- Buffer overflows
- Improper input validation
- Integer Overflow
- Memory corruption potential
- Double free
- Use after free

Your response must be either 'VULNERABLE' or 'BENIGN' - no additional explanation

Output format:
One word: VULNERABLE or BENIGN
"""

DETECTION_PROMPT = (
    DETECTION_SYSTEM_PROMPT
    + "\n\n## Instruction:\n"
    + DETECTION_INSTRUCTION
    + "\n## Input:\n<CODE>\n## Response:\n"
)


def render_query_prompt(code: str) -> str:
    """Substitute code into the query-generation prompt."""
    return QUERY_GENERATION_PROMPT.replace("<CODE>", code)


def render_detection_prompt(code_slice: str) -> str:
    """Substitute slice into the classification prompt."""
    return DETECTION_PROMPT.replace("<CODE>", code_slice)
