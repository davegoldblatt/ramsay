# Writing Custom Rubrics

Ramsay rubrics are YAML files that define quality scoring dimensions, pass/fail thresholds, banned phrases, and structural anti-patterns. When you call `generate()` or `evaluate()`, the rubric controls what "good enough" means.

## Rubric format

```yaml
name: my_rubric
description: >
  What this rubric evaluates and what "good" looks like.

dimensions:
  - name: dimension_name
    description: >
      What this dimension measures. Include the 1-5 scale descriptions
      so the LLM knows what each score means.
    min_pass: 4        # Minimum score to pass (1-5)
    hard_floor: true   # If true, failing this dimension fails the whole evaluation

kill_list:
  - "Structural anti-pattern description"
  - "Another pattern to reject"

banned_phrases:
  - "phrase that auto-fails"       # Case-insensitive literal match
  - "another banned phrase"

subject_banned:                    # Only relevant if you're evaluating text with a subject/title
  - "generic title"

max_em_dashes: 0                   # Maximum mid-sentence em dashes allowed
max_subject_words: 10              # Maximum words in subject/title
pass_rule: all_hard_floors         # "all_hard_floors" or "average"
```

## Key concepts

### Dimensions
Each dimension is scored 1-5 by the LLM. Write clear descriptions that include what each score level (1-5) means. The more specific the description, the more consistent the scoring.

### Hard floors vs. advisory
- **Hard floor** (`hard_floor: true`): If the score is below `min_pass`, the text fails. Period.
- **Advisory** (`hard_floor: false`): The score informs feedback but doesn't drive pass/fail.

### Banned phrases
These are checked by regex before the LLM even sees the text. They're case-insensitive literal matches. Use these for phrases that are always wrong regardless of context (e.g., "let's dive in" in formal writing).

Tip: trailing spaces matter. `"genuinely "` matches "genuinely curious" but not "genuinely" at end of sentence.

### Kill list
Unlike banned phrases (which are regex-matched), kill list items are described to the LLM as structural anti-patterns. The LLM evaluates whether the text exhibits these patterns. Use these for patterns that require judgment (e.g., "editorializing instead of asking").

### Pass rules
- `all_hard_floors`: Text passes if all hard-floor dimensions meet their minimums.
- `average`: Text passes if the average of all dimensions is >= 3.5 AND all hard floors are met.

## Using custom rubrics

### With generate()

```python
from ramsay import generate

# By file path
result = generate(
    task="Write a product description for...",
    sources="...",
    rubric="/path/to/my_rubric.yaml",
)

# By dict (useful for programmatic rubrics)
result = generate(
    task="...",
    sources="...",
    rubric={
        "name": "custom",
        "description": "Quick custom rubric",
        "dimensions": [
            {"name": "quality", "description": "Overall quality", "min_pass": 3, "hard_floor": True},
        ],
    },
)
```

### With evaluate()

```python
from ramsay import evaluate

result = evaluate(text="...", rubric="/path/to/my_rubric.yaml")
result = evaluate(text="...", rubric={"name": "inline", "dimensions": [...]})
```

### From the CLI

```bash
ramsay generate --task "..." --sources notes.txt --rubric /path/to/my_rubric.yaml
ramsay evaluate --text "..." --rubric /path/to/my_rubric.yaml
```

## Built-in rubrics

| Rubric | Focus | Hard floors |
|--------|-------|-------------|
| `email` | Email naturalness, anti-AI-tells | not_embarrassing, no_pitch_energy, natural_shape |
| `essay` | Long-form writing quality | factual_precision, no_ai_tells, argument_structure |
| `blog` | Blog posts from research/interviews | hook_quality, no_ai_tells, argument_flow |
| `grant` | Grant proposal writing | problem_clarity, methodological_rigor, no_ai_tells |
| `newsletter` | Newsletter/digest style | editorial_voice, no_ai_tells, curation_quality |

## Tips

1. Keep dimension count between 3-7. Too few and you miss problems. Too many and the LLM's attention dilutes.
2. Put your most important dimension first. The LLM pays more attention to it.
3. Include concrete examples in your dimension descriptions. "A body that reads human but has a subject like 'Reconnecting' fails" is more useful than "subject should be natural."
4. The banned phrases list should be short and high-confidence. If a phrase is only sometimes bad, put it in the kill list description instead.
5. Test your rubric on 5-10 examples before deploying. Check that the scores feel right and that the pass/fail gate catches what you want it to catch.
