"""AVD Compliance: the chain to run after a real change on the AVD fabric.

Before the change: take an Operational Compliance snapshot (e.g. "CHG-1234 pre") of the AVD devices.
After the change: run this chain. It takes the post snapshot with exactly the pre snapshot's devices and rules,
compares the two with the Operational Compliance app, and publishes the "AVD Change Report" so the report is bound
to this change. Requires: nautobot-operational-compliance, nautobot-reports, nautobot-tools (ChainingJob), and the
report template installed by the "Load AVD Change Report" job.

Self-contained on purpose: this module is served from the repository through Nautobot's Git Repository job content.
"""
from __future__ import annotations

from nautobot.apps.jobs import BooleanVar, ObjectVar, StringVar
from nautobot.dcim.models import Device
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import Job as JobModel
from nautobot.extras.models import JobResult
from nautobot_operational_compliance.jobs import CompareSnapshots, TakeSnapshot
from nautobot_operational_compliance.models import Snapshot, ValidationResult
from nautobot_reports.jobs import PublishReport
from nautobot_reports.models import PublishedReport, ReportTemplate
from nautobot_tools.choices import JobChainStepStatusChoices
from nautobot_tools.job_chaining import ChainingJob

name = "AVD Compliance"  # module-level `name` = job grouping shown in the Nautobot UI

DEVICE_TAG = "avd"                          # devices of the AVD fabric
REPORT_TEMPLATE_NAME = "AVD Change Report"  # installed by the "Load AVD Change Report" job
# Absolute rules that legitimately FAIL on the NTC lab (documented in oc/README.md); excluded from the failure count.
EXPECTED_LAB_FAILURES = {"NTP Synchronised"}


def result_rows(job_results):
    """Flatten the ValidationResults created by the given JobResults."""
    qs = ValidationResult.objects.filter(job__in=job_results).select_related("post__device", "post__validation_rule")
    return [{"device": vr.post.device.name, "rule": vr.post.validation_rule.name, "match": vr.match, "two_sided": vr.pre_id is not None} for vr in qs]


