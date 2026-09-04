"""AVD Prep: install the "AVD Change Report" Reports-app template from this repository.

Load this repository into Nautobot as a Git Repository with the "jobs" provided content; the job then reads the
report definition from the checkout's own `reports/avd_change_report/` directory (report.yaml, Jinja blocks,
saved-view and GraphQL specs). Nothing has to be copied onto the Nautobot filesystem. Requires the Reports app.
"""
from __future__ import annotations

from pathlib import Path

from nautobot.apps.jobs import BooleanVar, Job
from nautobot_reports.models import ReportTemplate
from nautobot_reports.report_import import ReportTemplateImporter

name = "AVD Prep"  # module-level `name` is what Nautobot shows as the job grouping in the UI

REPORT_NAME = "avd_change_report"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"  # <repo>/reports


def load_report(user, overwrite: bool, logger, source: Path = REPORTS_DIR, report_name: str = REPORT_NAME):
    """Get-or-create the report template (owner=user, shared, not built-in) and build its blocks from the definition.

    Returns (template, action) where action is "created", "rebuilt" or "unchanged". Saved views and GraphQL queries
    listed in the definition's required_objects are created by the Reports app's importer when missing.
    """
    definition = ReportTemplateImporter.load_definition(report_name, source)
    template_name = definition["name"]
    existing = ReportTemplate.objects.filter(name=template_name).order_by("-is_shared").first()
    if existing and not overwrite:
        logger.info("Report template %r already exists (%d blocks); leaving it untouched. Enable `overwrite` to rebuild it from %s.",
                    template_name, existing.blocks.count(), source, extra={"object": existing})
        return existing, "unchanged"
    if existing is None:
        template, created = ReportTemplate.objects.get_or_create(
            name=template_name, owner=user, defaults={"description": definition.get("description", ""), "is_shared": True})
    else:
        template, created = existing, False
    if not created:
        template.description = definition.get("description", "")
        template.is_shared = True
        template.validated_save()
    ReportTemplateImporter.build(template, report_name=report_name, source_path=source)
    action = "created" if created else "rebuilt"
    logger.success("Report template %r %s from %s (%d blocks).", template_name, action, source, template.blocks.count(), extra={"object": template})
    return template, action


class LoadAvdChangeReport(Job):
    """Install (or rebuild) the AVD Change Report template, with its saved views and GraphQL queries."""

    overwrite = BooleanVar(default=False, description="Rebuild the template from this repository's definition even if it already exists. This discards any edits made to the template in the UI.")

    class Meta:  # pylint: disable=too-few-public-methods
        name = "Load AVD Change Report"
        description = "Creates the 'AVD Change Report' Reports-app template (blocks, saved views, GraphQL queries) from reports/avd_change_report in this repository. Idempotent; `overwrite` rebuilds it."
        has_sensitive_variables = False

    def run(self, overwrite=False):  # pylint: disable=arguments-differ
        if not (REPORTS_DIR / REPORT_NAME / "report.yaml").exists():
            raise FileNotFoundError(f"{REPORTS_DIR / REPORT_NAME / 'report.yaml'} not found in the repository checkout")
        template, action = load_report(self.user, overwrite, self.logger)
        return {"template": str(template.pk), "name": template.name, "action": action, "blocks": template.blocks.count(), "source": str(REPORTS_DIR)}


