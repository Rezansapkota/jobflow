# Jobflow validation — 21 September 2026

The tested build is running locally at http://localhost:8768. Core local workflows pass validation. Fully unattended LinkedIn/SEEK automation and public hosting are not certified for production.

## Results

| Area | Evidence | Result |
| --- | --- | --- |
| Automated regression suite | 143 tests, 43.854 seconds; zero failures or skips | Passed |
| Browser interface | Applications, profile, job search, login and resume builder at 1440, 768, 390 and 320 px | 20 layouts passed, no horizontal overflow or browser errors |
| Profile and job workflows | Create/switch/save profiles, job import, duplicate detection, filters, review, approval and rejection | Passed in isolated databases and browser fixtures |
| Resume builder | Prefill, per-profile drafts, analysis, editing, stale-result invalidation and downloads | Passed |
| Documents | PDF, DOCX and text exports; selectable PDF text, pagination, Unicode, XML escaping, single-column reading order | Passed; a generated PDF was also visually inspected |
| Live local AI | Installed Qwen model analyzed a fictional candidate and job, retained employer/dates, selected relevant skills and rejected an unheld licence | Passed |
| AI preparation pipeline | Real Qwen assessment, resume and cover-letter generation from an injected fictional listing | Passed; no live application attempted |
| Certificates | Extraction validation, holder/expiry checks, profile isolation, attachment selection and uploads to simulated forms | Passed; model extraction is not credential authentication |
| Automation controls | Stop, approval fingerprint, changed documents, queue serialization, restart recovery and uncertain-result handling | Passed |
| Site forms | Intercepted LinkedIn/SEEK fixtures, resume/letter upload, unknown questions, invalid fields and confirmation recognition | Passed in fixtures only |
| Live LinkedIn | Read-only Chrome outside the restricted sandbox found 60 search links | Detail access required sign-in or verification |
| Live SEEK | Read-only Chrome outside the restricted sandbox | Verification required; no readable listings collected |
| Saved documents | Seven existing resume/cover-letter pairs checked for completeness and candidate-name consistency | Passed these limited checks; this does not certify every written claim |

All six frontend JavaScript files passed syntax checks. The final browser check verified that the server's build matches the current source and Ollama is available.

## Fixes delivered

- Serve the favicon from the same origin so the content security policy permits it.
- Require the matching active profile for resume and cover-letter downloads, preventing stale links from downloading another profile's documents.
- Hide another profile's automation activity when switching profiles.
- Continue local document preparation for collected jobs if the discovery browser fails; report the run as partial and retain Stop behavior.
- Reject generated residence, availability, relocation and work-rights claims independently of the model's own audit. A live generated cover letter exposed this issue. Failed audits use an extractive letter from saved facts.
- Strengthen the prose audit against invented connections between skills and duties.
- Update the browser workflow test for the current manual-add button label.
- Increment the tailoring version so older drafts are visibly marked for refresh.

## Remaining release limits

This is ready for local use with document review and human sign-in/verification. No real applications were submitted during testing. Passing fixture submissions does not prove that changing external site forms work unattended. Complete any site challenge in visible Chrome; automatic submission still needs separately approved documents and a supported application flow.

Four unsubmitted document pairs predate the updated tailoring checks, including one previously approved pair. They were preserved and are marked as older drafts. Use **Refresh these documents** in their review dialog, then read and approve the regenerated documents before using them. Tests cannot establish that every existing or future AI sentence is factually correct.

The server remains bound to this computer. Public deployment would need a separate authenticated service design; it was not performed or requested as a concrete hosting deployment.

## Reproduction and local artifacts

Run `.\.venv\Scripts\python.exe -m unittest discover -v` for the regression suite. Tests use isolated databases and intercepted application pages. Live discovery probes were read-only and used a fresh browser without your saved credentials.

Local artifacts are in ignored `data/qa/`: `unit-tests.log`, `final-browser-check.json`, `live-discovery.json`, the fictional AI resume analysis, and sample PDF/DOCX/text outputs. A SQLite backup was created before restarting the server. Your career profiles and application records were not replaced with test data.
