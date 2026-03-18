# Ramsay Filter

AI slop is not a collection of bad habits. It is a single failure mode: uniformity disguised as craft. The tell is never the technique itself, because any technique works in isolation. The tell is how evenly the technique gets distributed across a piece. Ezra Pound called it composing in the sequence of a metronome, and he was talking about bad poets in 1913, but it turns out LLMs have the same problem for the same reason.

Ramsay is a metronome detector you can run on your own text. It generates a draft, extracts every factual claim and checks it against your source material, then scores the output against a configurable style rubric. When something fails (and the first draft almost always fails), it rewrites with the specific feedback attached and tries again. It doesn't catch everything. Structure and narrative arc are still mostly on you, But it catches the mechanical stuff that accumulates into a fingerprint, the stuff a trained reader hears before they can name it.

[The full theory.](https://davesquickhits.substack.com/p/the-ramsay-filter-v2)

## Install

```bash
pip install -e .
```

Requires Python 3.9+ and an Anthropic API key:

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

## What it looks like

```python
from ramsay import generate

result = generate(
    task="Write a 1500-word essay explaining CRISPR base editing for a technical but non-specialist audience",
    sources="[your research notes, interview transcripts, paper excerpts]",
    rubric="essay",
)

print(result.passed)   # True if it cleared the quality bar
print(result.scores)   # dimension scores from the rubric
print(result.text)     # the final output
```

That's the happy path. The interesting part is everything it rejected along the way.

## How it works

Three stages, run in sequence. Grounding first because fabricated facts are worse than bad rhythm.

### 1. Generate

Produces initial text from your task, source material, and optional voice profile. The generation prompt is rubric-aware, so it knows what it'll be evaluated against.

### 2. Ground

Extracts every factual claim and checks it against your source material. Four verdicts: supported, contradicted, stale, unsupported. One failing claim fails the entire text. No averaging, no forgiveness for "mostly right."

### 3. Evaluate and rewrite

Two sub-stages:

**Regex precheck** (fast, deterministic, no API call): catches banned phrases, em dashes, structural tells. Defined in the rubric YAML.

**LLM evaluation**: scores the text on each dimension defined in the rubric. The LLM scores 1-5. Code enforces pass/fail deterministically from the scores. The LLM never decides the gate.

If either check fails, Ramsay rewrites with targeted feedback and runs the pipeline again. Repeats until pass or `max_rewrites` exhausted.

**Grounding fail-fast**: 2 consecutive grounding failures = bail. The generator keeps inventing the same kind of claim; another try won't help.

## Built-in rubrics

| Rubric | What it catches |
|--------|----------------|
| `essay` | Fabricated claims, AI tells, weak argument structure |
| `blog` | Bad hooks, listicle energy, disconnected sections |
| `email` | Pitch energy in warm follow-ups, AI rhythm, banned openers |
| `grant` | Vague problem statements, buzzword inflation, hand-waving methodology |
| `newsletter` | Neutral summaries (that's an RSS feed, not a newsletter), link dumping |

## Custom rubrics

Rubrics are YAML files. The short version:

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

```python
result = generate(task="...", sources="...", rubric="/path/to/my_rubric.yaml")
```

See `rubrics/README.md` for the full format.

## Voice profiles

Control the writing style:

```python
result = generate(
    task="Write about distributed caching",
    sources="...",
    rubric="blog",
    voice="Direct, conversational, no hedging. Short sentences. Technical but accessible.",
)
```

## CLI

```bash
# Generate with quality control
ramsay generate --task "Write about X" --sources notes.txt --rubric essay

# Evaluate existing text
ramsay evaluate --file draft.txt --rubric email --source notes.txt

# List available rubrics
ramsay rubrics
```

## API

The primary API is `generate()`. For evaluating existing text without generation, use `evaluate()`. For lower-level access to grounding and style evaluation independently, see `ramsay/grounding.py` and `ramsay/style.py`.

## License

MIT
