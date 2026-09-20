"""Code Explanation Tutor — inspect a .py file or paste source via AST."""

import ast
import streamlit as st


def parse_source(source: str):
    try:
        return ast.parse(source), None
    except SyntaxError as exc:
        return None, exc


def summarize_imports(tree):
    rows = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            rows.append((node.lineno, "import", ", ".join(a.name for a in node.names)))
        elif isinstance(node, ast.ImportFrom):
            rows.append((node.lineno,
                         f"from {node.module or ''} " + ("." * (node.level or 0)),
                         ", ".join(a.name for a in node.names)))
    return rows


def summarize_functions(tree):
    rows = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            params = [p.arg for p in node.args.args]
            if node.args.vararg:
                params.append(f"*{node.args.vararg.arg}")
            params.extend(p.arg for p in node.args.kwonlyargs)
            if node.args.kwarg:
                params.append(f"**{node.args.kwarg.arg}")
            doc = ast.get_docstring(node) or "—"
            rows.append((node.lineno, node.name, "(" + ", ".join(params) + ")", doc))
    return rows


def summarize_classes(tree):
    rows = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [(m.name, m.lineno) for m in node.body
                       if isinstance(m, ast.FunctionDef)]
            doc = ast.get_docstring(node) or "—"
            rows.append((node.lineno, node.name, methods, doc))
    return rows


def call_names(node, user_funcs):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in user_funcs:
            return [node.func.id]
    return []


def collect_calls(node, user_funcs):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    names = call_names(node, user_funcs)
    for child in ast.iter_child_nodes(node):
        names.extend(collect_calls(child, user_funcs))
    return names


def collect_statements_calls(stmts, user_funcs):
    return [n for st in stmts for n in collect_calls(st, user_funcs)]


def format_signature(node):
    params = [p.arg for p in node.args.args]
    if node.args.vararg:
        params.append(f"*{node.args.vararg.arg}")
    params.extend(p.arg for p in node.args.kwonlyargs)
    if node.args.kwarg:
        params.append(f"**{node.args.kwarg.arg}")
    sig = f"def {node.name}({', '.join(params)})"
    if node.returns:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def get_parameters(node):
    return [p.arg for p in node.args.args]


