Code Explanation Tutor

A Streamlit app that explains any Python file using static analysis — no external AI API calls needed for the core logic.

Problem Statement

Upload a Python program or project source file. Ask questions like "What does this function do?", "Where does execution start?", or "How does data flow through this program?" and get beginner-friendly explanations grounded in the actual code structure.

How It Works

The app parses uploaded source with Python's built-in ast module (the same parser CPython uses internally) rather than regex or string matching. From the resulting syntax tree, it:

Lists every import, function, and class with signatures and docstrings
Detects the entry point (if __name__ == "__main__" block)
Builds a call graph showing which functions call which
Flags functions that are defined but never called
Computes cyclomatic complexity per function by counting branch nodes
Answers preset questions using this analysis directly, with no runtime execution of the uploaded code
Running Locally
bash
pip install streamlit
streamlit run app.py

Then open the local URL Streamlit prints, upload a .py file, and explore.

Example

A sample file, sample_inventory.py, is included for testing — it has a class, nested branching, an unused function, and a clear call chain, so it exercises every feature of the analyzer.

Tech Stack
Python standard library only (ast, statistics)
Streamlit for the interface
Limitations

This is static analysis — it inspects code structure without running it, so it cannot resolve dynamic behavior like getattr-based calls or runtime dispatch.

Built With

Built iteratively using Claude Code as a GenAI vibe-coding partner, as part of a mini project on GenAI-assisted rapid prototyping.
