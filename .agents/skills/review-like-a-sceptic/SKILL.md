---
name: review-like-a-sceptic
description: Use after code is written. Checks the real result instead of trusting the agent's own summary.
---

# Review like a sceptic

1. Run the tests and show the real output.
2. List anything you did not test.
3. Check these specifically: duplicate counting on retry, behaviour on rate limit, behaviour when a provider returns an empty or malformed answer, secrets in code.
4. List what could break in production.
5. Do not claim success without evidence.