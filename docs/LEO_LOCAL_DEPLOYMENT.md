# Running LEO on a machine you control

For one site's research use: the app runs on a computer or GPU node the institution controls, and notes never leave it. This is **not** a clinical or hospital-wide production system (see the end of this page).

## 1. Start it

```bash
bin/leo user add yourname            # asks for a password (10+ characters); turns login on
bin/leo start --local --port 8085    # this machine only: http://127.0.0.1:8085/leo/ui
```

- **Server.** `bin/leo start --local` runs gunicorn with one worker and four threads (`gunicorn_config.py`). One worker means one copy of the model in memory. `--dev` uses Flask's development server instead. If gunicorn is not installed it falls back to the development server and says so.
- **Model.** On a GPU node the model is loaded when the server starts (`MEDAI_EAGER_LOAD=1`, set by `bin/leo start`). With `--cpu` only the rules run and every value is marked "needs review".
- **Where it listens.** This machine only (127.0.0.1) unless `--host` says otherwise. On a Slurm node it listens on the node's address so an SSH tunnel can reach it, and it prints a warning if no login is set up. On a shared cluster, other users can reach that port: add a user first.
- **Reaching it from your laptop.** Use an SSH tunnel (`bin/leo status` prints the command). Login passwords are not encrypted on the wire; do not expose the port on a network without HTTPS (put a TLS proxy in front and set `MEDAI_LEO_COOKIE_SECURE=1`).
- **Set `SECRET_KEY`** in the environment (any long random string). Without it, sign-ins end every time the server restarts.

## 2. Login

| What | How |
|---|---|
| Add, change or remove a user | `bin/leo user add NAME` (again to change the password), `bin/leo user remove NAME`, `bin/leo user list` |
| Login turns on | when the first user exists, or with `MEDAI_LEO_REQUIRE_LOGIN=1` (with no users, nobody can sign in) |
| Covered | every page and API route except `/health` and the sign-in page |
| Browser | sign-in page, session of 8 hours (`MEDAI_LEO_SESSION_HOURS`), "Sign out" button |
| Scripts | HTTP Basic: `curl -u name:password http://127.0.0.1:8085/leo/phenotypes` |
| Passwords | stored as salted hashes in `data/leo_users.json` (owner-only; `MEDAI_LEO_USERS` moves it) |
| Guessing | five wrong tries lock that user from that address for ten minutes |
| Other sites | a page on another site cannot act with your session (cookie is SameSite=Lax and the request origin is checked) |

Restart a running server after adding the first user.

## 3. Who sees what

- Each job belongs to the user who started it. Other users get "unknown job" for its status, download, review and delete. (Anyone with login to the machine itself, or the account that runs the app, can still read the files in `data/leo_jobs/`.)
- With login on, the reviewer recorded on every review decision is the signed-in user, not a typed name.
- Job files are deleted after 24 hours (`MEDAI_LEO_JOB_TTL_H`) and can be deleted at once from the result page.

## 4. Audit log

`data/leo_audit.jsonl` (owner-only, append only; `MEDAI_LEO_AUDIT` moves it). One line per event: time (UTC), user, address, event, job id. Events: `login`, `login_failed`, `login_blocked`, `logout`, `job_plan`, `job_start` (file name, phenotypes, counts), `job_cancel`, `job_delete`, `download`, `review_save`, `review_export`, `extract_note` (length only). It never holds note text, file contents or passwords. Read it with `bin/leo user audit -n 100`.

The log is a plain file the app's account can edit; it records activity, it is not tamper-proof. Back it up if it matters.

## 5. Restarts

Each job writes a small record (`job.json`) in its folder. After a restart:

- finished jobs can still be viewed, downloaded and reviewed (review decisions were already saved on disk);
- a job that was **running** when the app stopped is shown as failed, with the message "The app restarted while this job was running. Start it again." It is not resumed;
- waiting-to-confirm jobs ("Describe a job") stay confirmable.

## 6. Install

Packages are listed in `requirements-leo.txt` (versions the tests ran with) and, for the exact set in `venv-medcat`, `requirements-leo.lock.txt`. `bin/leo install --check-only` lists what is missing. The model (Med42-8B, about 16 GB in half precision) must be downloaded first, and a GPU with roughly 20 GB or more of memory is expected for the language model. The development cluster uses an L40S 24 GB. Docker files exist (`Dockerfile`, `Dockerfile.gpu`) and use the same gunicorn settings; they were not tested for LEO.

## 7. What was tested, and what was not

Tested (automated, `tests/test_leo_app.py`): login required everywhere, wrong passwords, redirects that cannot leave the site, Basic auth, cross-site refusal, lockout after five failures, users' jobs hidden from each other, jobs restored after a restart, a job that was running at restart marked failed, audit log without note text, file permissions of the users file and log. Also by hand: `bin/leo start --local --cpu` under gunicorn with login on (sign-in, API call, audit lines).

**Not tested:** a clean-machine install; the GPU model loading under gunicorn (the smoke test was rules-only); load from several users at once; HTTPS; recovery after a full disk or a killed GPU job.

## 8. What this is not

- Not single sign-on, not roles or an administrator tier, no password reset by e-mail (use `bin/leo user add`).
- Not monitored: there is no alerting. `/health` and the logs (`logs/`, rotated) are what exist.
- No accuracy figure applies to real notes. Every value stays a draft to be checked against its quote.
- Not approved for patient data by anyone. Approvals, de-identification decisions and any clinical use are separate (see `LEO_EPIC_INTEGRATION.md`, sections 5 and 8).
