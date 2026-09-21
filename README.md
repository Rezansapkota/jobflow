# Jobflow

A local application workspace for LinkedIn and SEEK. Built with Python, SQLite, plain JavaScript and an optional Playwright browser assistant.

## Start

```powershell
.\.venv\Scripts\python.exe start.py
```

Use the address printed by the launcher. It remembers the latest port, reuses the matching build, and selects a free port when an older idle build occupies the previous address. Keep the terminal open while using the app. If the virtual environment does not exist, create it with `python -m venv .venv`. This command does not require PowerShell script execution to be enabled.

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
2. Open **Job search**, enter keywords, and select LinkedIn, SEEK, or both. Search finds matches and prepares documents for review; it does not submit applications.
3. Add a job link, company, title and pasted description to the pipeline. Duplicate links are rejected even when tracking parameters differ.
4. Select jobs and click **Prepare selected**. Open each job to read or download its DOCX resume.
5. Review the resume and cover letter, then click **Approve & apply**. This immediately queues that job for automatic submission; no mode selection or second Run click is needed. Approved jobs wait for the current browser operation and submit one at a time. Previously approved, unqueued jobs show **Apply approved**. **Reject** cancels a waiting job. **Apply approved selection** can start a batch of up to 10 already-approved jobs. For a manual application, use **Apply manually in Chrome** in the review dialog.
6. Sign in through the visible agent browser if needed. It has a separate persistent browser profile. A manual handoff stays open for up to five minutes per job. Your resume is available through the dashboard and at `data/<job-id>.docx`.

Automatic mode attempts LinkedIn Easy Apply and SEEK application forms. It fills recognised contact fields and exact saved question answers, uploads the resume to a recognised resume field, advances identifiable steps, and clicks an identifiable submit button. Unknown questions, consent controls, login, verification and unsupported steps hand control to you. This connector is experimental: site layouts vary and live submission has not been tested. A click alone never counts as a successful application; unrecognised confirmation leaves the application marked **Check submission**. Check the site before resetting it to Saved and preparing again.

## Resume Builder

Open **Resume Builder** in the sidebar. It prefills the selected career profile, including eligible certificate information. Edit your source facts, paste a job description, optionally enter the target title, and select **Analyze job & tailor resume**.

**Local AI** uses the installed Qwen model to compare key requirements with quoted profile evidence, select relevant experience and skills, and write a focused summary. It retains source employment headings and dates, checks generated prose against the selected facts, and flags missing or incomplete evidence for review. **Basic matching** works without Ollama and uses wording overlap; it does not assess whether qualifications are satisfied. Neither mode adds missing qualifications or provides an ATS score.

The local model connection is shown at the top of the builder, with **Check connection** to refresh its status. The LLM also considers saved target roles, location preferences, work rights, availability and other constraints, and application answers. These are available under **Saved information included in the analysis** and inform the fit review without being inserted into resume prose. Change these saved details in **My profile**.

Set **Detail level**, **Writing style**, **Emphasis** (role fit, transferable experience or verified achievements), and **Maximum skills** before generating. Length and style guide the local model rather than enforcing an exact page count; the skill limit is enforced. Basic matching supports the skill limit only. Preferences are saved per profile, and changing them clears the outdated tailored result. Local generation stays on Ollama at `127.0.0.1:11434` using `qwen3:8b`, without a cloud fallback.

Review the analysis and **Final tailored resume**, optionally edit the final text, then download PDF, Word or plain text. PDF requires Playwright and Google Chrome. Exports use selectable text, a single column and standard section headings without graphics or tables. These choices support parsing but cannot guarantee an ATS result.

Source edits, job descriptions and final resumes are saved separately for each profile in this browser. Editing source facts or the target job clears the outdated final resume so you can regenerate it. Tailoring does not change the saved career profile or submit an application. Active analysis resumes when this page is reloaded while the server is still running; a server restart requires starting unfinished analysis again. Browser drafts belong to the exact local address and port, so download a copy before clearing browser storage or changing the address.

## Account sign-in

Open **Login** and choose LinkedIn or SEEK. Credentials entered in this local page are used only for that login attempt and are not saved or sent to Ollama. Complete sign-in or verification in the site browser, then select **Account ready** in Jobflow. You can also use the account connection controls in My profile.

Browser sessions are stored locally under `data/browser-profiles/<profile-id>/chrome-browser/`, separately for each career profile and excluded from Git. New or copied profiles require their own sign-in. Profile links do not import career history. Login confirmation times out after five minutes; verification and unknown application questions may still require your input.

## Job agent

The app is reusable for any applicant. Each local workspace supports multiple named career profiles, but these are not separate authenticated user accounts. No applicant facts are built into the agent.

Use the **Active career profile** selector to switch. **New profile** can start blank or copy the current profile. Edit **Profile title** to rename it. Each profile has independent experience, skills, certifications, screening answers and search preferences. Switching saves any valid unsaved profile edits. During generation or application, switching is disabled.

