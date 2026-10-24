<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <img src="assets/logo.png" alt="SuspiciousDog, looking at your plugins sideways" width="260">
  </picture>
</p>

<h1 align="center">SuspiciousDog</h1>

<p align="center"><b>He doesn't trust your plugins. He's read your transcripts.</b></p>

<p align="center">
  <a href="https://github.com/Saturday-Company/SuspiciousDog/actions/workflows/test.yml"><img src="https://github.com/Saturday-Company/SuspiciousDog/actions/workflows/test.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Gemini%20CLI%20%C2%B7%20Aider%20%C2%B7%20anything-555" alt="works with">
  <img src="https://img.shields.io/badge/dependencies-0-2da44e" alt="zero dependencies">
  <img src="https://img.shields.io/badge/your%20data-stays%20home-2da44e" alt="local only">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT"></a>
</p>

<p align="center"><a href="README.it.md">Italiano</a></p>

<p align="center">
  <img src="assets/hypotheses.svg" alt="Three ideas tested on 1,009 real turns: all three died" width="820">
</p>

Every plugin, skill, hook and line of `CLAUDE.md` or `AGENTS.md` you give an AI agent is a hypothesis:
*if the agent does X, my work goes better.* Nobody tests it. You install it because it sounds smart.

Your agent has been keeping notes the whole time. Every turn of every session is on disk, along with what you
said right after. That's the experiment, already run. SuspiciousDog reads it.

## You know him

Sits in the corner. Says nothing when you install the plugin everyone's posting about. Two weeks later he walks
over with a printout. It changed nothing. He was right. He's always right. He read the logs.

## The numbers

On 23/10 we pointed him at our own sessions: 290 Claude Code sessions, 980 turns, 28 days. One developer, one model.
Real data, the same counts anyone can rebuild with `sdog sniff`. We handed him our three best ideas.

**Names written from memory. Dead.** When an agent writes a method, flag or column it never saw in the context, it
comes from the model's memory. That's where hallucinations live, surely. Of 90,101 names, the 19,244 written from
memory broke a tool call 0.07% of the time. The ones it had seen: 0.13%. The model's memory is fine. Our idea wasn't.

**"Done", without looking. Dead.** The agent says it's finished without running, rendering or opening anything
after its last edit. Happened in 27 turns. Pushback afterwards: 3.7%, against 3.1% everywhere else. Nothing.

**"Shall I also…?" Real.** The agent ends the turn offering more work. The answer is pushback 14.3% of the time,
against 2.6% (q = 0.045). `sdog show` explains it: it's not anger. It's *"no, put it on the list for later"*.
The same turns get a deferral 10.2% of the time against 1.4%, just short of the bar.

Two ideas out of three died in an evening. Without measuring, we'd have shipped both as hooks to every project
we have. The one that survived, survived by a whisker.

**A day later it didn't.** Three more offers on 24/10, none turned down: 7 in 52, q = 0.065. Back to *maybe*. The
complaint outcome added in 0.2 says the same thing louder: of 52 offers, 0 drew a complaint. People say "later" to
them, not "wrong". One developer's whisker is not a finding. (The chart at the top is the 24/10 count; its third card is read by a model, see below.)

**Then a model read the replies.** The patterns that recognise "pushback" are cheap and a little dim: to them,
*"no, later"* reads like a complaint. In 0.2 a small model can read the replies instead (`sdog classify`, off unless
you run it). On 80 replies we labelled by hand it got 77 right; the patterns got 58. Read by Haiku, the offer of more
work isn't a bad habit at all: it gets a quick yes 40% of the time against 23%, and a plain no 7.7% against 1.4%.
Ending with a question does the same, more clearly: a yes 43% against 22%, a no 6.7% against 1.1%, both real.
Questions get answered, that's all. Our one surviving idea was the patterns misreading "no".

Three ideas, three wrong. That's one developer, and effects this small need more than one developer to be sure.
**That's where you come in.**

