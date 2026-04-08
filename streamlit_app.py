from pathlib import Path

import streamlit as st

from mini_agentic_wiki import DEFAULT_KNOWLEDGE_DIR, MasterAgent


SAMPLE_QUERY = "How should agents collaborate in a local markdown knowledge system?"


def unique_existing_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    existing = []
    for path in paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        existing.append(path)
    return existing


st.set_page_config(page_title="Mini Agentic Wiki", layout="wide")

st.title("Mini Agentic Wiki")
st.caption("A small master-agent workflow that compiles local Markdown knowledge.")

with st.sidebar:
    st.header("System")
    st.write(
        "Master agent coordinates research, note compilation, linking, "
        "summarizing, writing, and validation."
    )
    st.write(f"Knowledge folder: `{DEFAULT_KNOWLEDGE_DIR}`")
    show_notes = st.checkbox("Show generated or updated notes", value=True)
    show_trace = st.checkbox("Show agent trace while running", value=True)

query = st.text_area(
    "Topic or query",
    value=SAMPLE_QUERY,
    height=120,
    help="The agents will read and update local Markdown notes for this topic.",
)

run_clicked = st.button("Run agent workflow", type="primary")

if run_clicked:
    clean_query = query.strip()
    if not clean_query:
        st.warning("Enter a topic or query first.")
        st.stop()

    master = MasterAgent(DEFAULT_KNOWLEDGE_DIR)

    with st.status("Running local Markdown agents...", expanded=show_trace) as status:
        state = master.run(clean_query)
        if show_trace:
            for item in state.trace:
                st.write(item)
        status.update(label="Workflow complete", state="complete", expanded=False)

    st.subheader("Response")
    st.markdown(state.response)

    if show_notes:
        updated_paths = unique_existing_paths(state.updated_paths)
        if updated_paths:
            st.subheader("Generated or Updated Notes")
            for path in updated_paths:
                with st.expander(path.name, expanded=path.name != "index.md"):
                    st.code(path.read_text(encoding="utf-8"), language="markdown")
        else:
            st.info("No Markdown files were changed during this run.")
else:
    st.info("Enter a topic and run the workflow to generate or update the Markdown wiki.")
