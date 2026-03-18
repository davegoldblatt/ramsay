"""
Example: Generate a follow-up email with quality control.

Demonstrates the FollowUpEasy use case -- generating emails that
pass grounding verification (no fabricated facts) and style evaluation
(no AI tells, no pitch energy).

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/generate_email.py
"""

from ramsay import generate

# The task
task = """Write a short follow-up email from me to Sarah Chen. We worked together
at Acme Corp on the data infrastructure team. She left 6 months ago to join
Zigzag as VP of Engineering. I want to reconnect casually -- no agenda, no pitch,
just genuine interest in how she's doing. Keep it under 100 words. Sound like
a real person, not an AI."""

# Source material: everything the email can reference
sources = """
Known facts about the relationship:
- I (the sender) and Sarah Chen worked together at Acme Corp for 2 years
- We were both on the data infrastructure team
- She left Acme Corp in September 2025 to join Zigzag as VP of Engineering
- We worked together on the data lake migration project (completed June 2025)
- My last email to her was October 2025 (congratulating her on the new role)
- I am NOT looking for a job -- do not imply job seeking
- I am NOT raising a fund or selling anything
- I am NOT asking for a favor
"""

# Generate with the email rubric
result = generate(
    task=task,
    sources=sources,
    rubric="email",
    max_rewrites=3,
)

print(f"Passed: {result.passed}")
print(f"Attempts: {len(result.attempts)}")
print(f"Scores: {result.scores}")
print()

if result.feedback:
    print(f"Feedback: {result.feedback}")
    print()

print("--- Generated email ---")
print(result.text)
print("--- End ---")

# Show the trace for debugging
if len(result.attempts) > 1:
    print(f"\n--- Trace ({len(result.attempts)} attempts) ---")
    for attempt in result.attempts:
        print(f"\nAttempt {attempt.attempt}: failure_type={attempt.failure_type}")
        if attempt.grounding:
            print(f"  Grounding: pass={attempt.grounding.get('pass')}")
        if attempt.style:
            print(f"  Style: passed={attempt.style.get('passed')}, scores={attempt.style.get('scores')}")
