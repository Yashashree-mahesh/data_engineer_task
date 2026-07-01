import re
from dataclasses import dataclass

from app.etl.extractor import ExtractedMaster


VALID_SCORES = {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"}
MONTHS = {
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
REQUIRED_FIELDS = {
    "rated_entity_name": "Rated entity",
    "sector": "CorporateSector",
    "country": "Country of origin",
    "currency": "Reporting Currency/Units",
}


@dataclass(frozen=True)
class ValidationIssue:
    rule_id: str
    severity: str
    field: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    source_filename: str
    issues: list[ValidationIssue]
    completeness_rate: float
    validity_rate: float

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def as_dict(self) -> dict:
        return {
            "source_filename": self.source_filename,
            "has_errors": self.has_errors,
            "completeness_rate": self.completeness_rate,
            "validity_rate": self.validity_rate,
            "issues": [issue.__dict__ for issue in self.issues],
        }


def validate_master(master: ExtractedMaster) -> ValidationReport:
    issues: list[ValidationIssue] = []
    present = 0
    for attr, label in REQUIRED_FIELDS.items():
        if getattr(master, attr):
            present += 1
        else:
            issues.append(ValidationIssue("required_field_present", "error", label, "Required field is missing"))

    if not master.rating_methodologies:
        issues.append(
            ValidationIssue("methodology_present", "warning", "Rating methodologies applied", "No methodology was provided")
        )
    elif len(set(master.rating_methodologies)) != len(master.rating_methodologies):
        issues.append(
            ValidationIssue("duplicate_methodology", "warning", "Rating methodologies applied", "Duplicate methodology value found")
        )

    if master.currency and not CURRENCY_PATTERN.match(master.currency):
        issues.append(
            ValidationIssue("currency_iso3_format", "error", "Reporting Currency/Units", "Currency must be a 3-letter uppercase ISO-like code")
        )

    if master.business_year_end_month and master.business_year_end_month not in MONTHS:
        issues.append(
            ValidationIssue("business_year_end_month", "warning", "End of business year", "Month value is not a recognized English month")
        )

    industry_names = [str(risk.get("name") or "") for risk in master.industry_risks]
    if len(set(industry_names)) != len(industry_names):
        issues.append(ValidationIssue("duplicate_industry_risk", "warning", "Industry risk", "Duplicate industry risk value found"))

    weight_sum = 0.0
    weighted_count = 0
    for index, risk in enumerate(master.industry_risks):
        score = str(risk.get("score") or "")
        normalized_score = score.replace("+", "").replace("-", "")
        if normalized_score and normalized_score not in VALID_SCORES:
            issues.append(
                ValidationIssue("industry_score_rating_scale", "error", f"industry_risks[{index}].score", f"Invalid score {score}")
            )
        weight = risk.get("weight")
        if not isinstance(weight, float):
            issues.append(ValidationIssue("industry_weight_numeric", "error", f"industry_risks[{index}].weight", "Invalid weight"))
            continue
        weighted_count += 1
        weight_sum += weight
        if weight < 0 or weight > 1:
            issues.append(
                ValidationIssue("industry_weight_range", "error", f"industry_risks[{index}].weight", "Weight must be between 0 and 1")
            )

    if weighted_count and abs(weight_sum - 1.0) > 0.001:
        issues.append(
            ValidationIssue("industry_weight_sum", "error", "Industry weight", f"Weights must sum to 1.0, got {weight_sum:.4f}")
        )

    validity_checks = max(1, len(master.industry_risks) * 2 + 1)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    return ValidationReport(
        source_filename=master.source_filename,
        issues=issues,
        completeness_rate=present / len(REQUIRED_FIELDS),
        validity_rate=max(0.0, (validity_checks - error_count) / validity_checks),
    )
