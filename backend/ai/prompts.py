from __future__ import annotations

import json

from backend.database.models import UserProfile
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.job_match import JobMatchResult
from backend.schemas.resume_analysis import CandidateProfile


def build_resume_analysis_messages(normalized_text: str) -> list[dict[str, str]]:
    schema = CandidateProfile.model_json_schema()
    schema_json = json.dumps(schema, ensure_ascii=True, indent=2)

    system_prompt = (
        "You extract structured candidate profile information from resume text. "
        "Return strict JSON only and match the provided schema exactly."
    )

    user_prompt = (
        "Extract candidate profile data only from the provided resume text.\\n\\n"
        "Rules:\\n"
        "1. Do not invent or infer information that is not explicitly present.\\n"
        "2. If information is missing, use null or an empty list.\\n"
        "3. Keep wording faithful to the source text for responsibilities, "
        "achievements, and summary.\\n"
        "4. Do not output markdown, prose, or explanations. Output JSON only.\\n"
        "5. Keep skills limited to explicit mentions from the resume text.\\n"
        "6. Keep date fields as strings when present; otherwise null.\\n\\n"
        f"Expected JSON schema:\\n{schema_json}\\n\\n"
        f"Resume text:\\n{normalized_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_job_analysis_messages(job_description: str) -> list[dict[str, str]]:
    schema = JobAnalysis.model_json_schema()
    schema_json = json.dumps(schema, ensure_ascii=True, indent=2)

    system_prompt = (
        "You are a structured job-description analyzer. "
        "Return strict JSON only and match the provided schema exactly."
    )

    user_prompt = (
        "Analyze the following job description and extract structured "
        "requirements.\\n\\n"
        "Rules:\\n"
        "1. Use ONLY information explicitly present in the job description.\\n"
        "2. Do not infer or invent technologies, years, education, certifications, "
        "locations, responsibilities, or benefits.\\n"
        "3. If information is missing or ambiguous, return null or an empty list "
        "according to the schema.\\n"
        "4. Distinguish required vs preferred requirements only when clearly stated; "
        "otherwise keep ambiguity without guessing.\\n"
        "5. Do not output markdown, prose, or explanations. Output JSON only.\\n"
        "6. Do not include candidate fit, scoring, ranking, or resume comparisons.\\n"
        "7. Do not convert broad responsibilities into required skills unless the "
        "description explicitly states that requirement.\\n\\n"
        f"Expected JSON schema:\\n{schema_json}\\n\\n"
        f"Job description:\\n{job_description}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_cover_letter_messages(
    *,
    profile: UserProfile,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
    job_title: str,
    company: str,
    job_description: str,
    match_result: JobMatchResult,
) -> list[dict[str, str]]:
    schema = {
        "type": "object",
        "properties": {"cover_letter": {"type": "string"}},
        "required": ["cover_letter"],
    }

    facts = {
        "profile": {
            "name": profile.name,
            "email": profile.email,
            "location": profile.location,
            "work_authorization": profile.work_authorization,
        },
        "candidate_summary": {
            "headline": resume_analysis.headline,
            "summary": resume_analysis.summary,
            "skills": [item.name for item in resume_analysis.skills],
            "recent_experience_titles": [
                item.title for item in resume_analysis.experience
            ],
        },
        "job": {
            "title": job_title,
            "company": company,
            "role_summary": job_analysis.role_summary,
            "required_skills": [item.name for item in job_analysis.required_skills],
            "preferred_skills": [item.name for item in job_analysis.preferred_skills],
        },
        "match": {
            "score": match_result.score,
            "matched_required_skills": match_result.matched_required_skills,
            "missing_required_skills": match_result.missing_required_skills,
            "strengths": match_result.strengths,
            "gaps": match_result.gaps,
        },
    }

    system_prompt = (
        "You draft concise professional cover letters as strict JSON. "
        "Never fabricate any candidate fact."
    )

    user_prompt = (
        "Write one concise cover letter draft for this application.\\n\\n"
        "Rules:\\n"
        "1. Use only factual information provided in FACTS.\\n"
        "2. Never invent employers, dates, achievements, certifications, "
        "or projects.\\n"
        "3. Keep to 3-5 short paragraphs.\\n"
        "4. If uncertain, omit that detail.\\n"
        "5. Return JSON only matching schema.\\n\\n"
        f"Schema: {json.dumps(schema, ensure_ascii=True)}\\n\\n"
        f"FACTS: {json.dumps(facts, ensure_ascii=True)}\\n\\n"
        f"JOB_DESCRIPTION: {job_description}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_screening_answer_messages(
    *,
    question: str,
    profile: UserProfile,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
    match_result: JobMatchResult,
) -> list[dict[str, str]]:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    facts = {
        "question": question,
        "profile": {
            "name": profile.name,
            "location": profile.location,
            "work_authorization": profile.work_authorization,
        },
        "resume": {
            "headline": resume_analysis.headline,
            "summary": resume_analysis.summary,
            "skills": [item.name for item in resume_analysis.skills],
            "experience_titles": [item.title for item in resume_analysis.experience],
        },
        "job": {
            "role_summary": job_analysis.role_summary,
            "required_skills": [item.name for item in job_analysis.required_skills],
        },
        "match": {
            "score": match_result.score,
            "strengths": match_result.strengths,
            "gaps": match_result.gaps,
        },
    }

    system_prompt = "You draft concise screening-question answers in strict JSON."
    user_prompt = (
        "Draft one answer for the question using only provided facts.\\n"
        "Never invent details. If uncertain, return an empty string.\\n"
        "Return JSON only matching schema.\\n\\n"
        f"Schema: {json.dumps(schema, ensure_ascii=True)}\\n"
        f"Facts: {json.dumps(facts, ensure_ascii=True)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
