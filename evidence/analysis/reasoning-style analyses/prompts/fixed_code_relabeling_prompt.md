# Fixed-Code Re-labeling Prompt

```text
You are assigning a primary reasoning-style label using the fixed codebook derived from the exploratory summarization stage.

This is not a correctness judgment. Do not evaluate whether the answer is correct.
Label only the dominant organization pattern of the response.

The four reasoning-style categories are:

1. Hierarchical Audit Structuring:
The response first establishes a hierarchical audit framework and then examines evidence, rules, and conclusions layer by layer, such as distinguishing global evidence, local evidence, candidate evidence, and non-mergeable evidence before giving a final judgment.

2. Procedural Constraint Decomposition:
The response decomposes task rules, steps, format requirements, or constraints into a set of checkable subconditions and verifies them one by one, such as turning ordering, labels, formats, and preconditions into checklist-style steps.

3. Local Evidence Grounding:
The response mainly focuses on local evidence, such as specific images, video segments, table cells, text fields, or local object relations. Such responses may accurately cite local information but may not form a complete global structure or cross-turn rule chain.

4. Global Schema Induction:
The response attempts to infer an overall task pattern, global rule, or abstract schema from multiple context fragments and uses that schema to explain subsequent questions, such as deriving a general procedure, classification system, or decision rule from multiple images, videos, or dialogue turns.

Decision rule:
Assign exactly one primary label from the four categories.
If multiple styles appear, choose the one that provides the main organization of the final answer.
Do not create a new category.
If the response is difficult to classify, choose the closest primary label and explain why this label is the best fit.

Output JSON only:
{
  "primary_label": "...",
  "brief_rationale": "..."
}
```
