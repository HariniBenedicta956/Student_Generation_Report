SYSTEM_PROMPT = (
    "You are an educational assessment expert. Generate a personalized student report "
    "in JSON format based on the student's performance data. Keep responses concise but insightful."
)


def build_prompt(student, custom_instructions=None):
    scores = student.get("scores", {})
    scores_str = ", ".join(f"{subject}: {score}" for subject, score in scores.items()) or "(none recorded)"

    # Raw CSV columns that weren't recognized as id/name/class/percentile/attendance
    # or a 0-100 subject score (e.g. survey answers, registration numbers, emails) —
    # kept so the model can actually reference/list them when asked to.
    fields = student.get("fields", {}) or {}
    fields_str = "\n".join(f"- {key}: {value}" for key, value in fields.items() if value not in (None, "")) or "(none)"

    priority_block = ""
    if custom_instructions:
        priority_block = (
            "PRIORITY INSTRUCTIONS FROM THE REPORT REQUESTER — these take precedence over the "
            "default field structure below. If they ask for a particular tone, focus, or template, "
            "or ask you to list specific questions/answers/results, follow them exactly, and put any "
            "such extra content in the optional 'custom_sections' field described below:\n"
            f"{custom_instructions}\n\n"
        )

    return (
        f"{priority_block}"
        f"Student: {student.get('name')}\n"
        f"Class: {student.get('class')}\n"
        f"Scores: {scores_str}\n"
        f"Percentile: {student.get('percentile')}\n"
        f"Attendance: {student.get('attendance')}%\n"
        f"Other recorded fields for this student (may include survey questions/answers, IDs, contact "
        f"info, etc.):\n{fields_str}\n\n"
        "Generate JSON with these fields:\n"
        "- summary (2 sentences)\n"
        "- strengths (3 bullet points)\n"
        "- improvements (3 bullet points)\n"
        "- recommendations (3 actionable tips)\n"
        "- career_guidance (1-2 sentences)\n"
        "- overall_insight (1 sentence)\n"
        "- custom_sections (OPTIONAL array of {\"heading\": string, \"content\": string}; only include "
        "this if the priority instructions above ask for specific extra content, such as listing "
        "questions and answers, a custom template section, or anything not covered by the fields "
        "above — otherwise omit it)\n\n"
        "Output only valid JSON."
    )


FALLBACK_NARRATIVE = {
    "summary": "This student has completed their assessment. Detailed AI-generated insights are temporarily unavailable.",
    "strengths": ["Performance data recorded", "Assessment completed", "Profile available for review"],
    "improvements": ["Detailed analysis pending", "Recommend manual review", "Retry AI generation later"],
    "recommendations": ["Consult subject teachers for detailed feedback", "Review raw scores in this report", "Regenerate this report later"],
    "career_guidance": "Career guidance will be available once AI generation succeeds.",
    "overall_insight": "Report generated using a fallback template due to a processing issue.",
}
