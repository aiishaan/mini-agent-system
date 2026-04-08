#!/usr/bin/env python3
"""A small local-markdown, multi-agent knowledge compiler.

The system is intentionally dependency-free. It is not a traditional RAG app:
agents do not retrieve chunks to stuff into a prompt. Instead, they read,
create, update, link, validate, and summarize Markdown notes in a local wiki.
"""

from __future__ import annotations

import argparse
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_DIR = ROOT / "knowledge"
STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "build",
    "by",
    "can",
    "for",
    "from",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "please",
    "query",
    "should",
    "system",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "use",
    "using",
    "what",
    "when",
    "where",
    "why",
    "with",
}


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:72] or "untitled"


def title_from_query(query: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\s-]", " ", query)
    words = [word for word in cleaned.split() if word.lower() not in STOP_WORDS]
    if not words:
        words = cleaned.split()[:5] or ["Untitled"]
    return " ".join(words[:7]).title()


def extract_terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text.lower()):
        if word not in STOP_WORDS:
            terms.add(word)
    return terms


def find_wikilinks(text: str) -> set[str]:
    return {match.strip() for match in re.findall(r"\[\[([^\]]+)\]\]", text)}


def first_sentence(text: str, fallback: str = "") -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return fallback
    sentence = re.split(r"(?<=[.!?])\s+", collapsed, maxsplit=1)[0]
    return sentence[:220]


def wrap_paragraph(text: str) -> str:
    return textwrap.fill(text.strip(), width=88)


def replace_section(markdown: str, heading: str, body: str) -> str:
    body = body.strip() + "\n"
    pattern = re.compile(
        rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    if pattern.search(markdown):
        return pattern.sub(rf"\g<1>{body}\n", markdown)
    markdown = markdown.rstrip() + "\n\n" if markdown.strip() else ""
    return markdown + f"## {heading}\n{body}\n"


@dataclass
class Note:
    path: Path
    title: str
    text: str
    links: set[str] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path) -> "Note":
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()
        return cls(path=path, title=title, text=text, links=find_wikilinks(text), terms=extract_terms(text))

    @property
    def summary(self) -> str:
        summary_match = re.search(r"^## Summary\n(.*?)(?=^## |\Z)", self.text, re.MULTILINE | re.DOTALL)
        if summary_match:
            return first_sentence(summary_match.group(1), fallback=self.title)
        return first_sentence(self.text, fallback=self.title)


@dataclass
class WorkflowState:
    query: str
    knowledge_dir: Path
    date: str
    notes: list[Note] = field(default_factory=list)
    topic: str = ""
    target_note: Note | None = None
    related_notes: list[Note] = field(default_factory=list)
    synthesis: str = ""
    response: str = ""
    updated_paths: list[Path] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def log(self, agent: str, message: str) -> None:
        self.trace.append(f"{agent}: {message}")


class KnowledgeBase:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def index_path(self) -> Path:
        return self.directory / "index.md"

    def load_notes(self) -> list[Note]:
        notes = []
        for path in sorted(self.directory.glob("*.md")):
            if path.name == "index.md":
                continue
            notes.append(Note.load(path))
        return notes

    def path_for_title(self, title: str) -> Path:
        return self.directory / f"{slugify(title)}.md"

    def save_note(self, title: str, markdown: str) -> Note:
        path = self.path_for_title(title)
        path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        return Note.load(path)

    def update_index(self, notes: Iterable[Note]) -> None:
        note_list = sorted(notes, key=lambda note: note.title.lower())
        title_to_note = {note.title: note for note in note_list}
        lines = [
            "# Knowledge Index",
            "",
            "This file is generated by the linker agent. Edit topic notes, not this index.",
            "",
            "## Notes",
        ]
        for note in note_list:
            lines.append(f"- [[{note.title}]] - `{note.path.name}`")
        lines.extend(["", "## Topic Graph"])
        has_edges = False
        for note in note_list:
            valid_links = sorted(link for link in note.links if link in title_to_note)
            if valid_links:
                has_edges = True
                lines.append(f"- [[{note.title}]] -> " + ", ".join(f"[[{link}]]" for link in valid_links))
        if not has_edges:
            lines.append("- No confirmed links yet.")
        self.index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


