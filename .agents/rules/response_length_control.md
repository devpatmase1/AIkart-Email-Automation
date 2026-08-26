# Custom Response-Length Control Rule

This rule defines an adaptive, content-aware response-length control system for AI agents. The goal is NOT to force every answer into an arbitrary fixed word count, but to dynamically determine the appropriate response depth based on query complexity while maintaining completeness, clarity, and logical conclusion.

---

## 1. Analyze Before Generating

* First analyze the original content, user request, complexity, number of concepts, required explanation, and amount of information needed.
* Determine the minimum amount of text required to provide a complete answer.
* Do not start writing until the required response depth is understood.

## 2. Use an Adaptive Word Range

* Never use a single rigid word limit.
* Generate a reasonable minimum and maximum word range based on the content.
* The maximum should be treated as a strong target, not something that causes the answer to become incomplete.
* A small overflow is acceptable when necessary to properly conclude an important point.

## 3. Prioritize Completeness Over Exact Word Count

* Never remove essential information merely to satisfy the word limit.
* Never end the response abruptly just because the limit has been reached.
* The response must always reach a natural conclusion.
* Avoid unnecessary repetition, filler, introductions, disclaimers, and verbose wording.

## 4. Range Selection Logic

Choose the range dynamically according to complexity:

* **Very Simple Request** → Short range (e.g., 50–150 words)
* **Moderate Explanation** → Medium range (e.g., 200–400 words)
* **Complex Explanation** → Longer range (e.g., 400–600 words)
* **Multi-Part or Highly Detailed Request** → Larger range (e.g., 750–950 words)

*Note: The numbers above are illustrative examples. Do NOT hard-code fixed limits. Dynamically determine the range based on content depth.*

## 5. Minimum-Word Rule

* The minimum represents the approximate amount of content required to answer the request properly.
* Do NOT artificially expand a short answer just to reach the minimum.

## 6. Maximum-Word Rule

* The maximum prevents unnecessary verbosity.
* When approaching the maximum:
  1. Remove repetition first.
  2. Remove low-value details.
  3. Compress wording.
  4. Preserve essential reasoning and conclusions.
* If a few additional words are genuinely necessary to complete the answer, exceeding the maximum slightly is preferable to producing an incomplete answer.

## 7. Final Validation Checklist

Before returning any response, internally check:

- [ ] Is every important part of the request answered?
- [ ] Is the reasoning complete?
- [ ] Does the response have a clear and natural conclusion?
- [ ] Is there unnecessary repetition or filler?
- [ ] Is the response within the content-aware, dynamically selected range?

If not, revise the response before returning it.
