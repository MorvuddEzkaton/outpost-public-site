# Branch retention

Keep `main` and `staging`, branches attached to active PRs, and explicitly registered rollback references. Do not carry the historical private repository's refs into this repository.

After a PR is merged and production is verified, its disposable topic branch may be removed automatically. Never automatically delete `main`, `staging`, unmerged work, or rollback references. Configure the hosting platform only after inspecting the relevant protection rules.

Routine rollback retention: five latest known-good deployment points plus explicitly marked major-release checkpoints. Prefer annotated release tags for immutable milestones; do not create one backup branch per small edit indefinitely.

For cleanup of the old private repository, first produce a separate private candidate list showing each branch SHA, active PRs, unique/unmerged changes, and a recoverable backup. Deletion requires explicit approval of that exact list. Age alone is not sufficient. Repository migration does not authorize deletion of historical branches.