class ResearchAgent:
    name = "research"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        state.notes = kb.load_notes()
        state.topic = title_from_query(state.query)
        query_terms = extract_terms(state.query)

        scored: list[tuple[int, Note]] = []
        for note in state.notes:
            title_terms = extract_terms(note.title)
            score = len(query_terms & note.terms) + (2 * len(query_terms & title_terms))
            if state.topic.lower() == note.title.lower():
                score += 5
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda item: item[0], reverse=True)
        state.related_notes = [note for _, note in scored[:5]]

        existing = next((note for note in state.notes if note.title.lower() == state.topic.lower()), None)
        state.target_note = existing
        if existing:
            state.log(self.name, f"found existing note [[{existing.title}]] plus {len(state.related_notes)} related note(s)")
            return state

        state.log(self.name, f"no exact note for [[{state.topic}]], so a compiled note will be created")
        return state


class NoteCompilerAgent:
    name = "note-compiler"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        related_links = [f"[[{note.title}]]" for note in state.related_notes if note.title != state.topic]
        connection_line = ", ".join(related_links) if related_links else "No confirmed local links yet."
        related_context = "\n".join(f"- [[{note.title}]]: {note.summary}" for note in state.related_notes)
        if not related_context:
            related_context = "- No related local notes were found before this run."

        if state.target_note is None:
            markdown = f"""# {state.topic}

## Summary
{wrap_paragraph(f"{state.topic} is a compiled knowledge note created from a user query and the existing local wiki. It should become more useful as agents add observations, links, and summaries over time.")}

## Key Points
- Original query: {state.query}
- This note favors durable local knowledge over one-off retrieved context.
- Future runs can refine this note by linking it to better established topics.

## Connections
{connection_line}

## Local Context
{related_context}

## Observation Log
- {state.date}: Created from query: {state.query}
"""
            state.target_note = kb.save_note(state.topic, markdown)
            state.updated_paths.append(state.target_note.path)
            state.log(self.name, f"created {state.target_note.path.name}")
            return state

        text = state.target_note.text
        current_connections = find_wikilinks(text)
        for note in state.related_notes:
            if note.title != state.target_note.title:
                current_connections.add(note.title)
        connections_body = (
            ", ".join(f"[[{title}]]" for title in sorted(current_connections))
            if current_connections
            else "No confirmed local links yet."
        )
        observation_match = re.search(
            r"^## Observation Log\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
        )
        observations = observation_match.group(1).strip() if observation_match else ""
        new_observation = f"- {state.date}: Revisited for query: {state.query}"
        if new_observation not in observations:
            observations = (observations + "\n" + new_observation).strip()

        text = replace_section(text, "Connections", connections_body)
        text = replace_section(text, "Observation Log", observations)
        state.target_note = kb.save_note(state.target_note.title, text)
        state.updated_paths.append(state.target_note.path)
        state.log(self.name, f"updated {state.target_note.path.name}")
        return state


class LinkingAgent:
    name = "linker"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        state.notes = kb.load_notes()
        titles = {note.title for note in state.notes}
        updated = []

        for note in state.notes:
            inferred_links = set(note.links)
            note_terms = extract_terms(note.title + " " + note.text)
            for other in state.notes:
                if other.title == note.title:
                    continue
                other_terms = extract_terms(other.title)
                if other.title in note.text:
                    inferred_links.add(other.title)
                elif note_terms & other_terms and note.title == state.topic:
                    inferred_links.add(other.title)

            valid_links = sorted(link for link in inferred_links if link in titles and link != note.title)
            body = ", ".join(f"[[{title}]]" for title in valid_links) if valid_links else "No confirmed local links yet."
            new_text = replace_section(note.text, "Connections", body)
            if new_text != note.text:
                saved = kb.save_note(note.title, new_text)
                updated.append(saved.path)

        state.notes = kb.load_notes()
        kb.update_index(state.notes)
        state.updated_paths.extend(path for path in updated if path not in state.updated_paths)
        state.updated_paths.append(kb.index_path)
        state.log(self.name, f"rebuilt index with {len(state.notes)} note(s)")
        return state


class SummarizerAgent:
    name = "summarizer"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        state.notes = kb.load_notes()
        state.target_note = next((note for note in state.notes if note.title == state.topic), state.target_note)
        related_titles = set(find_wikilinks(state.target_note.text if state.target_note else ""))
        related = [note for note in state.notes if note.title in related_titles]
        if not related:
            related = state.related_notes[:3]

        target_summary = state.target_note.summary if state.target_note else "No compiled note was created."
        bullets = [f"- Core note: [[{state.topic}]] - {target_summary}"]
        for note in related[:4]:
            bullets.append(f"- Related: [[{note.title}]] - {note.summary}")
        state.synthesis = "\n".join(bullets)
        state.log(self.name, f"synthesized {1 + len(related[:4])} note summary item(s)")
        return state


