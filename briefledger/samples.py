"""Small synthetic sources, authored for this workbench; no production/customer data."""

SAMPLES = [
    (
        "release-runbook.md",
        """# Release readiness runbook

Synthetic sample · Northstar product team · version 1.4

## Before a release
The release lead checks that the deployment candidate passed integration tests.
A second engineer reviews database changes and confirms the rollback plan.
All sample environment credentials are managed outside this document.
The release lead records the candidate version and expected customer impact.

## Rollback ownership
The release lead owns the rollback decision. The on-call engineer executes it.
A rollback begins when the error rate stays above two percent for five minutes.
Pause new deployments before starting rollback. Keep the incident channel open.
The rollback checklist requires a known-good artifact and a database compatibility check.
Do not roll back a destructive database migration without an approved recovery plan.

## Rollback checklist
1. Announce the rollback in the incident channel and record the start time.
2. Select the last verified release artifact from the deployment history.
3. Confirm that the prior application version can read the current database schema.
4. Deploy the known-good artifact to the sample staging environment first.
5. Verify health checks, payment simulations, and background job processing.
6. Record the final version and post a short recovery update.

## After deployment
Watch the error rate and latency dashboards for at least fifteen minutes.
The release lead closes the deployment record after smoke checks complete.
Keep failed release artifacts available for investigation; do not promote them again.
These thresholds are illustrative training values, not production operational advice.
""",
    ),
    (
        "incident-response.md",
        """# Incident response handbook

Synthetic sample · Service operations · revision 3

## First response
The on-call engineer acknowledges an incident within ten minutes during the sample rota.
Create an incident channel and record when the customer-visible symptoms began.
The incident commander coordinates the response; the technical lead investigates.
Do not place access tokens, customer data, or passwords in the incident timeline.

## Severity and communication
A severity-one incident affects the main workflow for most users.
The communications lead posts a concise update every twenty minutes.
Each update states the observed impact, current mitigation, and time of the next update.
Avoid claims about a root cause until there is supporting evidence.

## Rollback during an incident
Use the release readiness runbook when a recent deployment is the likely trigger.
The release lead owns rollback approval; the on-call engineer performs the steps.
A rollback does not replace checking data consistency and queued work.
If rollback is unsafe, isolate the failing path and document the temporary mitigation.

## Recovery and follow-up
Recovery is confirmed only after the main workflow and dependent jobs pass checks.
Schedule a review within two working days, including a factual timeline.
Assign each follow-up action an owner and a review date.
This handbook is fictional material for exercising search and citation behavior.
""",
    ),
    (
        "access-and-retention.md",
        """# Access and retention policy

Synthetic sample · Internal controls · November edition

## Access reviews
Workspace owners review member access every ninety days in this sample policy.
An access review checks each person's current role, team, and continued need.
Remove access when a member leaves the team or no longer needs the collection.
Viewers may inspect published material; editors may update working documents.
Never infer authorization from a display name or user-editable profile field.

## Document retention
Draft project notes are retained for thirty days after the project closes.
Approved decision records are retained for one year in this fictional policy.
Before deleting a document, check whether another record still cites it.
Deletion removes both the source text and its searchable passages from BriefLedger.

## Collection privacy
BriefLedger stores a separate document database for each browser collection.
Its browser cookie is a capability: possession of the cookie grants collection access.
The collection expires seven days after creation; clearing the cookie loses access.
A public demo on ephemeral storage may reset after a service restart.
Upload only test documents. These sample controls are not a compliance guarantee.

## Exceptions
An exception record must identify the owner, reason, and next review date.
A policy exception does not remove the requirement to validate source evidence.
""",
    ),
    (
        "search-method-notes.md",
        """# How this workbench retrieves evidence

Synthetic sample · Retrieval notes · Read me first

## Lexical retrieval
BriefLedger uses SQLite FTS5, a full-text search engine built into SQLite.
Search words are quoted and combined with AND, so each searchable term must match.
English stemming can match related word forms; this is not semantic understanding.
BM25 ranks matching passages. Smaller internal BM25 values indicate better matches.
The interface shows rank order rather than an invented confidence percentage.

## Source locations
Documents are split into overlapping passages of up to fourteen hundred characters.
Each passage retains its character offsets and original source line range.
Click View source to inspect the complete text and the highlighted source lines.
The excerpt is copied from the uploaded text, with matching terms highlighted.
BriefLedger renders Markdown and HTML as plain text; it does not execute document markup.

## When there is no evidence
A no-match outcome means no passage contains all the requested searchable terms.
Try fewer words, a more specific keyword, or upload a relevant source.
BriefLedger does not invent an answer or cite a source it did not retrieve.
It does not call an LLM, embed documents, browse the web, or send text to an AI provider.

## Limits
This small workbench is designed for UTF-8 text and Markdown, not scanned PDFs.
A source may be at most 128 KiB, and a collection may contain thirty sources.
Documents are private to this browser collection, not a shared global public library.
""",
    ),
]