class PostChangeValidation(ChainingJob):
    """After a real change: take the post snapshot, compare it with the pre snapshot, publish the change report."""

    pre_snapshot = ObjectVar(model=Snapshot, required=False,
                             description="The snapshot taken BEFORE the change. The post snapshot uses exactly its devices and rules. Leave empty to use the most recent snapshot covering the AVD devices.")
    snapshot_name = StringVar(default="", required=False, description="Name for the post-change snapshot. Default: the pre snapshot's name followed by ' post'.")
    publish = BooleanVar(default=True, description="Publish the 'AVD Change Report' for this change.")

    class Meta:  # pylint: disable=too-few-public-methods
        name = "Arista AVD Post Change Validation"
        description = "Take the post-change snapshot with the pre snapshot's devices and rules, compare the two with Operational Compliance, and publish the AVD Change Report for exactly this change."
        has_sensitive_variables = False
        rollback_on_failure = False
        soft_time_limit = 1800
        time_limit = 2100
        steps_to_display = ["Post Snapshot", "Compare", "Publish Report"]

    # -- stages run as their own JobResults so the comparison job can pair two snapshots and every stage is linkable
    def _execute(self, step_name, job_class, **job_kwargs):
        self.set_step_status(step_name, JobChainStepStatusChoices.STARTED)
        job_model = JobModel.objects.get(module_name=job_class.__module__, job_class_name=job_class.__name__)
        jr = JobResult.execute_job(job_model, self.user, job_kwargs=job_kwargs)
        if jr.status != JobResultStatusChoices.STATUS_SUCCESS:
            self.set_step_status(step_name, JobChainStepStatusChoices.FAILURE)
            self.logger.error("%s failed (JobResult %s): %s", step_name, jr.pk, jr.traceback or jr.result, extra={"object": jr})
            raise RuntimeError(f"{step_name}: {job_class.__name__} ended with {jr.status}")
        self.set_step_status(step_name, JobChainStepStatusChoices.FINISHED)
        self.logger.info("%s done: [%s](%s)", step_name, jr.job_model.name, jr.get_absolute_url(), extra={"object": jr})
        return jr

    def _take_snapshot_like(self, step_name, snapshot, snapshot_name):
        """Take a snapshot with exactly the devices and validation rules of `snapshot`."""
        outputs = snapshot.command_outputs.all()
        kwargs = {
            "snapshot_name": snapshot_name,
            "validation_rules": sorted({str(pk) for pk in outputs.values_list("validation_rule_id", flat=True)}),
            "device": sorted({str(pk) for pk in outputs.values_list("device_id", flat=True)}),
            "compare_against_latest_snapshot": False,
            "fail_job_on_task_failure": False,
            "debug": False,
        }
        jr = self._execute(step_name, TakeSnapshot, **kwargs)
        return jr, Snapshot.objects.get(job_result=jr)

    def _compare(self, pre, post):
        return self._execute("Compare", CompareSnapshots, pre_snapshot=str(pre.pk), post_snapshot=str(post.pk), fail_fast=False)

    def _publish_report(self, label):
        template = ReportTemplate.objects.filter(name=REPORT_TEMPLATE_NAME).order_by("-is_shared").first()
        if template is None:
            self.logger.warning("Report template %r not found; skipping Publish Report (run 'Load AVD Change Report' first).", REPORT_TEMPLATE_NAME)
            self.set_step_status("Publish Report", JobChainStepStatusChoices.SKIPPED)
            return None
        before = PublishedReport.objects.filter(report_template=template).order_by("-published_at").first()
        jr = self._execute("Publish Report", PublishReport, report_template=str(template.pk), reporting_period_start=1)
        published = PublishedReport.objects.filter(report_template=template).order_by("-published_at").first()
        if published and (before is None or published.pk != before.pk):
            self.logger.success("Report for `%s`: [%s](%s)", label, template.name, published.get_absolute_url(), extra={"object": published})
        return jr

    # -- workflow
    def workflow(self, context):
        inputs = context["input"]
        pre = inputs.get("pre_snapshot")
        if pre is None:
            pre = Snapshot.objects.filter(command_outputs__device__tags__name=DEVICE_TAG).distinct().order_by("-created").first()
            if pre is None:
                raise RuntimeError("No earlier snapshot covers the AVD devices; take a pre-change snapshot first (Operational Compliance → Take Snapshot).")
            self.logger.info("No pre snapshot given; using the most recent one: [%s](%s)", pre, pre.get_absolute_url(), extra={"object": pre})
        pre_outputs = pre.command_outputs.all()
        n_dev = len(set(pre_outputs.values_list("device_id", flat=True)))
        n_rules = len(set(pre_outputs.values_list("validation_rule_id", flat=True)))
        self.logger.info("Post snapshot will cover the same scope as the pre snapshot: %d device%s, %d rule%s.", n_dev, "s" if n_dev != 1 else "", n_rules, "s" if n_rules != 1 else "")
        post_name = inputs.get("snapshot_name") or f"{pre.name} post"
        post_jr, post = self._take_snapshot_like("Post Snapshot", pre, post_name)
        cmp_jr = self._compare(pre, post)
        rows = result_rows([post_jr, cmp_jr])
        two = [r for r in rows if r["two_sided"]]
        one = [r for r in rows if not r["two_sided"]]
        changed = [f"{r['device']}: {r['rule']}" for r in two if r["match"] == "FAIL"]
        failed = [f"{r['device']}: {r['rule']}" for r in one if r["match"] == "FAIL" and r["rule"] not in EXPECTED_LAB_FAILURES]
        self.logger.info("Change window: %d before/after checks, %d changed (%s). Absolute checks: %d, %d failed (%s).",
                         len(two), len(changed), ", ".join(changed) or "none", len(one), len(failed), ", ".join(failed) or "none")
        if inputs.get("publish", True):
            self._publish_report(pre.name)
        line = f"Result: {len(changed)} change{'s' if len(changed) != 1 else ''} detected, {len(failed)} failed absolute check{'s' if len(failed) != 1 else ''} (known lab conditions excluded)."
        if changed or failed:
            self.logger.warning(line)
        else:
            self.logger.success(line)
        return []  # every stage ran as its own JobResult above; nothing left for the chain runner
