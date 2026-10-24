"""Why a tool call failed, from the text of its error. Each kind points to a different fix."""

import re

KINDS = (
    ("blocked", r"auto mode classifier|denied by .{0,40}(policy|classifier|hook)|blocked by .{0,20}hook"),
    ("setup", r"none has been selected|no browser|not connected to|extension (is )?not (installed|connected|running)|"
              r"select_browser|switch_browser|no (tab|page) (is )?(open|selected)|call tabs_context|createifempty"),
    ("auth", r"unauthori[sz]ed|forbidden|\b40[13]\b|not authenticated|authenticat|access denied|token (has )?expired|"
             r"log ?in (again|required)|credential|permission denied"),
    ("not loaded", r"no such tool|tool .{0,40}not (found|available)|not available|inputvalidationerror.{0,40}deferred|"
                   r"must be loaded|toolsearch"),
    ("wrong arguments", r"inputvalidationerror|input validation error|invalid_input|\binvalid\b|required (property|parameter|"
                        r"field|argument)|is required|must be (a|an|one of|of type)|expected .{0,30}(got|received)|"
                        r"unknown (parameter|argument|option|field)|unrecognized|validation (error|failed)|schema"),
    ("wrong target", r"(tab|page|frame|target|element|ref|node|session)\b.{0,40}(closed|detached|not found|no longer|"
                     r"invalid|stale|does not exist|doesn't exist)|browser-internal|unparseable url|exceeds viewport|"
                     r"couldn't determine which page|showing error page|no visible elements|does not contain visible"),
    ("bad code", r"syntax error|relation .{0,60} does not exist|column .{0,60} does not exist|\berror: |sqlstate|"
                 r"violates .{0,30}constraint|duplicate key|typeerror|referenceerror|execution error|is not defined|"
                 r"cannot read propert"),
    ("not found", r"not found|\b404\b|does not exist|doesn't exist|no such (file|directory|project|deployment|resource)"),
    ("timeout", r"timed? ?out|deadline exceeded|etimedout"),
    ("server", r"\b5\d\d\b|internal (server )?error|econnrefused|connection (refused|reset|closed)|disconnected|"
               r"not connected|service unavailable|rate limit|too many requests|\b429\b"),
)
COMPILED = [(name, re.compile(pattern, re.I)) for name, pattern in KINDS]

FIX = {
    "auth": "configuration: reconnect or re-authorize it",
    "not loaded": "the agent calls it before loading it: a one-line rule or the skill can fix this",
    "wrong arguments": "the agent guesses the parameters: a rule or a skill with the right call shapes helps",
    "wrong target": "the agent acts on a tab, page or element that is gone or wrong: re-read the state first",
    "blocked": "the safety layer stopped it: working as intended, not the tool's fault",
    "setup": "the tool needs a first step (pick the browser, open a tab): one line in your instructions fixes it",
    "bad code": "the agent writes queries or scripts without reading the schema or the page first",
    "not found": "the agent guesses ids, paths or names: look them up first",
    "timeout": "slow or stuck calls: smaller requests, or the server is struggling",
    "server": "the server or the network, usually not the agent",
    "other": "",
}

SHORT = {
    "auth": "reconnect it", "not loaded": "called before it was loaded", "wrong arguments": "guessed parameters",
    "wrong target": "acts on gone or wrong pages", "bad code": "queries and scripts written blind",
    "not found": "guessed ids and paths", "timeout": "slow calls", "server": "the server's side",
    "setup": "a missing first step", "blocked": "your safety layer at work", "other": "",
}


def classify(text):
    for name, pattern in COMPILED:
        if pattern.search(text or ""):
            return name
    return "other"
