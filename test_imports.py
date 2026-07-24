import sys
sys.path.insert(0, '.')
from config import cfg, corp, experts, TokenBudget
from blackboard import blackboard, internal_notes
from router_engine import route, clear_cache, cache_stats
from tree_engine import execute, get_execution_log, AgentNode
from learn_engine import learn, get_stats

print("=== MAIK Import Test ===")
b = TokenBudget()
print(f"Budget: {b}")
print(f"Mode: {b.mode()}")
print(f"Role at depth 0: {corp.role_at_depth(0)}")
print(f"Role at depth 1: {corp.role_at_depth(1)}")
print(f"Role at depth 2: {corp.role_at_depth(2)}")

expert_name = experts.find_expert("code", "write a sort function")
print(f"Expert for code: {expert_name}")

model = cfg.pick_model("route", "normal")
print(f"Model for route: {model['name']} ({model['model']})")

blackboard.write("test", "hello world", "test_agent", 0.9)
val = blackboard.read("test")
print(f"Blackboard read: {val}")

internal_notes.write("agent1", "this is an internal note", "public", 0.95)
internal_notes.write("agent2", "confidential analysis", "private", 0.8)
all_notes = internal_notes.get_all_public()
print(f"Public notes: {all_notes[:80]}...")

routing = route("write a python function to sort a list", "code", b)
print(f"Route expert: {routing['expert']}")
print(f"Route confidence: {routing['confidence']}")
print(f"Route cached: {routing['cached']}")
print(f"Route budget: {routing['budget']}")

routing2 = route("write a python function to sort a list", "code", b)
print(f"Second route (should be cached): {routing2['cached']}")
print(f"Cache stats: {cache_stats()}")

learn_result = learn(
    problem="write a sort function",
    solution="def sort(lst): return sorted(lst)",
    outcome="success",
    agents_used=[{"role": "code_writer", "id": "agent-1"}],
    confidence=0.9,
    tokens=1500,
    duration_ms=5000
)
print(f"Learn run_id: {learn_result['run_id']}")
print(f"ELO updated: {learn_result['elo_updated']}")
print(f"Total runs: {learn_result['total_runs']}")
print(f"Replay queue: {learn_result['replay_queue_size']}")

stats = get_stats()
print(f"Stats success_rate: {stats['success_rate']:.2f}")
print(f"Stats avg_confidence: {stats['avg_confidence']:.2f}")

print(f"\n=== Testing offline execute (no API key) ===")
offline_budget = TokenBudget(total=50000)
result = execute("hello world test", "general", offline_budget, depth=0)
print(f"Execute solution (first 80 chars): {result['solution'][:80]}...")
print(f"Execute confidence: {result['confidence']}")
print(f"Execute agents count: {len(result['agents_used'])}")
print(f"Execute budget: {result['budget']}")
print(f"Budget mode: {result['budget_mode']}")
print(f"Has notes: {result.get('notes') is not None}")
print(f"Has chat_log: {result.get('chat_log') is not None}")
print(f"Has agents_log: {result.get('agents_log') is not None}")

print(f"\n=== ALL TESTS PASSED ===")
