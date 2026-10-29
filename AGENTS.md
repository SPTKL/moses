# Product delivery working agreement

## Python tooling

- Use uv for Python environments, dependencies, commands, tests, and builds.
- Maintain the shared `uv.lock` for the root package and `examples/pluto`
  workspace member. Use `uv sync --locked` and `uv run --locked`; pass the same
  optional extras to both commands. Use `uv build --package` for distributions.
- Declare development tools in dependency groups and runtime dependencies in
  package metadata. Update the lockfile with uv when dependencies change.
- Keep PLUTO separately packaged and out of the default Moses installation.
- Preserve historical commands in recorded evidence; current instructions must
  use uv. Python subprocesses should inherit the running environment through
  `sys.executable` rather than invoke package installation at runtime.

## Model routing and supervision

The user's standing preference is to minimize token cost while keeping Astra
responsible for supervision. Apply this policy to all work in this repository.

- Always use `gpt-6-astra` as supervisor. If the active coordinator is not Astra,
  delegate supervision to one Astra agent with a concise task brief. The
  supervisor checks scope and dependencies, reviews consequential design
  decisions, and reviews the final changes and validation evidence before work
  is reported complete. Reuse that supervisor across implementation waves.
- Use the least expensive suitable available worker: `gpt-6-luna` for bounded
  lookups, mechanical edits and straightforward documentation; `gpt-6-sol` for
  routine implementation, focused tests and debugging; `gpt-6.1-sol` when an
  implementation needs stronger coding capability. Reserve Astra's work for
  supervision, architecture, difficult reasoning and high-risk reviews.
  These are routing preferences, not assertions about current per-token prices.
- Start with low or medium reasoning effort. Escalate effort or worker capability
  when complexity, failed checks or uncertainty justify it. Do not repeatedly
  retry a task with an unsuitable model just to keep its nominal cost down.
- Delegate bounded tasks with relevant paths, acceptance criteria and explicit
  file ownership. Pass compact context instead of full conversation history
  where supported. Avoid duplicate repository scans, redundant reviews,
  unnecessary parallel workers and verbose status polling. Keep trivial actions
  with the coordinator when another worker would cost more than it saves.
- This policy authorizes task-level agent delegation. It does not authorize
  messaging external chats, changing account defaults or running background
  automations. `AGENTS.md` guides model choice; it does not switch the active
  chat's model by itself. Explicitly select supported models when delegating.
- If Astra or model selection is unavailable, disclose the limitation rather
  than silently substituting a supervisor or claiming Astra reviewed the work.
  Continue useful preparation, but keep final Astra acceptance pending.

## Delivery and product review

For Moses product and implementation work, use GitHub issues and the Moses
project as the delivery source of truth. Review `docs/roadmap.md` and the relevant
issue before changing scope. PLUTO is the first real-world adoption case;
`examples/pluto/docs/pluto-delivery-plan.md` records its current execution plan.

- Assess each meaningful change from a senior PM perspective: who can use it,
  which task it enables, what decisions/errors the user must understand, and
  what evidence supports usability. Include roadmap implications in the review.
- When a defect or missing requirement arises, search existing issues first.
  Add evidence to the matching ticket or create a focused ticket with a
  reproduction, user impact, acceptance criteria, dependencies and priority.
  Distinguish observed defects from suspected defects and product suggestions.
- Keep issue/project status accurate. Local implementation is not merged or
  released; close issues only after acceptance checks and reviewed merge.
- Distinguish exact production inputs, alternate representations, bounded real
  samples and synthetic fixtures. A passing sample is not full-build parity or
  proof of citywide capacity.
- For PLUTO, preserve upstream release selection, raw captures, keys/null policy,
  CRS/axis decisions, input locks and provenance. Do not silently substitute
  current public data for a missing pinned or restricted production input.
- When parallel agents are requested, assign nonoverlapping file ownership,
  explicit dependency contracts and verification expectations. Integrate and
  review their outputs before reporting completion. Session roles are not
  GitHub account assignees or continuously running background agents.
- Preserve existing user changes. Treat the neighboring NYCPlanning
  data-engineering checkout as reference material unless editing it is requested.
