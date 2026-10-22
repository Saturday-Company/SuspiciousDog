# Results

Our own sessions, frozen on 2026-10-23. Counts in [`results/saturday-2026-10-23.json`](results/saturday-2026-10-23.json)
(the same format `sdog share` produces) and [`results/saturday-2026-10-23-provenance.json`](results/saturday-2026-10-23-provenance.json).

## The data

- 290 Claude Code sessions with at least one answered turn (372 session files), 980 answered turns, 28 days.
- One developer (a co-founder of Saturday Company), working in Italian, on web apps, internal tools, design and ops.
- Almost all turns ran on Claude Opus 5.5.

Small, single-user, single-model. Treat everything below as one data point, which is the reason `sdog share` exists.

## Method

- A turn runs from a user message to the next one. Turns without a reply (the last of a session) are dropped.
- Factors and outcomes are the ones in [`suspiciousdog/signals.py`](suspiciousdog/signals.py). Outcomes are regular
  expressions on the first 250 to 300 characters of the reply, in English and Italian.
- For each factor × outcome with at least 10 turns on both sides: rate with vs without, two-sided Fisher exact test.
  Benjamini-Hochberg across all 84 tests. `real` means q < 0.05.

## Experiment 1: names written from memory (refuted)

`sdog provenance --history`. For every name the agent wrote in code or shell (attributes, calls, flags, compound
identifiers), was it in the context before the write, or defined by the agent itself? Failed tool results that
mention the name next to an error sign ("has no attribute", "unknown option", "not found"…) count as failures.

| | names | then failed | rate |
|---|---:|---:|---:|
| seen first, or defined by the agent | 70,857 | 95 | 0.13% |
| from memory (not seen, not defined) | 19,244 | 14 | 0.07% |

A turn-level check during the first exploration (not shipped as a command) found the same: turns with names from
memory got a correction 1.4% of the time, others 1.6%.

## Experiment 2: "done" without looking (refuted)

Factor `claims done without looking`: files were written, the final message claims success, and nothing was run,
rendered or opened after the last edit.

| outcome | with (27 turns) | without (953) | p |
|---|---:|---:|---:|
| pushback | 3.7% | 3.1% | 0.59 |
| deferral | 3.7% | 1.8% | 0.40 |

## Experiment 3: "Shall I also…?" (found)

Factor `ends offering more work`: the final message ends with an offer of more work as a question.

| outcome | with (49 turns) | without (931) | p | q |
|---|---:|---:|---:|---:|
| pushback | 14.3% (7) | 2.6% (24) | 0.0005 | 0.045 |
| deferral | 10.2% (5) | 1.4% (13) | 0.0013 | 0.056 |
| quick yes | 18.4% (9) | 11.9% (111) | 0.18 | |

Reading the turns with `sdog show`: the "pushback" replies are refusals of the offer ("no, put it on the to-do list
for later", "no, never mind, maybe once the product is validated"), not complaints about the work. Split on 2026-10-12, the pushback effect shows in
both halves: 11.1% vs 2.7% before (27 turns, p = 0.046), 18.2% vs 2.3% after (22 turns, p = 0.003). The factor was defined after reading these same sessions, so
this needs confirming on new data.

## Leads that did not survive the correction

`request sets a role` → interruption (5.1% vs 0.8%, q = 0.21): mostly prompts re-sent after an interruption.
`ends with a question` → pushback and deferral (q = 0.23): overlaps with the offer factor.

## Known limits

- Correlation, not cause.
- Outcomes come from regular expressions on the reply. They miss sarcasm, and count a "no" to an offer as pushback.
- One user and about 1,000 turns: only large effects are visible.
- Subagent transcripts are ignored.
