# Phase H — Organization Layer (Org Chart, Model Binding, System Prompts)

Design spec. Built as new modules in `maik_kernel/` + tests. Backend-first, test-driven.

## Features (from user requirements)

### H1 — OrgChartEngine (`org_chart.py`)
- Fully user-configurable hierarchy: any number of CEOs, managers per CEO, agents per manager.
- Default factory: classic 12-CEO council still available; `orgchart.light()` = 2 CEOs;
  custom: `OrgChart.from_spec()` with JSON `{"name","role","reports":[]}` or simple
  `build(council=[(n, domain, tier, ...)], agents_per_ceo=N)`.
- Each node has: id, name, role, domain, level (ceo/manager/agent/subagent), parent,
  budget, model_binding, system_prompt_id, powers (capabilities).
- Hierarchy traversal: `descendants(node)`, `chain(node)` (path to root), `siblings`, `reportees`.
- CEO oversight: `visible_notes(node, viewer)` — CEOs see hidden notebooks too; agents see only public.
- Persistence: `to_json/from_json` (chain of custody with org chart version).
- Dynamic deployment: `ceo.add_manager(name, ...)`, `add_agent(manager, ...)`,
  `add_subagent(agent, ...)` — with permission check (only ceo/manager roles deploy below them).

### H2 — ModelBinding (`model_binding.py`)
- Global model catalog: provider/model pairs + tiers. `ModelCatalog: available_tiers -> [models]`.
- Per-node binding: each org node binds a concrete `provider/model` (overrides tier default).
- User controls: `set_binding(node_id, "anthropic/claude-3.5-haiku")`, `unset_binding`, `list_bindings`.
- Executor uses binding when present, else tier default (existing behavior preserved).

### H3 — PromptSystem (`prompt_system.py`)
- `SystemPrompt` documents: id, owner_node_id, level, text, editable flag.
- Levels: org default, ceo default, role template, per-node override. Resolution order:
  per-node override -> role template -> ceo default -> org default.
- Role template library: code_writer, code_tester, code_reviewer, code_debugger,
  idea_verifier, idea_generator, options_provider, research_explorer, synthesizer, etc.
- **PromptBuilder**: given (role, mission, access_powers, constraints) builds a detailed
  system prompt; `build_role_prompt(role, ...)`, `describe_prompt_guidelines(role)`
  gives the CEO guidance text about what a good system prompt for that role looks like.
- User-editable: `update_prompt(node_id, text)` (user owns this action; CEO can set for reports).
- Self-awareness injection: every prompt gets an automatic `__SELF__` block appended:
  "You are {name}, role {role}, level {level}, reporting to {manager}; your capabilities: {...};
  your budget: {x}; your access: {...}" — time awareness via injected timestamp/UTC note.

### H4 — NotebookSystem (`notebooks.py`)
- Per-agent dual notebooks: `public` (chain-of-thought shared with reports/peers per policy)
  and `hidden` (private; only self + chain-of-command CEOs).
- Operations: write/read per notebook; CEO `read_hidden(node)`; agent `write_public/hidden`.
- Thread-safe, JSONL append, persisted under MAIK_DATA_DIR.

### H5 — CommandRunner (`command_runner.py`)  [sandboxed, behind a permission flag]
- Permission-gated command execution: each node has `powers`: file_create, command_run,
  screen_read, browser_automation (all OFF by default except CEO).
- `CommandRunner.execute(node, cmd, kind="shell")` — kind: shell | file | screen | browser(external).
- By default only shell+file for CEO/manager; screen/browser return
  "requires automation operator module (Phase I)" pointer.
- Dry-run mode default; `allow=True` enables real execution.

### H6 — CLIDeployer (`cli_deployer.py`)
- Registry of external agent CLIs: gemini-cli, claude-code, opencode, aider, openai codex...
- `CLIDeployer.probe(tool)` checks presence (which/shutil).
- `spawn(tool, task)` launches the CLI as a child process worker with a task prompt,
  captures output, applies timeout.
- CEO uses: `deploy("claude-code", "refactor this file...")`.

### Integration
- `maik status` gains an `org` view; new CLI subcommand `maik org` (status, add-manager,
  add-agent, bind-model, set-prompt, notebook, deploy).
- Executor: when config carries an OrgChart, route decision expands to the full node chain
  (CEO -> manager -> agent), each level appends its system prompt segment (time-aware),
  final agent's bound model drives the ladder call. Without OrgChart, existing 12-CEO
  behavior is unchanged (backward compatibility).
- Version bump: 3.0.0 -> 3.1.0.

## Tests
- test_org_chart.py, test_model_binding.py, test_prompt_system.py, test_notebooks.py,
  test_command_runner.py, test_cli_deployer.py, test_executor_org.py
- Run under MAIK_STUB=1. All must pass before push.

## Notes
- No paid keys required — everything testable offline.
- Key hygiene: no keys in new modules; .env handles them as before.
