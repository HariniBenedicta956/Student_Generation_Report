SYSTEM_PROMPT = (
    "You are an educational assessment expert. Generate a personalized student report "
    "in JSON format based on the student's performance data. Keep responses concise but insightful."
)


def build_prompt(student):
    scores = student.get("scores", {})
    scores_str = ", ".join(f"{subject}: {score}" for subject, score in scores.items())
    return (
        f"Student: {student.get('name')}\n"
        f"Class: {student.get('class')}\n"
        f"Scores: {scores_str}\n"
        f"Percentile: {student.get('percentile')}\n"
        f"Attendance: {student.get('attendance')}%\n\n"
        "Generate JSON with these fields:\n"
        "- summary (2 sentences)\n"
        "- strengths (3 bullet points)\n"
        "- improvements (3 bullet points)\n"
        "- recommendations (3 actionable tips)\n"
        "- career_guidance (1-2 sentences)\n"
        "- overall_insight (1 sentence)\n\n"
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
