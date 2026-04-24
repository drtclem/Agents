# ─────────────────────────────────────────────
# Cignition Session Feedback Generator
# Reads a tutoring session transcript (Excel),
# calculates talk time metrics, and uses an LLM
# to generate structured session feedback.
# ─────────────────────────────────────────────

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import openpyxl
import re
import json
from datetime import datetime

# Load environment variables from .env file (API key lives here)
load_dotenv()

# ── LLM Setup ──────────────────────────────────────────────────────────────
# Connect to DeepSeek via Lightning AI's OpenAI-compatible API
llm = ChatOpenAI(
    model="lightning-ai/deepseek-v4-pro",
    api_key=os.getenv("LIGHTNING_API_KEY"),
    base_url="https://lightning.ai/api/v1",
)


# ── Helper Functions ────────────────────────────────────────────────────────

def parse_time(t):
    """Convert a timestamp string (HH:MM:SS:FF) to total seconds."""
    parts = str(t).split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


def load_transcript(filepath):
    """
    Read a session transcript from an Excel file.
    Returns:
        lines: list of 'Speaker: text' strings for the LLM
        talk_time: dict of speaker -> total seconds spoken
        word_count: dict of speaker -> total words spoken
    """
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active

    lines = []
    talk_time = {}
    word_count = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        speaker = row[0]
        start = row[1]
        end = row[2]
        text = row[3]

        # Skip rows with no speaker or no spoken text
        if not speaker or not text:
            continue

        lines.append(f"{speaker}: {text}")

        # Add duration to this speaker's total talk time
        if start and end:
            duration = parse_time(end) - parse_time(start)
            talk_time[speaker] = talk_time.get(speaker, 0) + duration

        # Add word count to this speaker's total
        words = len(text.split())
        word_count[speaker] = word_count.get(speaker, 0) + words

    return lines, talk_time, word_count


def format_metrics(talk_time, word_count):
    """
    Format talk time and word count into a readable string
    that gets passed to the LLM as context.
    """
    total_time = sum(talk_time.values())
    total_words = sum(word_count.values())

    metrics = ["TALK TIME METRICS:"]
    for speaker, seconds in talk_time.items():
        mins = seconds // 60
        secs = seconds % 60
        pct = (seconds / total_time) * 100
        metrics.append(f"{speaker}: {mins} min {secs} sec ({pct:.1f}%)")

    metrics.append("\nWORD COUNT METRICS:")
    for speaker, words in word_count.items():
        pct = (words / total_words) * 100
        metrics.append(f"{speaker}: {words} words ({pct:.1f}%)")

    return "\n".join(metrics)


def is_absent_session(word_count):
    """
    Check if all students were effectively absent.
    If total student words are under 20, skip LLM and mark everyone absent.
    """
    student_words = sum(words for speaker, words in word_count.items()
                        if speaker.lower() != "tutor")
    return student_words < 20


def clean_response(text):
    """
    Remove hallucinated numbers that the LLM sometimes inserts mid-word
    (e.g. 'Leighton065' -> 'Leighton').
    """
    text = re.sub(r'(?<=[a-zA-Z])\d+', '', text)  # numbers after letters
    text = re.sub(r'\d+(?=[a-zA-Z])', '', text)    # numbers before letters
    return text


