
import re
import unicodedata
import streamlit as st
import pdfplumber
from pylatex import Document, NoEscape
from pylatex.package import Package
from pylatex.utils import escape_latex
from openai import OpenAI
import json
import plotly.express as px
import pandas as pd
from supabase import create_client, Client
import stripe
from streamlit_supabase_auth import login_form
from menu import menu_with_redirect
import tempfile
import os
from streamlit import switch_page

# ─── Supabase & Stripe Initialization ──────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# ─── OpenAI Setup ──────────────────────────────────────────────

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
OPENAI_MODEL = "gpt-4.1-mini"

def call_openai_system_user(system: str, user: str, max_tokens: int = 512, temp: float = 0.0) -> str:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temp,
    )
    return resp.choices[0].message.content.strip()

# ─── PDF Extraction ────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", text).strip()

def extract_sections_from_pdf(file) -> list[tuple[str, str]]:
    sections = []
    excluded = {"contents", "reading list", "readinglist"}

    with pdfplumber.open(file) as pdf:
        cur_title, cur_body = None, []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines = txt.splitlines()

            words = page.extract_words(extra_attrs=("size", "fontname", "top", "x0"))
            groups = {}
            for w in words:
                groups.setdefault(round(w["top"], 1), []).append(w)
            headings = sorted(
                (y, clean_text(" ".join(w["text"] for w in grp)))
                for y, grp in groups.items()
                if (sum(float(w["size"]) for w in grp)/len(grp) >= 13 or any("Bold" in w["fontname"] for w in grp))
            )

            hi = 0
            for i, line in enumerate(lines):
                ln = clean_text(line)
                if not ln:
                    continue
                if hi < len(headings) and abs(headings[hi][0] - i*12) < 12:
                    if cur_title and cur_title.lower().replace(" ","") not in excluded:
                        sections.append((cur_title, clean_text(" ".join(cur_body))))
                    cur_title, cur_body = headings[hi][1], []
                    hi += 1
                else:
                    cur_body.append(ln)

        if cur_title and cur_title.lower().replace(" ","") not in excluded:
            sections.append((cur_title, clean_text(" ".join(cur_body))))

    if not sections:
        # fallback: split by big line breaks
        with pdfplumber.open(file) as pdf:
            full = ""
            for p in pdf.pages:
                full += (p.extract_text() or "") + "\n"
        paragraphs = re.split(r"\n{2,}", full)
        sections = [(f"Part {i+1}", clean_text(p)) for i, p in enumerate(paragraphs) if p.strip()]

    return sections


# ─── Multi Past Papers Raw Text Intake ──────────────────────────────

def extract_raw_text_from_pdfs_simple(paper_files) -> list[dict]:
    """
    Takes a list of uploaded past paper PDFs.
    Returns a list of dicts:
    [
        {"filename": ..., "raw_text": ...},
        ...
    ]
    """
    results = []
    for file in paper_files:
        raw_text = ""
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                raw_text += "\n" + page_text
        results.append({
            "filename": file.name,
            "raw_text": clean_text(raw_text),
        })
    return results

# ─── Chunking & Summarization ─────────────────────────────────

def chunk_text(text: str, max_tokens: int = 2000, overlap: int = 200) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_tokens - overlap):
        chunks.append(" ".join(words[i:i+max_tokens]))
        if i + max_tokens >= len(words):
            break
    return chunks

SYSTEM_PROMPT = """
You are an expert university-level tutor.
Your job is to transform each section of raw lecture notes into clear, concise, exam-focused study notes.
Strictly use only the material provided — do not invent.
Ignore any sections titled 'Reading List', 'Bibliography' or 'References' - do not summarise these, skip them entirely.

Each output section must contain:
1. An Overview paragraph (max 5 sentences).
2. 5–10 Key Concepts as a bullet list.
3. Step-by-Step Derivations (if any).
4. Important Equations list — each must have a short descriptive label.
5. Quick Tips: practical points for students.

Formatting:
- Use standard LaTeX sectioning commands: \\section, \\subsection.
- Use only ASCII text outside math.
- Do not use any custom macros.
- Use only amsmath/amsfonts.
- All math must be correctly wrapped: inline $...$ or \\(...\\), block \\begin{equation*}...\\end{equation*} or \\begin{align}...\\end{align}.
- The output must compile directly in XeLaTeX.
- Do not output HTML or Markdown.
"""

