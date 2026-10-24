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

## Update, 2026-10-24

One more day of sessions: 296 sessions, 1,009 answered turns, 29 days
([`results/saturday-2026-10-24.json`](results/saturday-2026-10-24.json)). Three more turns ended offering more work,
and none was turned down. "Ends offering more work" → pushback is now 7 of 52 against 25 of 957, p = 0.0008,
q = 0.065: no longer a finding, a lead. Deferral: 5 of 52 against 13 of 957, q = 0.065. Out of the 52, zero drew a
complaint (the 0.2 outcome that leaves out a "no" to an offer), so the reading from `show` stands: offers get
postponed, not resented.

### The kit (0.2)

[`results/saturday-2026-10-24-kit.json`](results/saturday-2026-10-24-kit.json), aggregate counts only, no names.
Among things loaded in 20 or more of 305 sessions: 30 of 114 skills, 19 of 30 MCP servers and 4 of 6 subagents were
used at least once. 60,026 tokens before the first word on average (from the first API call of each session); about
5,399 of them a session on things never used and removable (estimated as characters ÷ 4). The four servers marked
misused failed 16.4%, 7.4%, 6.6% and 6.3% of the time, against 2.7% for all other tool calls.

## Update, 2026-10-24, later: the replies read by a model

[`results/saturday-2026-10-24-classifier.json`](results/saturday-2026-10-24-classifier.json). `sdog classify` had
Claude Haiku label each of the 1,011 replies as complaint, declines, defers, accepts, new request or other, from the
end of the agent's message and the reply (up to 300 characters each).

**Validation.** On the 80 replies in `suspiciousdog/data/labels.jsonl`, in English and Italian, Haiku agreed with the
hand labels on 77, the regular expressions on 58. The 80 were written and labelled by us, for this check: they are
not a random sample of anybody's sessions, so read 96% against 72% as "clearly better", not as a measured accuracy.

**Results**, same test and correction as `sniff`, outcomes from the model's labels:

| factor | outcome | with | without | q |
|---|---|---:|---:|---:|
| ends with a question | quick yes | 43.3% (45 of 104) | 22.1% | < 0.001 |
| ends with a question | declines | 6.7% (7 of 104) | 1.1% | 0.034 |
| ends with a question | complaint | 1.9% (2 of 104) | 8.2% | 0.30 |
| ends offering more work | quick yes | 40.4% (21 of 52) | 23.4% | 0.19 |
| ends offering more work | declines | 7.7% (4 of 52) | 1.4% | 0.19 |
| ends offering more work | complaint | 1.9% (1 of 52) | 7.8% | 0.85 |

A question or an offer at the end of a turn gets a direct answer, yes or no, more often than anything else, and
fewer complaints. The 2026-10-23 "pushback" was the regular expressions counting "no, later" as a complaint. Of the
three ideas we started with, none holds as stated.

## Update, 2026-10-24: pruning our own kit

Applied with `sdog prune` and written in the journal on 2026-10-24: the hyperframes plugin (3 of 260 sessions,
~2,800 tokens a session), its companion skill, and a skill never called in 186 sessions. The before/after, including
the measured context at the start of each session, will be in `sdog journal` once 100 turns have gone by.

