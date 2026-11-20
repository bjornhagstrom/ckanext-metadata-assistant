# Security policy

## Supported versions

Security fixes are made only on the latest release. The extension is in development (0.x) and has not received a formal
security audit.

## What the extension protects

- **Nothing is saved or published by the AI.** Suggestions and translations are only returned to the edit form; a dataset
  changes only when an editor applies a suggestion and saves, or applies a stored translation proposal, as that editor.
- **Who may start AI calls.** Only users who may edit the dataset (or create one, for a new draft); sysadmins for the
  administration pages. Requests made through the queue (the form's panel) can be limited per user and site and have a
  circuit breaker; the limits are off by default (0), and the direct API actions are not limited (see "Background jobs and
  limits" in the README).
- **Landing pages.** The portal fetches a dataset's landing page itself only over https, refuses addresses that are not
  public (checked for every redirect), and limits size and time. The page's text is passed to the AI as fenced, untrusted
  data, never as instructions.
- **The AI connection and its keys** belong to [ckanext-ai-connector](https://github.com/bjornhagstrom/ckanext-ai-connector),
  which has its own security policy.

Reports about any way around these are especially welcome.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's **Report a vulnerability** function in the
repository's Security tab. The maintainer will acknowledge the report, assess impact and coordinate a fix and disclosure.
If private vulnerability reporting is temporarily unavailable, open a public issue containing no sensitive detail and ask
the maintainer for a private contact channel.

Do not include live credentials, API keys, personal data or data copied from a production CKAN installation in a report.