def summarize_section(title: str, body: str) -> str:
    chunks = chunk_text(body, max_tokens=4000, overlap=200)
    summary_parts = []
    for chunk in chunks:
        user_prompt = f"Section Title: {title}\n\n{chunk}"
        out = call_openai_system_user(SYSTEM_PROMPT, user_prompt, max_tokens=4000)
        summary_parts.append(out)
    final = "\n\n".join(summary_parts)
    return final

# ─── Past Paper Analysis ───────────────────────────────────────

PAST_PAPER_PROMPT = """
You are a meticulous academic examiner and curriculum analyst.

Your task:
Given the full raw text of a university-level past exam paper, extract and compile all useful meta information and question-level breakdowns.

**Your output must be a valid, compact JSON with the following structure:**

{
  "meta": {
    "institution": "string, if found",
    "faculty_or_school": "string, if found",
    "course_code": "string, if found",
    "subject": "string, if found",
    "year": "string, if found",
    "term": "string, if found",
    "duration": "string, if found",
    "total_marks": "string, if found",
    "instructions_summary": "short summary of any instructions",
    "notes": "any other meta information found"
  },
  "structure": {
    "sections": [
      {
        "section_title": "string",
        "instructions": "string, if any",
        "questions": [
          {
            "question_number": "1",
            "question_text": "full text of question",
            "topic_or_area": "your best guess",
            "question_type": "essay, short answer, calculation, derivation, proof, MCQ, etc.",
            "marks": "string, if specified"
          }
        ]
      }
    ]
  }
}

**Guidelines:**
- Be precise. Do not hallucinate details. Only extract what is clearly present.
- For instructions, interpret any details about how many questions must be answered.
- If there are no explicit sections, use a single default section called "Main Paper".
- Always wrap your output in valid JSON, no Markdown.
- Use sensible defaults: if a field is missing, output `null` or an empty string.

Input starts below:
"""


PAST_PAPER_TRENDS_SUPERPROMPT = """
You are an expert exam strategist and curriculum analyst.

Your task:
Given multiple JSON blocks, each containing the full structured breakdown of a past exam paper,
do a deep analysis to extract patterns, trends, and practical study advice.

**Your output must be a single valid JSON with this structure:**

{
  "overall_trends": {
    "common_topics": ["topic1", "topic2", "..."],
    "common_question_types": ["essay", "calculation", "proof", "..."],
    "recurring_sections_or_parts": ["Section A compulsory", "Short Questions Part B", "..."],
    "typical_instructions": ["Answer any 3 of 5 questions", "..."],
    "average_questions_per_paper": int,
    "average_marks_per_question": "estimate if possible"
  },
  "topic_frequencies": [
    {"topic": "Topic Name", "frequency": int}
  ],
  "frequencies_by_year": [
    {
      "year": "2022",
      "topics": [
        {"topic": "Topic Name", "frequency": int}
      ],
      "question_types": [
        {"type": "calculation", "frequency": int}
      ]
    },
    {
      "year": "2023",
      "topics": [...],
      "question_types": [...]
    }
  ],
  "useful_tips": [
    "Practical tip 1",
    "Practical tip 2",
    "Practical tip 3"
  ],
  "possible_exam_strategy": [
    "How to approach time management",
    "How to choose questions",
    "Any other useful advice"
  ]
}

**Guidelines:**
- Group trends by year using the `meta.year` field in each input JSON.
- If any paper has a missing year, note it in the results under `"year": "unknown"`.
- Identify overlapping topics — group by synonyms if needed.
- Spot repeated question styles or formats.
- Note any repeated phrases in instructions.
- Give practical, concise tips for how a student should prepare.
- Wrap your output in valid JSON only. No Markdown.
- If something is unclear, make a reasonable estimate and say so.

Input JSONS below:
"""

# ─── PDF Creation ─────────────────────────────────────────────

def create_pdf_with_pylatex(latex_body: str, subject_title: str = "") -> str:
    doc = Document("study_materials", documentclass="article")
    doc.packages.append(Package('amsmath'))
    doc.packages.append(Package('amsfonts'))
    doc.packages.append(Package('graphicx'))
    if subject_title.strip():
        doc.preamble.append(NoEscape(f"\\title{{{subject_title.strip()}}}"))

    doc.append(NoEscape("\\maketitle"))
    doc.append(NoEscape(latex_body.strip()))
    
    tex_path = "study_material.tex"
    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(doc.dumps())
        
    #st.text_area("Generated .tex source", open(tex_path).read(), height=400)

    filename = "study_materials"
    doc.generate_pdf(filename, clean_tex=False)
    return filename + ".pdf"