## Help the pack

```bash
sdog share
```

It prints everything it would send, and waits for your yes. Then it opens a GitHub issue under your account with
this, and only this:

| Sent | Never sent |
|---|---|
| which agents, how many sessions | your prompts, your agent's replies |
| how many turns, over how many days | file names, paths, project names |
| for each factor × outcome: four integers | code, commands, anything you typed |
| for public plugins, MCP servers and built-in tools: sessions loaded, used, calls, failures, weight | your own skills, private plugins, connectors you named, your CLAUDE.md: those are one number, "private items" |

The factor names come from SuspiciousDog's own list, public names from fixed lists, and a test fails the build if
anything else could get in ([PRIVACY.md](PRIVACY.md)). Every shared result is public, so the dataset belongs to
everyone who adds to it. A GitHub Action adds the shares up into the pack page, which goes live with the first
shares: which agent habits go with worse answers, on which agents, and for every public plugin and MCP server how
often people who load it actually use it, and how often it fails. Marketplaces show stars. This shows use.

## Ten seconds

```bash
pipx install git+https://github.com/Saturday-Company/SuspiciousDog
sdog demo        # synthetic sessions, to see what it looks like
sdog             # your own: the checkup
sdog kit         # what you load, what you use, what fails
```

<p align="center"><img src="assets/demo.svg" alt="sdog demo output on synthetic sessions" width="820"></p>

The demo runs on made-up sessions with one planted effect, and says so. `real` means the result survives the
correction for every test he ran. `maybe` is a lead. `vibes` is vibes.

## Your kit

*New in 0.2.* Every plugin, skill, MCP server and line of CLAUDE.md you add was a bet. He checks the bets. Claude
Code records the most; Codex, Gemini CLI and Aider record less, and `sdog doctor` says what each one can't show.

```bash
sdog                # the checkup: one screen, what weighs, what fails, what changed, what the agent keeps doing
sdog kit            # everything you added: what it weighs, what you use, what fails
sdog kit gamma      # one item in detail, and how to drop it
```

Every session writes down what it loaded into the context before you typed a word (the skill list, the subagent
list, the instructions of every MCP server, your CLAUDE.md files) and what it actually called. He lines them up.

<p align="center"><img src="assets/kit.svg" alt="Our sessions: 60,026 tokens before the first word, 5,399 of them on things never used. 30 of 114 skills used." width="820"></p>

On our own 305 sessions: 60,000 tokens before the first word, on average. Of the 114 skills loaded in 20 or more
sessions, 30 were ever used. About 5,400 tokens a session went to things we had never used once, and a connector
loaded in 266 sessions had been called zero times. Four MCP servers failed more than twice as often as everything else.

Every item gets a verdict: **ballast** (loaded in 20+ sessions, never used), **rare** (under 5% of the sessions that
load it), **elsewhere** (used in one project, loaded in all of them), **misused** (fails far more often than your other
tools), **earns its place**, or **too new to judge**. Built-in pieces you can't remove are counted apart. Token weights
are estimates (characters ÷ 4) and say so.

### Prune, with an undo

```bash
sdog prune          # proposals, applied only on your yes
sdog undo           # put the last one back
sdog journal        # everything changed or noted, and what happened after
```

He proposes, you pick. What he can do himself goes through the agent's own commands (`claude plugin disable`,
`claude mcp remove`, `gemini mcp disable`) or moves a skill into an attic, or into the one project that uses it.
Something you use now and then that costs under 100 tokens a session he leaves alone: a skill you need once a month
is worth its line. Every change goes into a
journal with its undo. Connectors and skills that live on claude.ai he can't touch: he tells you where to click,
and `sdog note "disconnected Gamma"` puts it in the journal. Two weeks later `sdog journal` says whether anything got
worse, and how much lighter the start of a session really got, measured from the API usage, not estimated.