Enter certifications manually, or use **Uploaded certificates** in My profile. Upload one certificate per PDF, DOCX, PNG or JPEG file (up to 10 MB, 10 PDF pages, 30 files per profile). PDF/DOCX text is extracted locally; images and scanned PDF pages use bundled local RapidOCR models. Qwen reads the extracted text and fills the certificate name, issuer, holder, issue/expiry dates and course codes. No document is sent to a cloud service. Image-only DOCX files need a PDF or image copy for OCR.

The **Certification section used in applications** combines manually entered details with enabled uploads whose holder matches the profile and whose extracted details pass checks. It feeds the ATS resume, job matching, summaries, cover letters and recognised certification text fields. Unreadable text, mismatched holders, missing issuers and expired/uninterpretable expiry dates require correction through **Edit details**. Extraction is not verification of authenticity. Blank expiry means expiry was not stated, not a claim of lifetime validity.

For each prepared job, certificate names, shortened names and saved course codes/keywords are matched against the job text. Relevant file IDs are saved with the application and shown in its details. The browser attaches the original files only to recognised certificate/licence/qualification/supporting-document fields that match the certificate or accept generic certificate evidence. The form's file-type and multiple-file constraints are respected; ambiguous single-file fields or unsupported formats require manual input. Files are never substituted into resume or cover-letter fields. Jobs without an attachment field retain the selected files for manual handoff. Specific yes/no eligibility questions still need exact saved answers.

Uploads belong to one named profile. Copying profile text does not copy uploaded files; upload the same certificate to each profile where needed. Files and extracted text are stored under ignored `data/`, excluded from GitHub. **Remove from profile** disables a certificate and removes it from current use; its file remains locally for historical applications. Editing certificates invalidates that profile's unsubmitted drafts. Reprepare jobs to refresh their document and attachment selection.

Jobs belong to the profile that found or imported them. Prepared applications save a profile snapshot so their resume, cover letter and form answers stay consistent. Editing a profile invalidates only that profile's unsubmitted drafts. Existing single-profile data is migrated to **Default profile**. Duplicate job URLs are prevented across the workspace to avoid applying twice with different career profiles.

Save target roles (comma separated), search location, career facts, work rights and other constraints. In **Job search**, select sites and use **Search options** to set the match threshold and run limits. Searching prepares documents for review. Automatic submission is a separate action in Applications after document approval.

The agent opens a visible browser, reads up to 3 search pages per site and role, canonicalises links and skips existing jobs. It extracts job descriptions from JobPosting data or site-specific page elements. Local Qwen assesses role/location fit and mandatory requirements. Only jobs above the score threshold with no identified missing or unknown mandatory requirements are selected. An AI score is an estimate, not proof of eligibility; review assessments in each job.

After discovery finishes, selected jobs automatically enter document generation. Qwen writes each resume and cover letter without a separate Prepare selected click. Run activity shows queued and completed document pairs, with a View generated documents button. Qwen selects job-relevant skills, education and certifications and omits unrelated roles and duties from each job-specific draft. Selected facts remain verbatim; the original job headings, employers and dates remain attached to selected experience, in source order. The cover letter uses the same selected facts, and the master profile is unchanged. Related roles above the chosen score threshold can receive partial-match drafts when requirements remain missing or unknown; these stay marked Needs input for review. Both documents can be downloaded as DOCX. The browser uploads them to recognised resume/cover-letter fields (or fills a cover-letter text field). Some employers do not offer a cover-letter field. Unknown fields and consent still require user input.

The default search inspects at most 10 new jobs and can revisit unfinished saved jobs. The new-listing limit is configurable up to 30. Application batches are separately limited to 10 approved jobs. **Stop run** takes effect after the current browser or model operation; a submitted application cannot be undone. A failed/ambiguous application is not automatically retried. Run activity and per-job assessments are saved locally. This is a finite run, not a recurring background schedule.

SEEK may show a browser verification page; the visible browser waits up to five minutes for the user to complete it. LinkedIn may require sign-in. No challenge is bypassed. Extraction failures are logged instead of being treated as real job matches.

## Current boundaries

Resume downloads and browser uploads use the same ATS-friendly DOCX writer: one column, Arial 11 pt body text, standard section headings, one-inch margins, and contact information in ordinary body paragraphs. There are no tables, text boxes, images, headers or footers. The DOCX stores real selectable text and keeps selected employment and education facts in their original order. Enter roles most recent first, with complete job titles, employers and clear date ranges; the agent does not invent or guess those details. A plain-text resume download lets you inspect the linear reading order.

