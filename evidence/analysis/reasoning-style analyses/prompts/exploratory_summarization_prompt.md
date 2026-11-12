# Exploratory Summarization Prompt

```text
You are analyzing how a model organizes its reasoning in a multimodal context-learning task.

This is not a correctness judgment. Do not decide whether the answer is right or wrong.
Do not use any predefined label set.

Input:
1. The original multi-turn task prompt.
2. The model response.
3. The rubric or grading rationale, if available.

Please describe the dominant reasoning organization pattern of the response in free form.

Focus on:
- how the response organizes information before reaching its conclusion;
- what kinds of evidence the response mainly relies on;
- whether the response checks rules, constraints, formats, or ordering requirements;
- whether the response builds an intermediate structure to connect evidence and decisions;
- how evidence, rules, intermediate decisions, and final conclusions are connected.

Output:
{
  "free_form_description": "...",
  "key_reasoning_features": ["...", "..."],
  "brief_rationale": "..."
}
```