class WriterAgent:
    name = "writer"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        state.log(self.name, "produced structured response")
        note_path = state.target_note.path if state.target_note else kb.path_for_title(state.topic)
        response = f"""# Answer

The local wiki now has a compiled note for [[{state.topic}]]. Based on the current Markdown knowledge base:

{state.synthesis}

## Structured Output
- Query: {state.query}
- Compiled topic: [[{state.topic}]]
- Primary note: `{note_path}`
- Knowledge style: local Markdown notes with wiki links, not vector RAG

## Agent Trace
{chr(10).join(f"- {item}" for item in state.trace)}
"""
        state.response = response.rstrip()
        return state


class ValidatorAgent:
    name = "validator"

    def run(self, state: WorkflowState, kb: KnowledgeBase) -> WorkflowState:
        notes = kb.load_notes()
        titles = {note.title for note in notes}
        if not state.response:
            state.warnings.append("No response was generated.")
        if state.topic not in titles:
            state.warnings.append(f"The compiled note [[{state.topic}]] was not found.")
        for note in notes:
            for link in find_wikilinks(note.text):
                if link not in titles:
                    state.warnings.append(f"{note.path.name} links to missing note [[{link}]].")
        if not kb.index_path.exists():
            state.warnings.append("Knowledge index was not generated.")

        if state.warnings:
            state.log(self.name, f"reported {len(state.warnings)} warning(s)")
            state.response = replace_section(
                state.response,
                "Agent Trace",
                "\n".join(f"- {item}" for item in state.trace),
            )
            state.response = state.response.rstrip() + "\n\n## Validation Warnings\n" + "\n".join(
                f"- {warning}" for warning in state.warnings
            )
        else:
            state.log(self.name, "passed")
            state.response = replace_section(
                state.response,
                "Agent Trace",
                "\n".join(f"- {item}" for item in state.trace),
            )
            state.response = (
                state.response.rstrip()
                + "\n\n## Validation\n- Passed: response, compiled note, index, and wiki links are consistent."
            )
        return state


class MasterAgent:
    def __init__(self, knowledge_dir: Path):
        self.kb = KnowledgeBase(knowledge_dir)
        self.agents = [
            ResearchAgent(),
            NoteCompilerAgent(),
            LinkingAgent(),
            SummarizerAgent(),
            WriterAgent(),
            ValidatorAgent(),
        ]

    def run(self, query: str) -> WorkflowState:
        state = WorkflowState(
            query=query.strip(),
            knowledge_dir=self.kb.directory,
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        for agent in self.agents:
            state = agent.run(state, self.kb)
        return state


def render_notes(paths: Iterable[Path]) -> str:
    rendered = []
    seen = set()
    for path in paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        rendered.append(f"\n--- {path} ---\n{path.read_text(encoding='utf-8').rstrip()}")
    return "\n".join(rendered)


def run_once(args: argparse.Namespace) -> None:
    master = MasterAgent(args.knowledge_dir)
    state = master.run(args.query)
    print(state.response)
    if args.show_notes:
        print(render_notes(state.updated_paths))


def run_interactive(args: argparse.Namespace) -> None:
    master = MasterAgent(args.knowledge_dir)
    print("Mini Agentic Wiki. Enter a topic or query. Use Ctrl-D to exit.")
    while True:
        try:
            query = input("\nquery> ").strip()
        except EOFError:
            print()
            return
        if not query:
            continue
        state = master.run(query)
        print()
        print(state.response)
        if args.show_notes:
            print(render_notes(state.updated_paths))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local Markdown mini agentic AI/wiki workflow."
    )
    parser.add_argument("query", nargs="*", help="Topic or question to process.")
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        default=DEFAULT_KNOWLEDGE_DIR,
        help=f"Directory that stores Markdown notes. Default: {DEFAULT_KNOWLEDGE_DIR}",
    )
    parser.add_argument(
        "--show-notes",
        action="store_true",
        help="Display generated or updated Markdown notes after the response.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open a small REPL-style input loop.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.query = " ".join(args.query).strip()

    if args.interactive:
        run_interactive(args)
        return

    if not args.query:
        parser.error("provide a query or use --interactive")
    run_once(args)


if __name__ == "__main__":
    main()
