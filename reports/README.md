# reports

Nautobot Reports-app templates for the NTC + Arista lifecycle demo, in the same `report.yaml` + Jinja format as
the app's built-in reports (`nautobot_reports/builtin_reports/*`).

| Folder | Template | Purpose |
| --- | --- | --- |
| `avd_change_report/` | AVD Change Report | Per-change artifact: the latest Operational Compliance snapshot comparison in the reporting period, told in prose (what changed, where, which before/after and AVD validation checks passed or failed), plus intent-vs-configuration amplification and the Nautobot change log for the window. |

Loading into Nautobot (no app code needed): create a `ReportTemplate` and call the app's importer with this
directory as `source_path`:

    from pathlib import Path
    from nautobot_reports.report_import import ReportTemplateImporter
    ReportTemplateImporter.build(template, "avd_change_report", source_path=Path("<clone>/reports"))

The importer creates the saved views (`savedviews_spec.json`) and GraphQL queries (`graphql_spec.json`) named in
`report.yaml` `required_objects`, then rebuilds the blocks. In the nautobot-3.1 project this is wrapped by
`avd_demo/reports/import_report.py`. Publish with the app's **Publish Report** job; `reporting_period_start` is the
look-back window in days used to pick "the change".
