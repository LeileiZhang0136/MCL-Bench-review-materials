# Method Manifest for the 189 Synthetic Cases

All 189 synthetic cases in the paper were generated through the same method:

```text
synthetic-gpt55-api-v1
```

The author-confirmed generator is the GPT-5.5 API; no dated model snapshot is
claimed. The source dataset families are SlideVQA and MMLongBench-Doc. All
original benchmark content is kept unchanged. The executable pipeline,
prompts, schemas, and validators form a reference implementation of the shared
method.

The public method manifest contains only:

1. public `MCL-0001` to `MCL-0189` identifiers;
2. benchmark taxonomy;
3. task and serialized rubric-entry counts;
4. generation model; and
5. common construction method.

The paper may use:

> All 189 synthetic cases in the paper were generated through the GPT-5.5 API
> using source material from SlideVQA and MMLongBench-Doc.
