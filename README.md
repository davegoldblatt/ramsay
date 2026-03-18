# Ramsay

Quality-controlled text generation. Define a rubric, provide sources, get text that passes your quality bar.

Ramsay generates text, then runs it through factual grounding verification and style evaluation against your rubric. If anything fails, it rewrites with targeted feedback until the text passes or gives up. The filter IS the product -- generation is just the entry point.

## Install

```bash
pip install -e .
```

Requires Python 3.9+ and an Anthropic API key:

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

## Quick start

Generate a quality-controlled essay in 5 lines:

```python
from ramsay import generate

result = generate(
    task="Write a 1500-word essay explaining CRISPR base editing for a technical but non-specialist audience",
    sources="[your research notes, interview transcripts, paper excerpts]",
    rubric="essay",
)

print(result.text)     # the final output
print(result.passed)   # True if it cleared the quality bar
print(result.scores)   # dimension scores from the rubric
```

## Use cases

**Scientific essays** -- Generate from research notes. Grounding verification catches fabricated claims. Style evaluation catches AI tells.

**Blog posts** -- Generate from interviews or research. The `blog` rubric checks for hook quality, argument flow, and AI patterns.

**Follow-up emails** -- Generate emails that sound like a real person wrote them. The `email` rubric catches pitch energy, banned phrases, and unnatural rhythm.

**Grant proposals** -- Generate from research plans and budgets. The `grant` rubric checks problem clarity, methodological rigor, and buzzword inflation.

**Newsletters** -- Generate digests from curated sources. The `newsletter` rubric checks editorial voice, curation quality, and density.

## How it works

Ramsay runs a three-stage pipeline:

### 1. Generate

Produces initial text from your task description, source material, and optional voice profile. The generation prompt is rubric-aware -- it knows what it'll be evaluated against.

### 2. Ground

Extracts every factual claim from the text and checks it against your source material. Four verdicts:

- **Supported** -- claim appears in the source material
- **Contradicted** -- claim conflicts with the source material (most serious)
- **Stale** -- claim was true but may no longer be current
- **Unsupported** -- claim has no basis in any source (fabricated)

One failing claim fails the entire text. No averaging, no forgiveness for "mostly right."

### 3. Evaluate and rewrite

Two sub-stages:

**Regex precheck** (fast, deterministic, no API call): Catches banned phrases, em dashes, structural tells. Defined in the rubric YAML.

**LLM evaluation**: Scores the text on each dimension defined in the rubric. The LLM scores 1-5; code enforces pass/fail deterministically from the scores. The LLM never decides the gate.

If either check fails, Ramsay rewrites with targeted feedback and runs the pipeline again. Repeats until pass or `max_rewrites` exhausted.

**Grounding fail-fast**: 2 consecutive grounding failures = bail. The generator keeps inventing the same kind of claim; another try won't help.

## Voice profiles

Control the writing style with an optional `voice` parameter:

```python
result = generate(
    task="Write about distributed caching",
    sources="...",
    rubric="blog",
    voice="Direct, conversational, no hedging. Short sentences. Technical but accessible.",
)
```

Voice can be a string, a dict with structured fields, or None (model's default voice):

```python
result = generate(
    task="...",
    sources="...",
    rubric="essay",
    voice={
        "tone": "academic but readable",
        "sentence_length": "varied, mostly medium",
        "perspective": "third person",
        "formality": "professional",
    },
)
```

## API reference

### `generate(task, sources, rubric, ...)` -- primary API

Generate quality-controlled text.

```python
from ramsay import generate

result = generate(
    task="Write a 500-word blog post about X",
    sources="Research notes, transcripts, etc...",
    rubric="blog",              # built-in name, file path, or dict
    voice="Conversational...",  # optional style profile
    max_rewrites=3,             # retry budget
    model="claude-sonnet-4-6",  # optional model override
)

result.text       # str -- the final output
result.passed     # bool -- did it clear the quality bar
result.attempts   # list[Attempt] -- all attempts with traces
result.scores     # dict -- final dimension scores
result.feedback   # str -- remaining feedback if it didn't fully pass
```

### `evaluate(text, source_material, rubric, ...)` -- check existing text

Evaluate text without generating or rewriting.

```python
from ramsay import evaluate

result = evaluate(
    text="Your text here...",
    source_material="Research notes, transcripts, etc...",
    rubric="email",
    subject="optional title",
    skip_grounding=False,
)

result.passed      # bool -- overall pass/fail
result.grounding   # GroundingResult with claim-level details
result.style       # StyleResult with scores and feedback
result.feedback    # combined feedback string
```

### Lower-level APIs

```python
from ramsay import verify_grounding, evaluate_style, load_rubric

# Grounding only
grounding = verify_grounding(text, source_material)
grounding.passed          # bool
grounding.claims          # list of Claim objects
grounding.failing_claims  # claims that failed

# Style only
style = evaluate_style(text, "email", subject="optional subject")
style.passed              # bool
style.scores              # dict of dimension scores
style.precheck_failed     # True if it failed at the regex stage

# Load and inspect a rubric
rubric = load_rubric("email")
rubric.dimensions             # list of Dimension objects
rubric.hard_floor_dimensions  # dimensions that drive pass/fail
rubric.banned_phrases         # list of banned phrases
```

## Custom rubrics

Rubrics are YAML files. See `rubrics/README.md` for the full format. The short version:

```yaml
name: my_rubric
description: What this rubric evaluates

dimensions:
  - name: clarity
    description: "Is it clear? 1=confusing, 5=crystal clear"
    min_pass: 4
    hard_floor: true   # Failing this fails the whole evaluation

  - name: tone
    description: "Does it sound human? 1=robotic, 5=genuine"
    min_pass: 3
    hard_floor: false   # Informs feedback but doesn't drive pass/fail

banned_phrases:
  - "game-changing"
  - "synergy"

kill_list:
  - "Buzzword soup -- multiple superlatives in one sentence"

pass_rule: all_hard_floors
```

Use a custom rubric:

```python
result = generate(task="...", sources="...", rubric="/path/to/my_rubric.yaml")
# or inline as a dict
result = generate(task="...", sources="...", rubric={"name": "inline", "dimensions": [...]})
```

## CLI

```bash
# Generate text (primary command)
ramsay generate --task "Write about X" --sources notes.txt --rubric essay
ramsay generate --task "Write about X" --sources notes.txt --rubric blog --voice "Casual, direct"

# Evaluate existing text
ramsay evaluate --file draft.txt --rubric email --source notes.txt
ramsay evaluate --text "Hey Sarah..." --rubric email --skip-grounding

# List available rubrics
ramsay rubrics

# JSON output
ramsay generate --task "..." --sources notes.txt --rubric essay --json
```

## Built-in rubrics

| Rubric | Focus | Hard floors |
|--------|-------|-------------|
| `email` | Email naturalness, anti-AI-tells | not_embarrassing, no_pitch_energy, natural_shape |
| `essay` | Long-form writing quality | factual_precision, no_ai_tells, argument_structure |
| `blog` | Blog posts from research/interviews | hook_quality, no_ai_tells, argument_flow |
| `grant` | Grant proposal writing | problem_clarity, methodological_rigor, no_ai_tells |
| `newsletter` | Newsletter/digest style | editorial_voice, no_ai_tells, curation_quality |

## License

MIT