def _names_from_target(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [e.id for e in target.elts if isinstance(e, ast.Name)]
    return []


def get_assignments(node):
    names = set()
    for st in ast.walk(node):
        if isinstance(st, ast.Assign):
            for t in st.targets:
                names.update(_names_from_target(t))
        elif isinstance(st, ast.AugAssign):
            names.update(_names_from_target(st.target))
        elif isinstance(st, ast.NamedExpr):
            names.update(_names_from_target(st.target))
    return sorted(names)


def returns_value(node):
    for st in ast.walk(node):
        if isinstance(st, ast.Return) and st.value is not None:
            return True
    return False


def cyclomatic_complexity(node):
    return 1 + sum(1 for st in ast.walk(node)
                   if isinstance(st, (ast.If, ast.For, ast.While,
                                       ast.ExceptHandler, ast.BoolOp)))


def called_by(func_name, calls):
    return sorted(f for f, callee in calls.items() if func_name in callee)


def build_summary(node, calls):
    parts = []
    kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
    params = get_parameters(node)
    parts.append(f"{kind} `{node.name}` takes {'no parameters' if not params else ', '.join(params)}")
    assigns = get_assignments(node)
    if assigns:
        parts.append(f"assigns {', '.join(assigns)}")
    callees = calls.get(node.name, [])
    if callees:
        parts.append(f"calls {', '.join('`' + c + '`' for c in callees)}")
    if returns_value(node):
        parts.append("returns a value")
    else:
        parts.append("does not return a value")
    parts.append(f"has cyclomatic complexity {cyclomatic_complexity(node)}")
    return " and ".join(parts) + "."


def build_call_graph(tree):
    user_funcs = {n.name for n in ast.iter_child_nodes(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    calls = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls[node.name] = collect_statements_calls(node.body, user_funcs)
    return user_funcs, calls


def find_main_block(tree):
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__" and isinstance(test.ops[0], ast.Eq)
                    and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value == "__main__"):
                return node
    return None


def describe_stmt(st):
    return {ast.Expr: "expression statement", ast.Assign: "assignment",
            ast.If: "if statement", ast.For: "for loop", ast.While: "while loop",
            ast.With: "with block", ast.Try: "try block"}.get(type(st), type(st).__name__)


def find_entry(tree, user_funcs):
    main_if = find_main_block(tree)
    if main_if:
        return {"type": "main", "label": "if __name__ == '__main__':",
                "calls": collect_statements_calls(main_if.body, user_funcs)}
    for st in ast.iter_child_nodes(tree):
        if not isinstance(st, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                               ast.ClassDef, ast.Assign, ast.AnnAssign,
                               ast.AugAssign, ast.Delete)):
            return {"type": "statement",
                    "label": f"First executable: {describe_stmt(st)}",
                    "calls": collect_statements_calls([st], user_funcs)}
    return {"type": "none", "label": "No entry point found", "calls": []}


def render_call_tree(root_label, root_calls, calls, visited):
    lines = [root_label]
    for child in root_calls:
        if child in visited:
            lines.append(f"    └─ {child} (cycle)")
            continue
        lines.append(_expand(child, calls, visited, "    "))
    return "\n".join(lines)


def _expand(name, calls, visited, prefix):
    visited.add(name)
    lines = [prefix + "└─ " + name]
    for child in calls.get(name, []):
        if child in visited:
            lines.append(prefix + "    └─ " + child + " (cycle)")
        else:
            lines.append(_expand(child, calls, visited, prefix + "    "))
    return "\n".join(lines)


def main():
    st.set_page_config(page_title="Code Explanation Tutor", layout="wide")
    st.title("Code Explanation Tutor")

    col_upload, col_paste = st.columns(2)
    source = None
    validation_error = None

    with col_upload:
        uploaded = st.file_uploader("Upload a .py file", type=["py"])
        if uploaded:
            if not uploaded.name.lower().endswith(".py"):
                validation_error = f"{uploaded.name} is not a Python file"
            else:
                try:
                    content = uploaded.read().decode("utf-8")
                except UnicodeDecodeError:
                    validation_error = f"{uploaded.name} is not valid UTF-8 text"
                else:
                    if not content.strip():
                        validation_error = f"{uploaded.name} is empty"
                    else:
                        source = content
                        st.caption(f"Loaded: {uploaded.name}")

    with col_paste:
        pasted = st.text_area("Or paste Python source", height=180)
        if pasted.strip():
            source = pasted

    if validation_error:
        st.error(validation_error)
        return

    if not source:
        st.info("Upload a .py file or paste Python source to begin.")
        return

    tree, err = parse_source(source)
    if err:
        st.error(f"Not valid Python — SyntaxError on line {err.lineno}: {err.msg}")
        return

    imports = summarize_imports(tree)
    functions = summarize_functions(tree)
    classes = summarize_classes(tree)

    st.markdown("## Inventory")
    ic, fc, cc = st.columns(3)
    ic.metric("Imports", len(imports))
    fc.metric("Top-level functions", len(functions))
    cc.metric("Classes", len(classes))

    if imports:
        st.markdown("### Imports")
        st.table([{"Line": l, "Type": t, "Names": n} for l, t, n in imports])

    if functions:
        st.markdown("### Functions")
        st.table([{"Line": l, "Name": n, "Parameters": p, "Docstring": d}
                  for l, n, p, d in functions])

    if classes:
        st.markdown("### Classes")
        class_rows = []
        for lineno, name, methods, doc in classes:
            method_str = ", ".join(f"{m} (L{ml})" for m, ml in methods) or "—"
            class_rows.append({"Line": lineno, "Class": name,
                               "Methods": method_str, "Docstring": doc})
        st.table(class_rows)

    # Execution Flow
    st.markdown("## Execution Flow")
    user_funcs, calls = build_call_graph(tree)
    entry = find_entry(tree, user_funcs)

    called_set = set(entry["calls"])
    for callee_list in calls.values():
        called_set.update(callee_list)
    uncalled = sorted(user_funcs - called_set)

    st.markdown("### Entry Point")
    if entry["type"] == "main":
        st.success("Entry point: `if __name__ == '__main__':` block")
    elif entry["type"] == "statement":
        st.info(entry["label"])
    else:
        st.warning("No `if __name__ == '__main__'` block and no module-level executable statement found.")

    st.markdown("### Call Graph")
    visited = set()
    tree_text = render_call_tree(entry["label"], entry["calls"], calls, visited)
    st.code(tree_text)

    if uncalled:
        st.markdown("### Uncalled Functions")
        st.warning("Defined but never called: " + ", ".join(f"`{f}()`" for f in uncalled))
    else:
        st.markdown("### Unused Functions")
        st.success("No unreachable functions — every definition is called.")

    # Q&A
    st.markdown("## Q&A")
    func_nodes = {n.name: n for n in ast.iter_child_nodes(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    q = st.radio("Ask a question", [
        "Where does execution start?",
        "What does this function do?",
        "How does data flow through this program?",
    ])
    st.markdown(f"**{q}**")

    if q == "Where does execution start?":
        if entry["type"] == "none":
            answer = "No entry point found — no `if __name__ == '__main__':` block and no module-level executable statement."
        else:
            parts = [f"Execution starts at the `{entry['label']}` block."]
            if entry["calls"]:
                parts.append("It begins by calling: " + ", ".join(f"`{c}`" for c in entry["calls"]) + ".")
            else:
                parts.append("It calls no functions directly.")
            answer = " ".join(parts)
        st.info(answer)

    elif q == "What does this function do?":
        if not func_nodes:
            st.info("No functions defined in this source.")
        else:
            target = st.selectbox("Which function?", list(func_nodes.keys()), key="qa_func")
            st.info(build_summary(func_nodes[target], calls))

    else:  # data flow
        parts = ["Data flows between functions via parameters and return values."]
        if entry["type"] != "none" and entry["calls"]:
            parts.append("The entry point calls " + ", ".join(f"`{c}`" for c in entry["calls"]) + ".")
        else:
            parts.append("There is no callable entry point.")
        parts.append(f"{len(user_funcs)} function(s) are defined here.")
        if uncalled:
            parts.append("Never called: " + ", ".join(f"`{u}`" for u in uncalled) + ".")
        else:
            parts.append("All functions are reached through the call graph.")
        st.info(" ".join(parts))

    # Function inspector
    st.markdown("## Function Inspector")
    if func_nodes:
        choice = st.selectbox("Select a function", list(func_nodes.keys()))
        node = func_nodes[choice]
        sig = format_signature(node)
        doc = ast.get_docstring(node) or "—"
        callees = calls.get(choice, [])
        callers = called_by(choice, calls)
        params = get_parameters(node)
        assigns = get_assignments(node)
        ret = returns_value(node)
        cc = cyclomatic_complexity(node)

        st.markdown("### Signature")
        st.code(sig)
        st.markdown("### Docstring")
        st.text(doc)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Calls")
            st.write(callees if callees else "none")
            st.markdown("#### Parameters")
            st.write(params if params else "none")
            st.markdown("#### Variables assigned")
            st.write(assigns if assigns else "none")
        with c2:
            st.markdown("#### Called by")
            st.write(callers if callers else "none (definition)")
            st.markdown("#### Returns a value?")
            st.write("yes" if ret else "no")
            st.markdown("#### Cyclomatic complexity")
            st.metric("Complexity", cc)
            st.caption("Counts: If + For + While + ExceptHandler + BoolOp nodes + 1")

        st.markdown("### Summary")
        st.info(build_summary(node, calls))
    else:
        st.info("No functions defined in this source.")


if __name__ == "__main__":
    main()
