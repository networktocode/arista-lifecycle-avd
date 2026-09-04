# jobs

Nautobot Jobs served from this repository. Add the repository to Nautobot as a **Git Repository** with the
provided content **Jobs** (`extras.job`); Nautobot imports this `jobs/` package from its checkout.

| Grouping | Job | Purpose |
| --- | --- | --- |
| AVD Prep | Load AVD Change Report | Installs the Reports-app template from `reports/avd_change_report/` in this checkout (idempotent; `overwrite` rebuilds it). |
| AVD Compliance | Arista AVD Post Change Validation | After a change: post snapshot with the pre snapshot's devices and rules → Operational Compliance comparison → publish the AVD Change Report. Needs nautobot-operational-compliance, nautobot-reports and nautobot-tools. |

Requires the Nautobot Reports app (and, for the compliance chain, Operational Compliance and nautobot-tools) on the target instance. Enable the job after the first sync.

Nautobot discovers git-sourced jobs with `pkgutil.walk_packages`, which only descends into real packages: the repository
root therefore carries an `__init__.py` (Nautobot does not create one).
