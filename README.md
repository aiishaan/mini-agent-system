# Mini Agentic Wiki

A small, dependency-free agentic AI system that stores knowledge as local Markdown
notes instead of using traditional RAG.

The master agent coordinates six simple agents:

- `research`: reads existing Markdown notes and finds related topics
- `note-compiler`: creates or updates a structured topic note
- `linker`: builds wiki-style links and regenerates the knowledge index
- `summarizer`: synthesizes the current note graph
- `writer`: produces the structured user response
- `validator`: checks that notes, links, index, and response are consistent

## Run It

```bash
python3 mini_agentic_wiki.py "How should agents collaborate in a local markdown knowledge system?" --show-notes
```

For a simple input loop:

```bash
python3 mini_agentic_wiki.py --interactive --show-notes
```

## Run The Web Demo

Install the web dependency:

```bash
pip install -r requirements.txt
```

Start the Streamlit app:

```bash
streamlit run streamlit_app.py
```

The web app uses the same `MasterAgent` workflow as the CLI. It accepts a topic
or query, runs the agent pipeline, displays the structured response, and can show
the generated or updated Markdown notes.

## Deploy For A Live URL
https://mini-agent-system-ufb2czoruss8japp252uvv.streamlit.app/

The fastest deployment path is Streamlit Community Cloud:

- Push this project to GitHub.
- Create a new Streamlit app from the repo.
- Set the app entrypoint to `streamlit_app.py`.
- Deploy it and use the generated `.streamlit.app` URL for the demo.

The app writes knowledge files into the deployed app's local `knowledge/` folder.
That is enough for a demo, but a production version would connect persistent
storage so notes survive redeployments.

## How Knowledge Is Stored

Notes live in `knowledge/*.md`. Each note is a structured Markdown page:

- `# Topic`
- `## Summary`
- `## Key Points`
- `## Connections`
- `## Observation Log`

The system uses wiki links such as `[[Agentic AI]]` and maintains
`knowledge/index.md` as a generated topic graph. This is closer to a compiled
knowledge/wiki workflow than vector retrieval: agents update the local knowledge
base as part of answering the query.
