# Jobflow

A local application workspace for LinkedIn and SEEK. Built with Python, SQLite, plain JavaScript and an optional Playwright browser assistant.

## Start

```powershell
.\.venv\Scripts\python.exe start.py
```

Open http://127.0.0.1:8768. The launcher reuses an already running server. Keep the terminal open while using the app. If the virtual environment does not exist, create it with `python -m venv .venv`. This command does not require PowerShell script execution to be enabled.

To use a different port:

```powershell
.\.venv\Scripts\python.exe start.py --port 8769
```

Then open http://127.0.0.1:8769. Use the port printed by the launcher.

For browser application runs:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Install [Ollama](https://ollama.com/) and download the local model for AI features:

```powershell
ollama pull qwen3:8b
```

Keep Ollama running. Jobflow connects to its local service on port 11434; no cloud API key is needed.

The dashboard, profile, job queue and DOCX export work without Playwright.
Google Chrome is used for the dashboard and all agent browser sessions, including LinkedIn and SEEK. The launcher opens the dashboard in Chrome. Install Google Chrome first; Jobflow does not change your system-wide default browser.

## Use

1. Choose or create a named career profile, such as **Rejan IT profile** or **Rejan Aged Care profile**. Save relevant work history, skills, education, target roles and certifications in **My profile**.
2. Open **Job agent** for browser discovery, matching, document generation and application in one run. Or use **Find opportunities** for manual searching.
3. Add a job link, company, title and pasted description to the pipeline. Duplicate links are rejected even when tracking parameters differ.
4. Select jobs and click **Prepare selected**. Open each job to read or download its DOCX resume.
5. Choose **Manual handoff** or **Automatic submission**, then **Run selected**. Up to 10 ready applications are processed in order.
6. Sign in through the visible agent browser if needed. It has a separate persistent browser profile. A manual handoff stays open for up to five minutes per job. Your resume is available through the dashboard and at `data/<job-id>.docx`.

Automatic mode attempts LinkedIn Easy Apply and SEEK application forms. It fills recognised contact fields and exact saved question answers, uploads the resume to a recognised resume field, advances identifiable steps, and clicks an identifiable submit button. Unknown questions, consent controls, login, verification and unsupported steps hand control to you. This connector is experimental: site layouts vary and live submission has not been tested. A click alone never counts as a successful application; unrecognised confirmation leaves the application marked **Check submission**. Check the site before resetting it to Saved and preparing again.

## Account sign-in

In **My profile / Job site accounts**, save your LinkedIn and SEEK profile links (optional). Blank links open the site's account page. Start **Job agent**; it opens each selected account in a visible browser. Enter your login ID/password directly on the site, complete verification, check the account, then click **Account ready — continue** in Jobflow. Confirm each selected site once per run; the agent then searches using your saved target roles and location, assesses suitability with Qwen, creates an ATS-friendly resume and cover letter, and attempts supported applications within your limits.

Profile links alone do not sign you in or import your career history. Complete the career profile in Jobflow. Passwords are not collected by Jobflow or sent to Ollama. Browser sessions are stored locally under `data/browser-profiles/<profile-id>/chrome-browser/`, separately for each career profile, and excluded from Git. Treat this local folder as private because it contains signed-in sessions. New/copied profiles require their own sign-in; older shared sessions are not reused. Account confirmation times out after five minutes, and Cancel run stops before discovery. Site verification or unknown application questions may still need your input.

## Job agent

The app is reusable for any applicant. Each local workspace supports multiple named career profiles, but these are not separate authenticated user accounts. No applicant facts are built into the agent.

Use the **Active career profile** selector to switch. **New profile** can start blank or copy the current profile. Edit **Profile title** to rename it. Each profile has independent experience, skills, certifications, screening answers and search preferences. Switching saves any valid unsaved profile edits. During generation or application, switching is disabled.

Enter certifications manually, or use **Uploaded certificates** in My profile. Upload one certificate per PDF, DOCX, PNG or JPEG file (up to 10 MB, 10 PDF pages, 30 files per profile). PDF/DOCX text is extracted locally; images and scanned PDF pages use bundled local RapidOCR models. Qwen reads the extracted text and fills the certificate name, issuer, holder, issue/expiry dates and course codes. No document is sent to a cloud service. Image-only DOCX files need a PDF or image copy for OCR.

The **Certification section used in applications** combines manually entered details with enabled uploads whose holder matches the profile and whose extracted details pass checks. It feeds the ATS resume, job matching, summaries, cover letters and recognised certification text fields. Unreadable text, mismatched holders, missing issuers and expired/uninterpretable expiry dates require correction through **Edit details**. Extraction is not verification of authenticity. Blank expiry means expiry was not stated, not a claim of lifetime validity.

For each prepared job, certificate names, shortened names and saved course codes/keywords are matched against the job text. Relevant file IDs are saved with the application and shown in its details. The browser attaches the original files only to recognised certificate/licence/qualification/supporting-document fields that match the certificate or accept generic certificate evidence. The form's file-type and multiple-file constraints are respected; ambiguous single-file fields or unsupported formats require manual input. Files are never substituted into resume or cover-letter fields. Jobs without an attachment field retain the selected files for manual handoff. Specific yes/no eligibility questions still need exact saved answers.

Uploads belong to one named profile. Copying profile text does not copy uploaded files; upload the same certificate to each profile where needed. Files and extracted text are stored under ignored `data/`, excluded from GitHub. **Remove from profile** disables a certificate and removes it from current use; its file remains locally for historical applications. Editing certificates invalidates that profile's unsubmitted drafts. Reprepare jobs to refresh their document and attachment selection.

Jobs belong to the profile that found or imported them. Prepared applications save a profile snapshot so their resume, cover letter and form answers stay consistent. Editing a profile invalidates only that profile's unsubmitted drafts. Existing single-profile data is migrated to **Default profile**. Duplicate job URLs are prevented across the workspace to avoid applying twice with different career profiles.

Save target roles (comma separated), search location, career facts, work rights and other constraints. In **Job agent**, select sites, a match threshold and run limits. **Search, prepare and apply** starts the full workflow; **Search and prepare only** stops before application forms.

The agent opens a visible browser, reads up to 3 search pages per site and role, canonicalises links and skips existing jobs. It extracts job descriptions from JobPosting data or site-specific page elements. Local Qwen assesses role/location fit and mandatory requirements. Only jobs above the score threshold with no identified missing or unknown mandatory requirements are selected. An AI score is an estimate, not proof of eligibility; review assessments in each job.

For selected jobs, Qwen writes a summary, orders existing skills and writes a cover letter. Employment history and education remain verbatim. Both documents can be downloaded as DOCX. The browser uploads them to recognised resume/cover-letter fields (or fills a cover-letter text field). Some employers do not offer a cover-letter field. Unknown fields and consent still require user input.

The default run inspects at most 10 new jobs and attempts at most 3 applications. Limits are configurable up to 30 inspected jobs and 10 attempts. **Stop run** takes effect after the current browser or model operation; a submitted application cannot be undone. A failed/ambiguous application is not automatically retried. Run activity and per-job assessments are saved locally. This is a finite run, not a recurring background schedule.

SEEK may show a browser verification page; the visible browser waits up to five minutes for the user to complete it. LinkedIn may require sign-in. No challenge is bypassed. Extraction failures are logged instead of being treated as real job matches.

## Current boundaries

Resume downloads and browser uploads use the same ATS-friendly DOCX writer: one column, Arial 11 pt body text, standard section headings, one-inch margins, and contact information in ordinary body paragraphs. There are no tables, text boxes, images, headers or footers. The DOCX stores real selectable text and keeps source employment and education in their original order. Enter roles most recent first, with complete job titles, employers and clear date ranges; the agent does not invent or guess those details. A plain-text resume download lets you inspect the linear reading order.

This format follows [Greenhouse's published parsing guidance](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse). It improves compatibility; no format guarantees successful parsing or ranking by every ATS. Match scores in the app are not ATS scores. Existing saved resumes receive the new Word styling when downloaded again; prepare them again to refresh the text structure and contact lines.

- **Local Qwen AI** uses your installed `qwen3:8b` through Ollama at `127.0.0.1:11434` to write a job-specific summary and order your existing skills. Work history, contact details and education remain unchanged. Review generated summaries for accuracy; prompts cannot guarantee factuality. Requests stay local, with no cloud fallback or API key. Failed drafts leave existing resumes unchanged and show the error inside the job.
- **Basic tailoring** remains available: matching skills move first and all other profile text stays verbatim. Select the engine beside **Prepare selected**. Local AI processes up to 10 selected jobs sequentially while the dashboard stays responsive. Editing is paused during generation to keep profile snapshots consistent.
- Browser discovery is available through **Job agent**. There is no recurring search scheduler or universal application connector.
- Login and CAPTCHA are handled by you. No stealth mechanisms or verification bypass.
- LinkedIn prohibits third-party site automation, and SEEK restricts automated access except through permitted interfaces. Using automated mode can risk account restrictions. Manual handoff is the default. See [LinkedIn guidance](https://www.linkedin.com/help/linkedin/answer/a1340567/automated-activity-on-linkedin?lang=en) and [SEEK terms](https://au.seek.com/terms/en).
- Browser confirmation recognition is intentionally conservative. You can update statuses manually after checking your applications.

## Data and development

All profile text, resume snapshots and application records are stored in `data/workspace.db`. Generated resumes and browser sign-in state are under `data/`. These files contain personal information and are not encrypted. They are excluded from Git. The server binds to loopback only, validates Host and requires a per-session token for changes. Do not expose it on a public network.

Run checks:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
node --check static/ui.js
```

`app.py` contains persistence, tailoring and HTTP endpoints. `browser_agent.py` contains the browser connector. `static/` contains the interface. Set `PORT` to use another local port.

`discovery.py` extracts search results and descriptions; `automation.py` orchestrates bounded runs; `local_ai.py` calls Ollama. Tests use fictional profiles and intercepted local pages, never live submissions. Optional `python smoke_checks.py` checks public search pages without submitting; `python smoke_checks.py --model` exercises matching and cover-letter generation with a fictional profile without saving it to the workspace.

## Review before submission

Job agent searches and prepares documents, then leaves jobs in the pipeline for review. Open each job to preview and download its tailored resume and cover letter. Click **I reviewed both documents - approve**, then select the approved job and use **Run selected** with **Automatic submission**. The server blocks automatic runs without approval of the current documents and attachments. Regenerating documents or changing application facts requires a fresh review. Manual handoff remains under your control.

Chrome keeps a separate session for each career profile. Sign in once in its new agent window. Older Edge/Chromium sessions are not copied. Run `python start.py --port 8775` to open the updated local dashboard in Chrome.

## Combined job search

Use **Search jobs** on the dashboard or **Job search** in the sidebar. One **Search LinkedIn + SEEK** action searches both sites with the active profile, alternates their results within the overall limit, and saves jobs in one pipeline. Each site still needs its own sign-in. Suitable jobs receive documents for approval before submission.

## Google sign-in rejected

Google may reject sign-in from an automation-controlled browser, including Chrome. Signing into Chrome is not required to use Jobflow. In the agent window, return to LinkedIn or SEEK and use the site's own email sign-in option where offered. Enter the job-site password, not your Google password. For a Google-only account, use ordinary Chrome and the job site's account settings/help to establish an alternative sign-in method if supported. Signing into ordinary Chrome does not automatically sign in the separate agent session. Jobflow does not bypass this restriction. See https://support.google.com/accounts/answer/7675428 .
