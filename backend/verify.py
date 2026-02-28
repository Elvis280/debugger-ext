import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.stack_trace_parser import parse
from services.ast_analyzer import AstResult
from services.root_cause_detector import detect
from services.error_context_builder import build

SEP = "-" * 50
results = []

def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append((status, label))
    print(f"[{status}] {label}")

print(SEP)
print("SECTION 1 - Stack Trace Parser")
print(SEP)

t_zdiv = (
    "Traceback (most recent call last):\n"
    "  File \"app.py\", line 10, in <module>\n"
    "    result = calculate_ratio(10, 0)\n"
    "  File \"app.py\", line 6, in calculate_ratio\n"
    "    return a / b\n"
    "ZeroDivisionError: division by zero"
)
t_idx = (
    "Traceback (most recent call last):\n"
    "  File \"app.py\", line 3, in main\n"
    "    print(lst[5])\n"
    "IndexError: list index out of range"
)
t_name = (
    "Traceback (most recent call last):\n"
    "  File \"app.py\", line 2, in main\n"
    "    print(undefined_var)\n"
    "NameError: name 'undefined_var' is not defined"
)
t_attr = (
    "Traceback (most recent call last):\n"
    "  File \"app.py\", line 4, in process\n"
    "    result = obj.value\n"
    "AttributeError: 'NoneType' object has no attribute 'value'"
)

pz = parse(t_zdiv)
check("ZeroDivisionError parsed", pz and pz.error_type == "ZeroDivisionError")
check("ZeroDivisionError line=6", pz and pz.line == 6)
check("ZeroDivisionError func=calculate_ratio", pz and pz.function == "calculate_ratio")

pi = parse(t_idx)
check("IndexError parsed", pi and pi.error_type == "IndexError")
check("IndexError line=3", pi and pi.line == 3)

pn = parse(t_name)
check("NameError parsed", pn and pn.error_type == "NameError")

pa = parse(t_attr)
check("AttributeError parsed", pa and pa.error_type == "AttributeError")

print()
print(SEP)
print("SECTION 2 - Root Cause Detector")
print(SEP)

ast_zdiv = AstResult(node_type="BinOp", expression="a / b", variables=["a", "b"])
rc_zdiv = detect(pz, ast_zdiv)
check("ZeroDivisionError cause mentions 'b'", "b" in rc_zdiv.possible_cause)
check("ZeroDivisionError hint mentions guard", "0" in rc_zdiv.hint or "guard" in rc_zdiv.hint.lower() or "b" in rc_zdiv.hint)

ast_idx = AstResult(node_type="Subscript", expression="lst[5]", variables=["lst", "5"])
rc_idx = detect(pi, ast_idx)
check("IndexError cause detected", len(rc_idx.possible_cause) > 10)

ast_name = AstResult(node_type="Name", expression="undefined_var", variables=["undefined_var"])
rc_name = detect(pn, ast_name)
check("NameError cause mentions variable", "undefined_var" in rc_name.possible_cause)

print()
print(SEP)
print("SECTION 3 - Error Context Builder")
print(SEP)

rc = detect(pz, ast_zdiv)
ctx = build(pz, ast_zdiv, rc, "    return a / b  # error here")
check("ErrorContext.error_type correct", ctx.error_type == "ZeroDivisionError")
check("ErrorContext.line correct", ctx.line == 6)
check("ErrorContext.expression correct", ctx.expression == "a / b")
check("ErrorContext.variables correct", ctx.variables == ["a", "b"])
check("ErrorContext.code_snippet present", len(ctx.code_snippet) > 0)

print()
print(SEP)
fails = [r for r in results if r[0] == "FAIL"]
print(f"RESULT: {len(results) - len(fails)}/{len(results)} checks passed")
if fails:
    print("FAILURES:")
    for _, label in fails:
        print(f"  - {label}")
else:
    print("ALL CHECKS PASSED")
print(SEP)
