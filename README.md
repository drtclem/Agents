# Tutor Session Feedback Generator

An LLM-powered pipeline that automatically generates structured post-session feedback for tutors from raw session transcripts. Built with LangChain and Python.

## What it does

After a tutoring session, a tutor runs this tool against the session transcript. It:

- Calculates **talk time and word count metrics** per speaker from session timestamps
- Detects **absent sessions** automatically and skips LLM processing when students didn't show
- Uses an **LLM with structured prompt engineering** to generate per-student feedback
- Outputs a **JSON file** (for downstream system integration) and a **Markdown file** (human-readable)

### Output includes

For each student:
- Attendance status (Arrived on time / Late arrival / Early leave / Absent)
- Participation ratings across three dimensions (Persevered with Tasks, Listened Actively, Participated in Discussions)
- A parent-facing Student Understandings paragraph

Internal feedback:
- Lesson title in Cignition format with Common Core standard
- Slide range completed

Talk time analysis:
- Per-speaker time and word count percentages
- Automatic flag if tutor talk time exceeds 70%

## Tech stack

- **LangChain** — prompt templates, LCEL chains, output parsing
- **DeepSeek V4 Pro** via Lightning AI's OpenAI-compatible API
- **openpyxl** — Excel transcript parsing
- **Python** — regex post-processing, JSON validation, file output

## Setup

1. Clone the repo
2. Create and activate a virtual environment:

   python -m venv venv
   source venv/bin/activate

3. Install dependencies:

   pip install -r requirements.txt

4. Create a .env file in the project root:

   LIGHTNING_API_KEY=your_key_here

   Get a free API key at https://lightning.ai

## Usage

Run the script:

   python main.py

When prompted, enter the student names separated by commas (e.g. Alex, Jordan, Morgan).

The tool will generate two output files in your project folder:
- session_feedback_<timestamp>.json
- session_feedback_<timestamp>.md

## Transcript format

The tool expects an Excel file (.xlsx) with the following columns:

Speaker Name | Start Time | End Time | Text | Prompts | Notes
Tutor        | 00:00:00:00 | 00:01:30:00 | Good morning... | |
Student 1    | 00:01:30:05 | 00:01:38:00 | Good morning!  | |

A sample transcript (Sample_Lexington_Lesson1_fractions_9_00_Part1.xlsx) is included for testing.

## Roadmap

- Zoom API integration — auto-fetch transcripts when a session recording is ready
- RAG layer — surface relevant teaching strategy recommendations based on session content
- Multi-agent orchestration — separate agents for feedback generation and curriculum lookup
- Direct integration with Cignition's platform API