We ran it on ourselves on 24/10: a video plugin used in 3 sessions out of 260 (~2,800 tokens each time), its
companion skill, and a 3D skill nobody had ever called. Three lines in the journal. We'll report what they did.

### When it changed, and what it did

```bash
sdog timeline       # every day your kit changed, found in the transcripts, with your answers before and after
sdog kit vercel     # where a server fails, and why: auth, wrong arguments, bad code, wrong target, timeouts…
sdog rules          # beta: rules in your CLAUDE.md that your corrections keep repeating
```

Nobody writes down "installed a plugin on the 6th". The sessions do: the first one that lists it, the day a
CLAUDE.md came in with different content, the day the subagents started answering from another model. `timeline`
finds those days on its own and compares the 14 days around each, with the same tests and corrections as `sniff`.
Under 100 turns on either side it says *too early* and nothing else. Changes on the same day are one change: they
can't be told apart.

Failures get a reason, and the reason says who should fix it. *Auth* is your config. *Wrong arguments*, *bad code*,
*not found* and *wrong target* are the agent guessing, and a one-line rule usually fixes them. *Blocked* is your
safety layer doing its job. On our data, half of Vercel's failures were 403s, and two thirds of Supabase's were SQL
errors, like querying a table that doesn't exist.

### The whole thing on one page

```bash
sdog report --open  # one static HTML file on your disk: the kit, the timeline, the failures, the habits
```

No server, no network, nothing loaded from anywhere. It holds your project names and error messages, so it stays
yours; `sdog share` is the thing for sharing.

## For the agents

The agent is the one who starts from zero every session. He doesn't.

```bash
sdog brief          # what your past sessions say, in a few lines, every line on counts (~150-250 tokens)
sdog check "Before running SQL on Supabase, read the table schema"
sdog mcp            # the same answers as an MCP server: audit_setup, check_rule, evidence
```

`check` is for the moment someone says *"add a rule"*. Is something like it already loaded? Do your corrections
say it? Do the tools it names fail for a reason it would fix? It answers **already said**, **supported**, **weak**
or **no evidence**, with the numbers, and what the rule would cost in every session. On ours, the Supabase rule
above comes back *supported*: 6% of 1,039 calls fail, most of them SQL written blind. "Never use emoji in commit
messages" comes back *no evidence*.

The Claude Code plugin registers the MCP server, so the agent can ask by itself. We tried it in a real session:
asked to add that rule, Claude called `check_rule` first, then wrote the rule and told us why.

