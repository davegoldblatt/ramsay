"""
Example: Generate a blog post from an interview transcript.

Demonstrates using generate() with a voice parameter to control
the writing style.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/generate_blog.py
"""

from ramsay import generate

# The task
task = """Write an 800-word blog post about why most startups fail at hiring
their first sales rep. Use the interview transcript below as your primary source.
The post should feel like a founder sharing hard-won lessons, not a listicle."""

# Source material: interview transcript
sources = """
Interview with Maya Torres, CEO of Backplane (B2B SaaS, $4M ARR, 18 employees)

Q: When did you hire your first sales rep?
A: Way too early. We were at maybe $30k MRR, all founder-led sales. I thought
   a rep would 3x our pipeline. Instead we went three months with zero closed deals
   from the new hire and I was still closing everything myself.

Q: What went wrong?
A: Three things. First, we didn't have a repeatable sales motion. I could sell
   because I built the product and could improvise in every call. The rep couldn't.
   Second, we hired someone from a big company -- Oracle background -- and our deal
   size was $500/mo. The muscle memory was totally wrong. Third, we didn't have any
   sales collateral. No case studies, no ROI calculator. I was selling on vibes
   and product demos. You can't hand that off.

Q: What would you do differently?
A: I'd wait until $80-100k MRR and at least 3 repeatable deal patterns before
   hiring. And I'd hire someone who's sold at our price point, not someone
   impressive on paper. Our second hire came from a startup selling $200/mo
   subscriptions and she crushed it from month one.

Q: Any other advice for founders?
A: Document your sales calls before you hire. Record yourself, write down
   the objections, note what closes deals. The first rep needs a playbook,
   even if it's scrappy. If you can't describe your sales motion in a one-pager,
   you're not ready to hire.

Q: Numbers from your experience?
A: First rep: $0 closed in 3 months, $12k salary cost. Second rep: $47k closed
   in first 60 days, fully ramped by month 3. The difference wasn't talent --
   it was readiness. We had a playbook, case studies, and a price point that
   matched her experience.
"""

# Voice: how the blog should read
voice = "Direct and conversational. Short paragraphs. No hedging or qualifiers. Sounds like a founder writing on their blog at midnight, not a content marketer. Occasional bluntness."

# Generate
result = generate(
    task=task,
    sources=sources,
    rubric="blog",
    voice=voice,
    max_rewrites=3,
)

print(f"Passed: {result.passed}")
print(f"Attempts: {len(result.attempts)}")
print(f"Scores: {result.scores}")
print()

if result.feedback:
    print(f"Feedback: {result.feedback}")
    print()

print("--- Generated blog post ---")
print(result.text)
print("--- End ---")
