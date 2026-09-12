"""Service for transforming raw resume text and files into validated CandidateProfile."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Union
import httpx
from pydantic import ValidationError

from applypilot.domain.profile import CandidateProfile
from applypilot.modules.profile.ingestion.extractors import PdfExtractor, TexExtractor


class ResumeIngestionError(Exception):
    """Raised when resume extraction, LLM structuring, or profile validation fails."""
    pass


class ResumeIngestionService:
    """Extracts raw resume content and structures it into CandidateProfile using LLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("APPLYPILOT_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.base_url = (
            base_url
            or os.getenv("APPLYPILOT_LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.getenv("APPLYPILOT_LLM_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    async def parse_file(self, file_path: Union[Path, str]) -> CandidateProfile:
        """Extract text from resume file (.pdf or .tex) and transform into CandidateProfile.

        Args:
            file_path: Path to .pdf or .tex resume document.

        Returns:
            Validated CandidateProfile instance.

        Raises:
            FileNotFoundError: If target file does not exist.
            ValueError: If file format is not .pdf or .tex.
            ResumeIngestionError: If LLM call or schema validation fails.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Resume file not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = PdfExtractor().extract_text(path)
        elif suffix == ".tex":
            text = TexExtractor().extract_text(path)
        else:
            raise ValueError(
                f"Unsupported resume file format: {suffix}. Only .pdf and .tex are supported."
            )

        return await self.parse_text(text)

    async def parse_text(self, text: str) -> CandidateProfile:
        """Structure raw resume text into CandidateProfile using schema-constrained LLM.

        Args:
            text: Raw or extracted resume text content.

        Returns:
            Validated CandidateProfile instance.

        Raises:
            ResumeIngestionError: If API key is missing, network fails, or validation fails.
        """
        if not self.api_key:
            raise ResumeIngestionError(
                "No API key provided for resume ingestion. Set APPLYPILOT_LLM_API_KEY or OPENAI_API_KEY."
            )

        system_prompt = (
            "You are a high-precision recruitment profile extraction system.\n"
            "Your task is to parse raw resume text into a structured JSON object conforming strictly "
            "to the CandidateProfile domain schema.\n\n"
            "CRITICAL ANTI-HALLUCINATION RULES:\n"
            "1. Extract ONLY verifiable facts explicitly stated in the resume text.\n"
            "2. NEVER invent, assume, or extrapolate candidate information.\n"
            "3. If an optional field (such as ethnicity, political_status, health_status, GPA, test scores) "
            "is not explicitly mentioned, leave it null or omit it.\n"
            "4. Dates must be formatted as strings 'YYYY-MM-DD', 'YYYY-MM', or objects {'year': int, 'month': int, 'day': int}.\n"
            "5. Generate stable semantic IDs for education ('edu_bachelor', 'edu_master'), experiences ('exp_1'), "
            "and projects ('proj_1').\n"
            "6. Output must be a single valid JSON object."
        )

        user_prompt = (
            f"Please extract candidate facts from the following resume text:\n"
            f"--------------------\n"
            f"{text}\n"
            f"--------------------\n\n"
            f"JSON structure template:\n"
            f'{{\n'
            f'  "schema_version": "1.1.0",\n'
            f'  "profile_id": "cand_...",\n'
            f'  "identity": {{\n'
            f'    "name": "...",\n'
            f'    "gender": "male" | "female" | null,\n'
            f'    "birth_date": "YYYY-MM-DD" | null,\n'
            f'    "ethnicity": null,\n'
            f'    "health_status": null\n'
            f'  }},\n'
            f'  "contact": {{\n'
            f'    "mobile": "...",\n'
            f'    "email": "...",\n'
            f'    "current_city": "..."\n'
            f'  }},\n'
            f'  "education": [\n'
            f'    {{\n'
            f'      "id": "edu_bachelor",\n'
            f'      "school_name": "...",\n'
            f'      "education_level": "bachelor" | "master" | "doctor" | "associate" | "high_school",\n'
            f'      "major": "...",\n'
            f'      "start_date": "YYYY-MM",\n'
            f'      "end_date": "YYYY-MM"\n'
            f'    }}\n'
            f'  ],\n'
            f'  "experiences": [\n'
            f'    {{\n'
            f'      "id": "exp_1",\n'
            f'      "company_name": "...",\n'
            f'      "job_title": "...",\n'
            f'      "experience_type": "internship" | "full_time" | "research" | "student_org" | "volunteer",\n'
            f'      "start_date": "YYYY-MM",\n'
            f'      "end_date": "YYYY-MM"\n'
            f'    }}\n'
            f'  ],\n'
            f'  "projects": [\n'
            f'    {{\n'
            f'      "id": "proj_1",\n'
            f'      "project_name": "...",\n'
            f'      "role": "...",\n'
            f'      "start_date": "YYYY-MM",\n'
            f'      "end_date": "YYYY-MM"\n'
            f'    }}\n'
            f'  ],\n'
            f'  "skills": [\n'
            f'    {{\n'
            f'      "category": "technical",\n'
            f'      "name": "..."\n'
            f'    }}\n'
            f'  ]\n'
            f'}}'
        )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, json=payload, headers=headers)
            except httpx.HTTPError as e:
                raise ResumeIngestionError(f"LLM API request failed: {e}") from e

        if resp.status_code != 200:
            raise ResumeIngestionError(
                f"LLM API returned error status {resp.status_code}: {resp.text}"
            )

        try:
            api_data = resp.json()
            raw_content = api_data["choices"][0]["message"]["content"]
        except Exception as e:
            raise ResumeIngestionError(f"Invalid API response payload: {e}") from e

        content = self._clean_markdown_json(raw_content)

        try:
            profile_dict = json.loads(content)
        except json.JSONDecodeError as e:
            raise ResumeIngestionError(f"Failed to parse LLM response as JSON: {e}") from e

        if not isinstance(profile_dict, dict):
            raise ResumeIngestionError("Parsed LLM output is not a JSON dictionary.")

        if not profile_dict.get("profile_id"):
            profile_dict["profile_id"] = "cand_profile"

        try:
            return CandidateProfile.model_validate(profile_dict)
        except ValidationError as e:
            raise ResumeIngestionError(f"Profile validation failed: {e}") from e

    @staticmethod
    def _clean_markdown_json(raw_text: str) -> str:
        """Strip markdown code fence wrapper if present."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text