def save_output(response_text, student_names):
    """
    Parse the LLM's JSON response and save two files:
      - session_feedback_<timestamp>.json  (raw data)
      - session_feedback_<timestamp>.md    (human-readable)
    If JSON parsing fails, save the raw response as a .txt file instead.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"session_feedback_{timestamp}"

    # Try to parse the LLM response as JSON
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        print("Warning: LLM returned invalid JSON. Saving raw response.")
        with open(f"{base_filename}_raw.txt", "w") as f:
            f.write(response_text)
        return

    # Save raw JSON file
    with open(f"{base_filename}.json", "w") as f:
        json.dump(data, f, indent=2)

    # Save formatted markdown file
    with open(f"{base_filename}.md", "w") as f:
        f.write("# Session Feedback\n\n")
        for student in data["students"]:
            f.write(f"## {student['name']}\n")
            f.write(f"**Attendance:** {student['attendance']}\n\n")
            f.write(f"**Persevered with Tasks:** {student['participation']['perseveredWithTasks']}\n\n")
            f.write(f"**Listened Actively:** {student['participation']['listenedActively']}\n\n")
            f.write(f"**Participated in Discussions:** {student['participation']['participatedInDiscussions']}\n\n")
            f.write(f"**Student Understandings:** {student['studentUnderstandings']}\n\n---\n\n")
        f.write(f"## Internal Feedback\n")
        f.write(f"**Lesson Title:** {data['internalFeedback']['lessonTitle']}\n\n")
        f.write(f"**Slide Range:** {data['internalFeedback']['slideRange']}\n\n")
        f.write(f"## Talk Time Analysis\n")
        f.write(f"{data['talkTimeAnalysis']['metrics']}\n\n")
        f.write(f"**Note:** {data['talkTimeAnalysis']['flag']}\n")

    print(f"Saved: {base_filename}.json and {base_filename}.md")


# ── Prompt Template ─────────────────────────────────────────────────────────
# Instructions for the LLM. The {transcript} placeholder gets filled in
# at runtime with the actual transcript + metrics.
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an assistant that helps tutors at Cignition complete their session feedback.
Given a tutoring session transcript, you will produce:

Important rules:
- Only use names, words, and information that appear explicitly in the transcript
- Do not invent, infer, or add any information not present in the source text
- Use only standard English words
- For attendance: a student is 'Arrived on time' if they speak early in the session, 'Late arrival' if they first speak significantly after the session begins, 'Early leave' if they stop participating well before the session ends
- For student names: use exactly the names as they appear in the transcript
- The students in this session are provided at the top of the input. Generate feedback for each one.
- Do not include any numbers, codes, or identifiers within sentences — numbers should only appear in the talk time metrics section
- Do not use gendered pronouns (he/she/his/her). Use the student's name or "they/them" instead.

1. For each student:
   - Attendance status (Arrived on time / Late arrival / Early leave / Absent)
   - Participation rating for: Persevered with Tasks, Listened Actively, Participated in Discussions
     (More than 75% of the time / Approximately 50% of the time / Less than 25% of the time)
   - A Student Understandings paragraph (positive, professional tone, sent to parents, include student name)

2. Internal Feedback:
   - Lesson title in Cignition format (e.g. "Cignition: Fractions on a Number Line (3.NF.A.2)")
   - Slide range completed (e.g. "Slides 6-9")

3. Talk Time Analysis:
   - Show the talk time metrics as provided
   - If tutor talk time exceeds 70%, flag it as a note for improvement

Output your response as valid JSON only, with no additional text, reasoning, or explanation outside the JSON. Use this exact structure:
{{
  "students": [
    {{
      "name": "",
      "attendance": "",
      "participation": {{
        "perseveredWithTasks": "",
        "listenedActively": "",
        "participatedInDiscussions": ""
      }},
      "studentUnderstandings": ""
    }}
  ],
  "internalFeedback": {{
    "lessonTitle": "",
    "slideRange": ""
  }},
  "talkTimeAnalysis": {{
    "metrics": "",
    "flag": ""
  }}
}}"""),
    ("human", "Here is the transcript:\n\n{transcript}"),
])


# ── Chain ───────────────────────────────────────────────────────────────────
# LCEL pipe: fill prompt → send to LLM → extract text from response object
chain = prompt | llm | StrOutputParser()


# ── Main Execution ──────────────────────────────────────────────────────────

# Get student names upfront (transcript may label them generically as "Student 1")
student_names = input("Enter student names separated by commas: ")

# Load and parse the transcript
# TODO: replace hardcoded filename with Zoom API call when ready
lines, talk_time, word_count = load_transcript("Austin(sub)_Lexington_Lesson6mixed_8_45_Part1_11_18_21.xlsx")

if is_absent_session(word_count):
    # Skip the LLM entirely — just mark everyone absent
    print("No student participation detected. Marking all students as absent.")
    absent_output = {
        "students": [
            {"name": name.strip(), "attendance": "Absent", "participation": {}, "studentUnderstandings": ""}
            for name in student_names.split(",")
        ],
        "internalFeedback": {"lessonTitle": "", "slideRange": ""},
        "talkTimeAnalysis": {"metrics": "", "flag": ""}
    }
    save_output(json.dumps(absent_output), student_names)
else:
    # Build the full input: metrics + transcript text
    metrics = format_metrics(talk_time, word_count)
    transcript_text = "\n".join(lines)
    full_input = f"Students in this session: {student_names}\n\n{metrics}\n\nTRANSCRIPT:\n{transcript_text}"

    # Call the LLM, clean up any hallucinated numbers, save output
    response = chain.invoke({"transcript": full_input})
    response = clean_response(response)
    save_output(response, student_names)