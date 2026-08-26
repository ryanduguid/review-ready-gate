# review-ready-gate

Turn an agent's accounting run into a reviewer-ready pack.

An evaluation pack for `australian-accounting-skills` plus `aus-accounting-mcp`:
`input.json`, `run.log`, `output.json`, `expected.json`, `diff.md`, `README.md`,
and `REVIEW.md`.

**The pack is the evaluation artefact.** Use it to score whether a run is
reviewer-ready, not as a substitute for a human reviewer. See
[evaluation-pack.md](https://ryanduguid.github.io/docs/evaluation-pack.md).

## The contract

A gate run writes:

```
<run-dir>/
  input.json       # the case as submitted
  run.log          # stdout + stderr of the run
  output.json      # what the agent produced
  expected.json    # the known-good answer
  diff.md          # output vs expected, or "no expected"
  README.md        # machine summary of the case
  REVIEW.md        # human-facing: what to check, what is unknown
```

`REVIEW.md` is the file a reviewer opens. It never says "the agent was right."
It says: here is the input, here is the output, here is the expected (if any),
here is the diff, here is what a human still has to confirm.

## Install

```bash
pipx install review-ready-gate
```

The CLI is `review-gate`.

## Usage

```bash
review-gate run --case <case-id> --out ./runs/<run-id>
```

`--case` is a case id from `australian-accounting-skills` (for example
`coal-lsl-fy2025-hourly`). `--out` is a directory. The gate writes the seven
files into it.

If the case has no expected answer, `diff.md` says so and `REVIEW.md` flags it.

## What this is not

- Not a judge. It does not score the agent.
- Not a substitute for `aus-accounting-mcp`. The MCP is the calculator; this is
  the packager.
- Not a substitute for a human reviewer. `REVIEW.md` is a prompt, not a sign-off.

## Specs

Behaviour is specified in `openspec/specs/gate-pack/spec.md`. The CLI is a thin
wrapper around that contract.
