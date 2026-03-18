"""
Example: Define your own rubric and generate against it.

Demonstrates creating a rubric inline (as a dict) and using it
with generate(). Also shows loading a rubric from a YAML file.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/custom_rubric.py
"""

from ramsay import generate, evaluate, load_rubric

# --- Option 1: Inline rubric as a dict ---

product_rubric = {
    "name": "product_copy",
    "description": "Evaluates product descriptions for clarity and persuasion without hype.",
    "dimensions": [
        {
            "name": "clarity",
            "description": (
                "Is the product's value immediately clear? "
                "1 = Confusing, jargon-heavy. "
                "3 = Clear after a second read. "
                "5 = Crystal clear on first read."
            ),
            "min_pass": 4,
            "hard_floor": True,
        },
        {
            "name": "specificity",
            "description": (
                "Does it use concrete details instead of vague claims? "
                "1 = All buzzwords ('revolutionary', 'cutting-edge'). "
                "3 = Mix of specific and vague. "
                "5 = Every claim backed by a specific detail or number."
            ),
            "min_pass": 3,
            "hard_floor": True,
        },
        {
            "name": "tone",
            "description": (
                "Does it sound like a human who cares about the product? "
                "1 = Corporate committee-speak. "
                "3 = Professional but bland. "
                "5 = Genuine enthusiasm without hype."
            ),
            "min_pass": 3,
            "hard_floor": False,
        },
    ],
    "banned_phrases": [
        "revolutionary",
        "game-changing",
        "cutting-edge",
        "best-in-class",
        "world-class",
        "synergy",
        "leverage",
        "paradigm shift",
    ],
    "kill_list": [
        "Buzzword soup -- multiple marketing superlatives in the same sentence",
        "Feature listing without benefits -- 'supports X, Y, Z' without saying why the user cares",
    ],
    "pass_rule": "all_hard_floors",
}

# Task and sources
task = """Write a 150-word product description for Zigzag, a data pipeline tool.
Focus on what it does and why someone would use it. No marketing fluff."""

sources = """
Zigzag product facts:
- Data pipeline tool for CDC (change data capture) replication
- Supports PostgreSQL, MySQL, and MongoDB as sources
- Target: any data warehouse (Snowflake, BigQuery, Redshift)
- Replication latency: sub-60-second for tables under 1M rows
- No configuration files needed -- auto-discovers schema
- Handles schema evolution (column adds/drops/renames) automatically
- Backfill support for historical data
- Founded because the team maintained custom Debezium pipelines
- 47 companies in production
- 3 customers with >10TB daily throughput
- Single binary deployment
"""

print("=== Generating with custom inline rubric ===\n")
result = generate(
    task=task,
    sources=sources,
    rubric=product_rubric,
    max_rewrites=2,
)
print(f"Passed: {result.passed}")
print(f"Scores: {result.scores}")
print(f"\n{result.text}\n")

# --- Option 2: Evaluate existing text against a built-in rubric ---

print("=== Evaluating existing text against built-in essay rubric ===\n")

existing_text = """
The rise of large language models has fundamentally changed how we think about
software development. What used to require teams of engineers can now be
prototyped by a single developer with the right prompts.

But this framing misses something important. The hard part of software was never
the typing. It was understanding the problem well enough to know what to build.
LLMs accelerate the typing. They don't accelerate the understanding.
"""

eval_result = evaluate(
    text=existing_text,
    rubric="essay",
    skip_grounding=True,
)
print(f"Passed: {eval_result.passed}")
if eval_result.style:
    for name, score in eval_result.style.scores.items():
        print(f"  {name}: {score}")
    if eval_result.style.feedback:
        print(f"  Feedback: {eval_result.style.feedback}")

# --- Option 3: Load and inspect a rubric ---

print("\n=== Inspecting built-in rubrics ===\n")
for name in ["email", "essay", "blog", "grant", "newsletter"]:
    try:
        rubric = load_rubric(name)
        hard = ", ".join(d.name for d in rubric.hard_floor_dimensions)
        print(f"  {rubric.name}: {len(rubric.dimensions)} dimensions, hard floors: {hard}")
    except FileNotFoundError:
        print(f"  {name}: not found")