`brief` is the agent's memory, built from the data instead of from hunches: the habits that go with worse answers
in your sessions, and the tools that keep failing with what to do about each (*"re-read the page state before
acting"*, *"auth: don't retry, tell the user"*). Two optional hooks, off until you turn them on:

```bash
sdog hooks on brief      # the brief at the start of every session (~200 tokens, every session)
sdog hooks on sentinel   # once a week, one line on what a change of yours did
```

Both are journaled; `sdog undo` turns them off again. And he measures himself: SuspiciousDog shows up in its own
kit, and if he's ballast for you, the checkup says so.

## Commands

| | |
|---|---|
| `sdog` | the checkup: one screen with what matters |
| `sdog sniff` | every factor against every outcome (`--agent`, `--project`, `--outcome`, `--all`) |
| `sdog kit [NAME]` | what you added to your agent: weight, use, failures, a verdict (`--kind`, `--all`, `--json`) |
| `sdog timeline` | every change to your kit, found in the transcripts, with before/after (`--days`, `--all`) |
| `sdog rules` | beta: rules your corrections keep repeating |
| `sdog prune` / `undo` / `note` / `journal` | lighten the kit on your yes, put things back, log what you changed by hand, see what it did |
| `sdog report` | everything on one HTML page, on your disk (`--open`, `--out`) |
| `sdog brief` | for agents: what your past sessions say, in a few lines (`--here`, `--json`) |
| `sdog check "RULE"` | before adding a rule: already said, supported, weak or no evidence (`--json`) |
| `sdog mcp` | the MCP server: `audit_setup`, `check_rule`, `evidence` |
| `sdog hooks on\|off brief\|sentinel` | optional hooks, off by default, each with an undo |
| `sdog classify` | optional: a small model reads the replies (`--validate`, `--backend claude\|anthropic\|openai`) |
| `sdog doctor` | what he can read, and whether the transcript format changed under him |
| `sdog show "ends offering more work" --outcome deferral` | the actual turns behind a number. Read them before you believe anything. |
| `sdog test "t.tool_calls > 40"` | your own hypothesis, as a Python expression over a turn |
| `sdog before-after CLAUDE.md` | did that rule help? Compares outcomes before and after its last commit (or any date). |
| `sdog share` | counts to the public dataset, after you've seen them |
| `sdog provenance` | experiment 1 on a session: names on evidence, names from memory |
| `sdog agents` / `sdog format` | what he can read, and the open format for everything else |

## Install

**Any agent, any OS:** `pipx install git+https://github.com/Saturday-Company/SuspiciousDog`, then `sdog`.
Python 3.10+, no dependencies.

**Claude Code plugin** (adds `/suspiciousdog:sniff`, a skill and the MCP server, no pip needed):

```bash
claude plugin marketplace add Saturday-Company/SuspiciousDog
claude plugin install suspiciousdog@suspiciousdog
```

**Codex, Gemini CLI, Cursor, OpenCode and the rest:** install with pipx and copy [`AGENTS.md`](AGENTS.md) into
your project, or point the agent at [`skills/suspiciousdog/SKILL.md`](skills/suspiciousdog/SKILL.md). Details per
agent in [INSTALL.md](INSTALL.md).

## What he reads

| Agent | Where | Turns | Kit |
|---|---|---|---|
| Claude Code | `~/.claude/projects/*/*.jsonl` | stable, tested on real sessions | everything |
| Codex CLI | `~/.codex/sessions/**/rollout-*.jsonl` | beta | skills, AGENTS.md, used MCP servers and why they fail |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.jsonl` | beta | GEMINI.md files, server notes, used tools and skills |
| Aider | `.aider.chat.history.md` | beta | read-only files (conventions), models |
| Anything else | the open JSONL format, `sdog format` | stable | if you write `loaded` events |

Beta readers are built from each agent's source code and tested on fixtures, not yet on real sessions. If one
misreads yours, open an issue with the shape (not the content) of the file.

## How it works

1. Sessions become **turns**: your message, everything the agent did, and your next message.
2. Each turn gets **factors** (it wrote files, used subagents, ended with an offer, claimed done without looking,
   ran 40+ tools…) and **outcomes** (your reply was pushback, a deferral, a quick yes, or you interrupted it).
3. For every factor and outcome: outcome rate with the factor vs without, Fisher's exact test, then
   Benjamini-Hochberg across all tests, because with 80 tests a few small p-values are just luck.
4. `show` puts the real turns next to every number. Outcomes are read from the text of your reply, so a "no" to an
   offer counts as pushback. `sdog classify` has a small model read them instead, if you want it to. The numbers say
   where to look; the turns say what happened.

## FAQ

**Is it causation?** No. He tells you where to look. You look.

**Does anything leave my machine?** Only when you run `sdog share` and say yes, and only counts. Or when you run
`sdog classify`, which sends the end of each agent message and your reply to the model you pick, after telling you
how much.

**It found nothing.** Good. Your agent is fine, or you need more sessions. Either way, no new plugins today.

**My agent isn't listed.** Six kinds of JSON lines. `sdog format`.

**Can I add a factor?** `sdog test` takes any expression. If it's worth keeping, open a PR to `signals.py`.

**Why "SuspiciousDog"?** Look at him.

## License

MIT. Made by [Saturday Company](https://saturdaycompany.it). Our own counts are in [`results/`](results/) and the
methods in [RESULTS.md](RESULTS.md).
