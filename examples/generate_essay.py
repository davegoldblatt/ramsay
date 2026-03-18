"""
Example: Generate a scientific essay from research notes.

Demonstrates the primary generate() API -- provide a task, sources,
and a rubric, and Ramsay generates text that passes the quality bar.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/generate_essay.py
"""

from ramsay import generate

# The task: what you want written
task = """Write a 1000-word essay explaining CRISPR base editing for a technical
but non-specialist audience. Cover what base editing is, how it differs from
traditional CRISPR-Cas9 (which cuts DNA), the two main types (CBE and ABE),
and why it matters for treating genetic diseases. Use the source material
for all technical claims."""

# Source material: the facts the essay must be grounded in
sources = """
Research notes on CRISPR base editing:

Key facts:
- Traditional CRISPR-Cas9 creates double-strand breaks (DSBs) in DNA
- DSBs are repaired by the cell, but repair is error-prone (insertions/deletions)
- Base editors were first published by David Liu's lab at Harvard/Broad Institute (2016)
- Base editors do NOT cut both DNA strands -- they chemically convert one base to another
- Two main types:
  - CBE (cytosine base editor): converts C-G to T-A
  - ABE (adenine base editor): converts A-T to G-C, published 2017
  - Together, CBEs and ABEs can address ~60% of known point mutations causing disease
- Point mutations (single-letter changes) cause ~30,000 known genetic diseases
- Key advantage: no DSBs means fewer unintended edits (indels)
- Base editing is less efficient than Cas9 at completely knocking out genes
- Clinical trials:
  - Verve Therapeutics: base editing for heterozygous familial hypercholesterolemia (HeFH)
  - Beam Therapeutics: base editing for sickle cell disease (Phase 1/2)
  - First in-human base editing data (Verve, 2023): PCSK9 editing reduced LDL cholesterol ~55%
- Limitations:
  - Can only make certain transition mutations (not all 12 possible base changes)
  - "Bystander editing" -- nearby bases in the editing window can also be changed
  - Delivery remains a challenge (lipid nanoparticles for liver, viral vectors for other tissues)
- Prime editing (also from Liu lab, 2019) can make all 12 types of point mutations
  but is less efficient than base editing for the mutations both can address
"""

# Generate the essay
result = generate(
    task=task,
    sources=sources,
    rubric="essay",
    max_rewrites=3,
)

# Print results
print(f"Passed: {result.passed}")
print(f"Attempts: {len(result.attempts)}")
print(f"Scores: {result.scores}")
print()

if result.feedback:
    print(f"Feedback: {result.feedback}")
    print()

print("--- Generated essay ---")
print(result.text)
print("--- End ---")
