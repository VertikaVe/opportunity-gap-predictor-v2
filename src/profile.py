from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class StudentProfile:
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    college: Optional[str] = None

    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    degree: Optional[str] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    semester: Optional[int] = None
    cgpa: Optional[float] = None

    skills: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    experience: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def is_empty(self) -> bool:
        return not self.skills and not self.name and not self.email


def manual_profile(
    name: str,
    skills: List[str],
    degree: Optional[str] = None,
    branch: Optional[str] = None,
    graduation_year: Optional[int] = None,
    semester: Optional[int] = None,
    cgpa: Optional[float] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    college: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
) -> StudentProfile:

    return StudentProfile(
        name=name,
        email=email,
        phone=phone,
        college=college,
        city=city,
        state=state,
        country=country,
        skills=skills,
        degree=degree,
        branch=branch,
        graduation_year=graduation_year,
        semester=semester,
        cgpa=cgpa,
    )