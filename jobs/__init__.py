"""Nautobot Jobs sourced from this repository (GitRepository provided content: extras.job).

Nautobot imports this package and expects the jobs to be registered from here, so each job module is imported below.
Each module sets its own module-level `name`, which Nautobot shows as the job grouping.
"""
from nautobot.apps.jobs import register_jobs

from .arista_avd_post_change_validation import PostChangeValidation
from .load_avd_change_report import LoadAvdChangeReport

register_jobs(LoadAvdChangeReport, PostChangeValidation)