# ─── Streamlit App ────────────────────────────────────────────


# ─── Authentication & Profile Fetch ──────────────────────────────

menu_with_redirect()

# 2) Extract user info from seesion_state
user = st.session_state["user"]
user_id = user["id"]
user_email = user["email"]

st.title("Sprag - Study Assistant")

def get_user_supabase_client(access_token: str) -> Client:
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options={
            "headers": {
                "Authorization": f"Bearer {access_token}"
            }
        }
    )

access_token = st.session_state["access_token"]

user_supabase = get_user_supabase_client(access_token)

# 3) Load their profile by id
res = user_supabase.table("profiles") \
    .select("*") \
    .eq("id", user_id) \
    .limit(1) \
    .execute()
profile = res.data[0] if res.data else None

credits = profile["credits"]

if not profile:
    st.error("⚠️ Could not load your profile; please contact support.")
    st.stop()

# 4) If they have no Stripe customer ID yet, create one and store it
if not profile.get("stripe_customer_id"):
    cust = stripe.Customer.create(email=user_email)
    user_supabase.table("profiles") \
      .update({"stripe_customer_id": cust["id"]}) \
      .eq("id", user_id) \
      .execute()
    profile["stripe_customer_id"] = cust["id"]


subject = st.text_input("Subject (e.g., Atomic Physics)")
lec_file = st.file_uploader("Lecture Notes PDF (typed only) (MAX 20MB)", type=["pdf"])
paper_file = st.file_uploader("Past Paper PDFs (MAX 20MB)", type=["pdf"], accept_multiple_files=True)

max_file_size_mb = 20

if lec_file is not None:
    lec_file.seek(0, 2)
    size_mb = lec_file.tell() / (1024 * 1024)
    lec_file.seek(0)
    if size_mb > max_file_size_mb:
        st.error(f"Lecture Notes PDF is too large ({size_mb:.2f} MB). Max size allowed: {max_file_size_mb} MB ")
        st.stop()
        
if paper_file:
    for f in paper_file:
        f.seek(0, 2)
        size_mb = f.tell() / (1024 * 1024)
        f.seek(0)
        if size_mb > max_file_size_mb:
            st.error(f"Past Paper '{f.name}' is too large ({size_mb:.2f} MB). Max  size allowed: {max_file_size_mb} MB ")
            st.stop()

      
st.write("### What do you want to generate?")

run_summarization = st.checkbox("📚 Lecture Notes Summary", value=bool(lec_file))
run_pastpaper = st.checkbox("📄 Past Paper Analysis", value=bool(paper_file))

