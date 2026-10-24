"""Factors (what the agent did in a turn) and outcomes (how the user answered). English and Italian."""

import re

from .model import ASK, BROWSER, PLAN, SKILL, SUBAGENT, WEB

CLAIMS_DONE = re.compile(
    r"\b(done|fixed|works|working now|resolved|all set|ready|implemented|updated|completed|"
    r"fatto|sistemat|corrett|risolt|funziona|tutto (ok|a posto|pronto)|pronto|verificat|completat|"
    r"ho (tolto|messo|aggiunto|cambiato|rifatto|spostato|sostituito|corretto|sistemato))", re.I)
OFFERS_MORE = re.compile(
    r"(shall i|should i|want me to|do you want|would you like|i can also|next i could|"
    r"procedo|le faccio|lo faccio|la faccio|li faccio|vuoi che|ti va|preferisci|aggiungo|faccio anche|passo a|"
    r"implemento|lo preparo|la preparo)[^?\n]{0,80}\?\s*$", re.I)
ROLE = re.compile(r"(you are an?|act as|sei un|agisci da|agisci come) ", re.I)

PUSHBACK = re.compile(
    r"^(no\b|nope|non (funziona|va\b|è (così|questo|quello|giusto)|mi piace|ho detto|voglio)|ancora|di nuovo|"
    r"that's not|that is not|still\b|again\b)|"
    r"(doesn't work|does not work|not working|still broken|still (not|the same|there)|didn't work|wrong|"
    r"not what i (asked|meant|said)|i (said|told you)|why did you|revert|undo|roll ?back|stop\b|"
    r"non va\b|non funziona|storto|è rimast|rimane (uguale|così)|non si (vede|apre|carica)|sbagliat|"
    r"non è cambiato|uguale a prima|si rompe|si spezza|non compare|non ha funzionato|stesso problema|"
    r"ti avevo|avevo detto|ti ho detto|non ti ho chiesto|perch[eé'] hai|riporta tutto|torna indietro|annulla|"
    r"interrompi|c'è ancora|c'e' ancora|ancora (non|lo stesso|qualcosa))", re.I)
DEFERRAL = re.compile(
    r"(later|not now|not yet|some other time|park (it|that)|put it on the (list|backlog)|backlog|maybe (later|someday)|"
    r"leave it|skip (it|that)|for now no|in futuro|tra le cose da fare|più avanti|piu' avanti|per ora no|"
    r"lasciamo (stare|così|cosi)|non (ora|adesso|serve|importa)|magari (poi|dopo|in futuro)|non ancora|"
    r"un'altra volta|spenderei)", re.I)
QUICK_YES = re.compile(
    r"^(ok|okay|yes|yep|yeah|sure|go|go ahead|do it|ship it|perfect|great|thanks|lgtm|"
    r"sì|si|sisi|vai|procedi|perfetto|ottimo|grazie|va bene|fallo|certo|esatto|bene|pusha|committa|accetta|confermo)\b",
    re.I)


def _claims_done_blind(t):
    return bool(t.files_written) and bool(CLAIMS_DONE.search(t.final[-600:])) and t.looked_after_last_edit() is False


FACTORS = {
    "writes files": lambda t: bool(t.files_written),
    "touches 5+ files": lambda t: len(t.files_written) >= 5,
    "40+ tool calls": lambda t: t.tool_calls >= 40,
    "under 5 tool calls": lambda t: 0 < t.tool_calls < 5,
    "text only": lambda t: t.tool_calls == 0 and bool(t.final.strip()),   # an empty turn is a failure, not text
    "3+ tool errors": lambda t: t.errors >= 3,
    "uses subagents": lambda t: t.uses(SUBAGENT),
    "plan mode": lambda t: t.uses(PLAN),
    "uses skills": lambda t: t.uses(SKILL),
    "web research": lambda t: t.uses(WEB),
    "drives a browser": lambda t: t.uses(BROWSER),
    "asks with a question tool": lambda t: t.uses(ASK),
    "ends with a question": lambda t: t.final.rstrip().endswith("?"),
    "ends offering more work": lambda t: bool(OFFERS_MORE.search(t.final.rstrip()[-200:])),
    "long final answer (300+ words)": lambda t: len(t.final.split()) >= 300,
    "claims done without looking": _claims_done_blind,
    "checks the result after the last edit": lambda t: t.looked_after_last_edit() is True,
    "long request (60+ words)": lambda t: len(t.request.split()) >= 60,
    "short request (<10 words)": lambda t: len(t.request.split()) < 10,
    "request sets a role": lambda t: bool(ROLE.match(t.request)),
    "request includes a screenshot": lambda t: "[Image" in t.request,
    "at night (0-6)": lambda t: bool(t.when) and t.when.hour < 6,
}

OUTCOMES = {
    "pushback": lambda t: bool(PUSHBACK.search(t.reply[:300])),
    "deferral": lambda t: bool(DEFERRAL.search(t.reply[:250])),
    "interruption": lambda t: t.interrupted,
    "quick yes": lambda t: bool(QUICK_YES.match(t.reply)) and len(t.reply.split()) <= 8,
}


def stems(text):
    """Rough word stems, good enough to compare two messages in English or Italian."""
    return {w[:6] for w in re.findall(r"[a-zà-ù]{4,}", text.lower())}


def _declines_offer(t):
    offered = bool(OFFERS_MORE.search(t.final.rstrip()[-200:]))
    return offered and bool(re.match(r"^(no|nope|nah|non (ora|adesso|serve)|dopo|later|not now)\b", t.reply, re.I) or
                            DEFERRAL.search(t.reply[:250]))


def _asks_again(t):
    a, b = stems(t.request), stems(t.reply)
    return len(a) >= 4 and len(b) >= 4 and len(a & b) / len(a | b) >= 0.5


# Outcomes added in 0.2. `sniff` keeps the four above, so its corrections and the shared dataset stay comparable;
# `before-after`, `timeline`, `test` and `show` use these too.
EXTRA_OUTCOMES = {
    "complaint": lambda t: bool(PUSHBACK.search(t.reply[:300])) and not _declines_offer(t),
    "asks again": _asks_again,
}
ALL_OUTCOMES = {**OUTCOMES, **EXTRA_OUTCOMES}