This format follows [Greenhouse's published parsing guidance](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse). It improves compatibility; no format guarantees successful parsing or ranking by every ATS. Match scores in the app are not ATS scores. Existing saved resumes receive the new Word styling when downloaded again; prepare them again to refresh the text structure and contact lines.

- **Local Qwen AI** uses your installed `qwen3:8b` through Ollama at `127.0.0.1:11434` to write a job-specific summary and order your existing skills. Work history, contact details and education remain unchanged. Review generated summaries for accuracy; prompts cannot guarantee factuality. Requests stay local, with no cloud fallback or API key. Failed drafts leave existing resumes unchanged and show the error inside the job.
- **Basic tailoring** remains available: matching skills move first and all other profile text stays verbatim. Select the engine beside **Prepare selected**. Local AI processes up to 10 selected jobs sequentially while the dashboard stays responsive. Editing is paused during generation to keep profile snapshots consistent.
- Browser discovery is available through **Job agent**. There is no recurring search scheduler or universal application connector.
- Login and CAPTCHA are handled by you. No stealth mechanisms or verification bypass.
- LinkedIn prohibits third-party site automation, and SEEK restricts automated access except through permitted interfaces. Using automated mode can risk account restrictions. Approve & apply queues automatic submission; Apply manually in Chrome remains available in the review dialog. See [LinkedIn guidance](https://www.linkedin.com/help/linkedin/answer/a1340567/automated-activity-on-linkedin?lang=en) and [SEEK terms](https://au.seek.com/terms/en).
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

Use **Posted within** to choose any time, the last 24 hours, or 3, 7, or 14 days, and **Sort jobs** to choose newest first or relevance. These filters are passed to both job sites. Runs with a posting-date filter search new listings without reprocessing older saved jobs. Job details show the posting date or relative posting label when available; exact posting times are not invented.

**Search options / Search browser** defaults to visible Chrome when SEEK is selected, using the same career profile's saved browser session as Login. Background mode remains available. Being signed in does not mean a site's verification check has cleared: visible runs pause for up to five minutes to let you complete it, then resume discovery.

In **Job search**, answer **What type of job do you want?** with a few keywords or job titles, for example `kitchen hand, cleaner, hospitality`. Local Qwen turns them into at most three focused search queries, shown in Run activity. These queries guide both discovery and matching for this run without changing your saved career profile. Leave the field blank to search your saved target roles. The saved location and career facts still apply. Suitable jobs receive individual resumes and cover letters for review and approval before submission. Planning uses one bounded local-model call per run; invalid plans stop with a message so you can adjust the keywords.

Use **Search jobs** on the dashboard or **Job search** in the sidebar. One **Search LinkedIn + SEEK** action searches both sites with the active profile, alternates their results within the overall limit, and saves jobs in one pipeline. Each site still needs its own sign-in. Suitable jobs receive documents for approval before submission.

## Google sign-in rejected

Google may reject sign-in from an automation-controlled browser, including Chrome. Signing into Chrome is not required to use Jobflow. In the agent window, return to LinkedIn or SEEK and use the site's own email sign-in option where offered. Enter the job-site password, not your Google password. For a Google-only account, use ordinary Chrome and the job site's account settings/help to establish an alternative sign-in method if supported. Signing into ordinary Chrome does not automatically sign in the separate agent session. Jobflow does not bypass this restriction. See https://support.google.com/accounts/answer/7675428 .

## Reliability update

Combined search now checks unfinished saved jobs first and searches public listings without account confirmation. If one site requires verification or has no readable listings, it reports the issue and continues with the other site. Use **My profile / Connect LinkedIn** or **Connect SEEK** to establish access separately. Document preparation errors and no-result runs are distinct from successful runs. Existing completed document pairs and uncertain submissions are preserved. Ollama availability is checked before starting. See [the automation brief](AUTOMATION_BRIEF.md) for the full workflow requirements.

Document tailoring first extracts verified quotations of the main job duties and requirements, excluding labelled employer-background and benefits sections. Both documents use the selected profile facts against those priorities. Conditional credentials such as "if applicable" and duplicated credentials are omitted. Cover letters connect specific evidence to the role without inventing commitments. The Review screen shows the priorities used. Older unapproved drafts refresh on the next search; approved and already-attempted applications are preserved. Use Refresh these documents to explicitly revise an older draft.

Uncertain application outcomes receive an automatic read-only check of the exact job page using the saved site session. Recognised applied status is recorded with the check time and evidence; no Submit button is clicked during verification. If the site does not provide evidence or requires sign-in, the status remains uncertain. Kitchen drafts exclude clinical care duties and care-placement blocks. Generated prose is checked against selected source facts, with extractive wording used when claims cannot be supported.

## Validation and release status

See [QA_REPORT.md](QA_REPORT.md) for the latest test results, fixes and live-site limits. This release is a local desktop workspace, not a public hosted service. The automated regression suite and local AI/export checks pass. Live job-site sign-in/verification is still required, and real application submission has not been certified. Older unsubmitted documents are marked for refresh; review regenerated documents before approving them.

## Resolving missing information

Before calling a requirement unknown, suitability checks now include saved application answers alongside profile facts and eligible certificate details. Preparing an existing job rechecks those facts. Requirement extraction retries an invalid AI quotation once, then uses the original advertisement wording instead of asking the applicant to repair AI output.

The review dialog distinguishes **Preparation failed**, **Review match**, and **Profile details needed**. When personal facts remain unresolved, enter accurate details in **Details still needed** and select **Save answers & retry**. Answers are saved in the active career profile and reused during assessment; changing them refreshes unsubmitted drafts. Negative answers are retained. Unresolved requirements stay visible, and preparing documents does not approve or submit the application.
