# Jobflow automation requirements

Build a reusable local job-search assistant for multiple named career profiles. Use Google Chrome for LinkedIn and SEEK and local Ollama/Qwen for matching and writing. Provide one combined search based on the selected profile's roles, location, experience, skills, work rights and verified certifications.

Search accessible listings without requiring sign-in upfront. If a site blocks access or requires verification, report that site clearly and continue with the other site. Provide separate account-connection controls. Keep passwords on the job sites and do not bypass login or verification restrictions.

Merge new listings into one pipeline without duplicating previously tracked URLs. Revisit unfinished saved jobs without overwriting completed documents or retrying uncertain submissions. Respect per-run limits and a Stop control. Report the current stage and distinguish no results, partial results, blocked access, document errors and successful preparation.

Assess mandatory requirements separately from an estimated match score. Do not invent qualifications or infer eligibility where evidence is missing. Produce a distinct ATS-friendly resume and cover letter for suitable jobs, using the selected career profile and relevant certification evidence.

Show both documents before submission. Require approval of the exact documents and attachments, and invalidate approval when they change. Submit only supported forms with approved documents. Pause for unknown answers, declarations, verification and external application flows. Confirm successful submission from the site; preserve uncertain outcomes without automatically retrying.

Make the dashboard show clear next actions. Preserve saved work if Chrome closes or a run fails. Check Ollama before starting, explain failures in plain language, and ensure the launcher opens the current build. Validate changes with isolated Chrome application fixtures and read-only live discovery checks; do not claim live submission works until it has actually been confirmed.
