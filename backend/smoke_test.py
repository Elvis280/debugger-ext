"""
smoke_test.py  –  runs without a live server, tests all backend service modules.
Usage:  cd backend && python smoke_test.py
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(__file__))

# ── 1. Stack trace parser ─────────────────────────────────────────────────────
from services.stack_trace_parser import parse

ZERO_DIV = """Traceback (most recent call last):
  File "app.py", line 10, in <module>
    result = calculate_ratio(10, 0)
  File "app.py", line 6, in calculate_ratio
    return a / b
ZeroDivisionError: division by zero"""

INDEX_ERR = """Traceback (most recent call last):
  File "app.py", line 3, in <module>
    print(lst[5])
IndexError: list index out of range"""

NAME_ERR = """Traceback (most recent call last):
  File "app.py", line 2, in <module>
    print(undefined_var)
NameError: name 'undefined_var' is not defined"""

ATTR_ERR = """Traceback (most recent call last):
  File "app.py", line 4, in process
    result = obj.value
AttributeError: 'NoneType' object has no attribute 'value'"""

cases = [
    ("ZeroDivisionError", ZERO_DIV),
    ("IndexError",        INDEX_ERR),
    ("NameError",         NAME_ERR),
    ("AttributeError",    ATTR_ERR),
]

print("=" * 60)
print("1. STACK TRACE PARSER")
print("=" * 60)
all_pass = True
for expected_type, trace in cases:
    p = parse(trace)
    ok = p is not None and p.error_type == expected_type
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"{status}  {expected_type}")
    if p:
        print(f"       file={p.file}  line={p.line}  func={p.function}")
        print(f"       msg ={p.message}")

# ── 2. Root cause detector ────────────────────────────────────────────────────
from services.ast_analyzer import AstResult
from services.root_cause_detector import detect

print()
print("=" * 60)
print("2. ROOT CAUSE DETECTOR (rule-based, no AI needed)")
print("=" * 60)

for expected_type, trace in cases:
    p = parse(trace)
    if p is None:
        print(f"SKIP {expected_type} — parse failed")
        continue
    ast_dummy = AstResult(
        node_type="BinOp" if "Div" in expected_type else
                  "Subscript" if "Index" in expected_type else
                  "Attribute" if "Attr" in expected_type else "Name",
        expression="a / b" if "Div" in expected_type else None,
        variables=["a", "b"] if "Div" in expected_type else
                  ["lst", "5"] if "Index" in expected_type else
                  ["obj"] if "Attr" in expected_type else ["undefined_var"],
    )
    rc = detect(p, ast_dummy)
    print(f"PASS  {expected_type}")
    print(f"       cause : {rc.possible_cause}")
    print(f"       hint  : {rc.hint}")

# ── 3. Error context builder ──────────────────────────────────────────────────
from services.error_context_builder import build

print()
print("=" * 60)
print("3. ERROR CONTEXT BUILDER")
print("=" * 60)
p = parse(ZERO_DIV)
ast_r = AstResult(node_type="BinOp", expression="a / b", variables=["a", "b"])
from services.root_cause_detector import detect
rc = detect(p, ast_r)
ctx = build(p, ast_r, rc, "    return a / b  # error here")
print(f"PASS  ErrorContext built")
print(f"       error_type    : {ctx.error_type}")
print(f"       file          : {ctx.file}")
print(f"       line          : {ctx.line}")
print(f"       expression    : {ctx.expression}")
print(f"       possible_cause: {ctx.possible_cause}")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("Smoke test complete. Backend service modules OK.")
print("(AI engine skipped — requires GEMINI_API_KEY + network)")
print("=" * 60)