if st.button("Run Selected Tasks"):
    # 1) Compute cost
    cost = 0.5 * int(run_summarization) + 0.5 * int(run_pastpaper)
    if cost == 0:
        st.error("Please select at least one task.")
        st.stop()
    if credits < cost:
        st.error(f"Not enough credits ({credits} left; need {cost}).")
        st.stop()

    if not any([run_summarization, run_pastpaper]):
        st.error("Please select at least one task to run.")
        st.stop()

    # Validate required files
    if run_summarization and not lec_file:
        st.error("Lecture notes PDF is required for summarization.")
        st.stop()
    if run_pastpaper and not paper_file:
        st.error("Past paper PDF is required for analysis.")
        st.stop()

    st.info(f"Running selected tasks. Usage: {cost} credits")

    summarized = []
    sections = []

    if run_summarization:
        with st.spinner("Extracting and summarizing lecture notes…"):
            sections = extract_sections_from_pdf(lec_file)
            st.info(f"Found {len(sections)} sections.")
            prog = st.progress(0)
            for i, (t, b) in enumerate(sections, 1):
                summarized.append((t, summarize_section(t, b)))
                prog.progress(i / len(sections))

    pastpaper_jsons = []
    pastpaper_trends = ""

    if run_pastpaper:
        with st.spinner("Extracting and analyzing past papers…"):
            raw_texts = extract_raw_text_from_pdfs_simple(paper_file)

            for i, paper in enumerate(raw_texts, 1):
                st.info(f"Analyzing paper: {paper['filename']}")
                single_paper_json = call_openai_system_user(
                    "You are a meticulous academic examiner.",
                    PAST_PAPER_PROMPT + "\n\n" + paper["raw_text"],
                    max_tokens=4000
                )
                pastpaper_jsons.append(single_paper_json)

            # Combine all paper JSONs for trend analysis
            combined_jsons = "\n\n".join(pastpaper_jsons)

            pastpaper_trends = call_openai_system_user(
                "You are an expert exam strategist.",
                PAST_PAPER_TRENDS_SUPERPROMPT + "\n\n" + combined_jsons,
                max_tokens=4000
            )

            # Debug: show raw JSON if you want
            #st.json({"Past Paper Trends": pastpaper_trends})

            # ✅ NEW: Display nicely

            # Extract the inner JSON string and parse it
            trends = json.loads(pastpaper_trends)

            # ---------- Display -------------
            st.header("📊 Past Paper Trends Visualized")

            # Topics Bar Chart
            topic_freqs = trends["topic_frequencies"]
            topics = [item["topic"] for item in topic_freqs]
            freqs = [item["frequency"] for item in topic_freqs]

            fig_topics = px.bar(
                x=topics, y=freqs,
                labels={'x': 'Topic', 'y': 'Frequency'},
                title="Frequency of Topics",
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            st.plotly_chart(fig_topics)

            # Question Types Pie
            qtypes = trends["overall_trends"]["common_question_types"]
            qtype_freqs = [1] * len(qtypes)  # dummy counts, adjust if you have real ones
            fig_qtypes = px.pie(
                names=qtypes,
                values=qtype_freqs,
                title="Common Question Types",
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            st.plotly_chart(fig_qtypes)
            
            # Prepare and visualize yearly topic frequencies
            yearly_topics = []
            for year_entry in trends.get("frequencies_by_year", []):
                year = year_entry.get("year", "")
                for topic_info in year_entry.get("topics", []):
                    yearly_topics.append({
                        "Year": year,
                        "Topic": topic_info.get("topic", ""),
                        "Frequency": topic_info.get("frequency", 0)
                    })

            df_yearly_topics = pd.DataFrame(yearly_topics)

            if not df_yearly_topics.empty:
                st.subheader("📈 Yearly Topic Frequencies")
                fig_yearly_topics = px.bar(
                    df_yearly_topics,
                    x="Year",
                    y="Frequency",
                    color="Topic",
                    barmode="group",
                    title="Frequency of Topics by Year",
                    labels={"Frequency": "Frequency", "Year": "Year", "Topic": "Topic"},
                    width = 900,
                    height = 500,
                    color_discrete_sequence=px.colors.qualitative.Plotly
                )
                
                fig_yearly_topics.update_layout(
                    legend=dict(
                        y = -0.2,
                        yanchor = "top",
                        x = 0.5,
                        xanchor = "center" 
                    )
                )

                st.plotly_chart(fig_yearly_topics)
            else:
                st.write("No yearly topic frequency data available.")

            # Prepare and visualize yearly question type frequencies
            yearly_qtypes = []
            for year_entry in trends.get("frequencies_by_year", []):
                year = year_entry.get("year", "")
                for qtype_info in year_entry.get("question_types", []):
                    yearly_qtypes.append({
                        "Year": year,
                        "Question Type": qtype_info.get("type", ""),
                        "Frequency": qtype_info.get("frequency", 0)
                    })

            df_yearly_qtypes = pd.DataFrame(yearly_qtypes)

            if not df_yearly_qtypes.empty:
                st.subheader("📊 Yearly Question Type Frequencies")
                fig_yearly_qtypes = px.bar(
                    df_yearly_qtypes,
                    x="Year",
                    y="Frequency",
                    color="Question Type",
                    barmode="group",
                    title="Frequency of Question Types by Year",
                    labels={"Frequency": "Frequency", "Year": "Year", "Question Type": "Question Type"},
                    width = 900,
                    height = 500,
                    color_discrete_sequence=px.colors.qualitative.Plotly
                )
                st.plotly_chart(fig_yearly_qtypes)
            else:
                st.write("No yearly question type frequency data available.")

            
            saved_figures = []
            
            tmp_dir = tempfile.mkdtemp(dir="/tmp")
            
            fig_topics_path = os.path.join(tmp_dir, "fig_topics.pdf")
            fig_topics.write_image(fig_topics_path)
            saved_figures.append(fig_topics_path)

            fig_qtypes_path = os.path.join(tmp_dir, "fig_qtypes.pdf")            
            fig_qtypes.write_image(fig_qtypes_path)
            saved_figures.append(fig_qtypes_path)

            fig_yearly_topics_path = os.path.join(tmp_dir, "df_yearly_topics.pdf")            
            fig_yearly_topics.write_image(fig_yearly_topics_path)
            saved_figures.append(fig_yearly_topics_path)

            fig_yearly_qtypes_path = os.path.join(tmp_dir, "df_yearly_qtypes.pdf")
            fig_yearly_qtypes.write_image(fig_yearly_qtypes_path)
            saved_figures.append(fig_yearly_qtypes_path)


            # Typical Instructions
            st.subheader("Typical Instructions")
            for instr in trends["overall_trends"]["typical_instructions"]:
                st.write(f"- {instr}")

            # Key stats
            st.subheader("Key Stats")
            st.write(f"**Average questions per paper:** {trends['overall_trends']['average_questions_per_paper']}")
            st.write(f"**Average marks per question:** {trends['overall_trends']['average_marks_per_question']}")

            # Useful Tips
            st.subheader("✅ Useful Revision Tips")
            for tip in trends["useful_tips"]:
                st.write(f"• {tip}")

            # Exam Strategy
            st.subheader("📝 Suggested Exam Strategy")
            for strat in trends["possible_exam_strategy"]:
                st.write(f"• {strat}")


    # Combine output
    latex_body = ""

    if summarized:
        latex_body += "\n\n".join(content for _, content in summarized)

    if pastpaper_trends:
        latex_body += r"""\newpage
    \begin{center}
    \Huge \textbf{Past Paper Trends and Analysis}
    \end{center}   
        """
        #Key Stats
        latex_body += r"\section*{Key Stats}" + "\n"
        latex_body += r"\begin{itemize}" + "\n"
        latex_body += f"\\item  Average questions per paper: {trends['overall_trends']['average_questions_per_paper']}" + "\n"
        latex_body += f"\\item  Average marks per question: {trends['overall_trends']['average_marks_per_question']}" + "\n"
        latex_body += r"\end{itemize}" + "\n\n"
        
        #Instructions
        latex_body += r"\section*{Typical Instructions}" + "\n"
        latex_body += r"\begin{itemize}" + "\n"
        for instr in trends["overall_trends"]["typical_instructions"]:
            safe_instr = escape_latex(instr)
            latex_body += f"\\item {safe_instr}" + "\n"
        latex_body += r"\end{itemize}" + "\n\n"
        
        #Tips
        latex_body += r"\section*{Useful Tips}" + "\n"
        latex_body += r"\begin{itemize}" + "\n"
        for tip in trends["useful_tips"]:
            safe_tip = escape_latex(tip)
            latex_body += f"\\item {safe_tip}" + "\n"
        latex_body += r"\end{itemize}" + "\n\n"
        
        #Exam Strategy
        latex_body += r"\section*{Suggested Exam Strategy}" + "\n"
        latex_body += r"\begin{itemize}" + "\n"
        for strat in trends["possible_exam_strategy"]:
            safe_strat = escape_latex(strat)
            latex_body += f"\\item {safe_strat}" + "\n"
        latex_body += r"\end{itemize}" + "\n\n"
        
        #Images
        for fig in saved_figures:
            safe_fig = escape_latex(fig)
            latex_body += r"""\begin{center}
        \includegraphics[width=1.2\textwidth]{%s}
        \end{center}
            """ % safe_fig
            
        # ───  DEDUCT CREDITS NOW ─────────────────────────────────
    new_credits = credits - cost
    # update Supabase
    supabase.table("profiles") \
        .update({"credits": new_credits}) \
        .eq("id", user_id) \
        .execute()
    # show updated balance in sidebar
    st.sidebar.metric("Remaining Credits", new_credits)

    # ───  THEN RENDER OUTPUT ────────────────────────────────
    if latex_body:
        with st.spinner("Rendering PDF…"):
            pdf_fn = create_pdf_with_pylatex(latex_body, subject)
            st.success("✅ Your study materials are ready!")
            with open(pdf_fn, "rb") as f:
                st.download_button("Download PDF", f, file_name=pdf_fn)
    else:
        st.warning("No output generated — please check your selections.")
        
st.markdown("---")
st.info("Disclaimer: This tool provides AI-generated study support. Always cross check with your materials and syllabus.")
