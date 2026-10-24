"""Which kit items have public names, and may be counted in a share.

A name leaves the machine only if it is on these lists: built-in tools and subagents, MCP servers from public
directories, plugins from public marketplaces. Everything else (your own skills, a connector you named yourself,
a private plugin, any file path) stays home, and is counted only as "private items: N". A test guards it.
"""

import re

# Built-in tools of the agents we read, by their own names.
TOOLS = {
    "Agent", "AskUserQuestion", "Bash", "BashOutput", "Edit", "EnterPlanMode", "ExitPlanMode", "Glob", "Grep",
    "KillShell", "LS", "Monitor", "MultiEdit", "NotebookEdit", "Read", "Skill", "Task", "TodoWrite", "ToolSearch",
    "WebFetch", "WebSearch", "Write",
    "exec_command", "shell", "shell_command", "local_shell", "write_stdin", "apply_patch", "view_image", "web_search",
    "tool_search", "spawn_agent",
    "run_shell_command", "replace", "write_file", "read_file", "read_many_files", "glob", "grep_search",
    "list_directory", "web_fetch", "google_web_search", "invoke_agent", "activate_skill", "save_memory",
}
SUBAGENTS = {"general-purpose", "Explore", "Plan", "statusline-setup", "claude-code-guide", "fork"}
# MCP servers and connectors with public names, compared lowercased with "claude.ai " and separators removed.
MCP = {
    "asana", "atlassian", "box", "canva", "chromedevtools", "claudeinchrome", "claudebrowser", "claudedocs",
    "cloudflare", "cloudflaredeveloperplatform", "context7", "figma", "filesystem", "gamma", "github", "gitlab",
    "gmail", "googlecalendar", "googledocs", "googledrive", "googlesheets", "googleslides", "higgsfield", "hubspot",
    "intercom", "jira", "linear", "memory", "monday", "neon", "notion", "paypal", "playwright", "postgres",
    "puppeteer", "sentry", "sequentialthinking", "slack", "square", "stripe", "supabase", "vercel", "zapier",
}
MARKETPLACES = {"claude-plugins-official", "anthropic-agent-skills", "claude-code-plugins", "anthropics"}
# Skills that ship with Claude Code or claude.ai. A skill of yours never matches: these are the vendor's names.
SKILLS = {
    "simplify", "code-review", "init", "security-review", "loop", "schedule", "claude-api", "update-config",
    "keybindings-help", "fewer-permission-prompts", "run", "plugin-authoring", "workflow-authoring", "dataviz",
    "artifact-design", "artifact-diagramming", "artifact-capabilities", "review", "pr-comments", "statusline",
}
CLAUDE_AI_SKILLS = {
    "algorithmic-art", "brand-guidelines", "built-in-browser", "canvas-design", "chrome-browser", "computer-use",
    "deep-research", "docs", "docx", "frontend-design", "google-workspace", "import-memory", "internal-comms",
    "mcp-builder", "morning", "pdf", "pptx", "skill-creator", "slack-gif-creator", "theme-factory",
    "web-artifacts-builder", "webapp-testing", "xlsx",
}


def _flat(name):
    name = re.sub(r"^claude[_ ]ai[_ ]", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def key(it):
    """The public name of a kit item, or None if it stays home."""
    kind, name = it.kind, it.name
    if kind == "tool":
        return f"tool:{name}" if name in TOOLS else None
    if kind == "subagent":
        return f"subagent:{name}" if name in SUBAGENTS else None
    if kind == "mcp":
        flat = _flat(name)
        return f"mcp:{flat}" if flat in MCP else None
    if kind == "skill":
        if name.startswith("anthropic-skills:") and name.split(":", 1)[1] in CLAUDE_AI_SKILLS:
            return f"skill:{name}"
        return f"skill:{name}" if name in SKILLS else None
    if kind == "plugin":
        m = re.search(r"plugin ([^@\s]+)@([^,\s]+)", it.origin.get("source", ""))
        if m and m.group(1) == name and m.group(2) in MARKETPLACES and re.fullmatch(r"[a-z0-9-]{2,40}", name):
            return f"plugin:{name}@{m.group(2)}"
        return None
    return None


def allowed(public_key):
    """For validating a payload: could this name have come from key()?"""
    kind, _, name = public_key.partition(":")
    if kind == "tool":
        return name in TOOLS
    if kind == "subagent":
        return name in SUBAGENTS
    if kind == "mcp":
        return name in MCP
    if kind == "skill":
        return name in SKILLS or (name.startswith("anthropic-skills:") and name.split(":", 1)[1] in CLAUDE_AI_SKILLS)
    if kind == "plugin":
        plugin, _, market = name.partition("@")
        return market in MARKETPLACES and bool(re.fullmatch(r"[a-z0-9-]{2,40}", plugin))
    return False
