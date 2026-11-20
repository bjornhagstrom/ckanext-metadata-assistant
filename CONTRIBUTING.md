# Contributing

Thank you for helping improve ckanext-metadata-assistant. The extension is in development (0.x), so bug reports,
compatibility results (CKAN version, dataset schema, AI service and model) and feedback on the rule check and the
suggestions are especially useful.

## Before opening an issue

- search existing issues;
- include the CKAN, Python and ckanext-ai-connector versions, the dataset schema (ckanext-scheming, ckanext-fluent or none)
  and the model (`service/name`) used;
- describe the expected and actual result;
- include reproducible steps and relevant logs with keys, credentials and personal data removed.

Use a private security report instead of a public issue for vulnerabilities; see [SECURITY.md](SECURITY.md).

## Pull requests

1. Keep each pull request focused.
2. Add or update tests when changing behavior. Run the suite as the README's "Testing" section shows; continuous
   integration runs it on CKAN 2.11.1, the newest 2.11 patch and 2.12, and runs the JavaScript tests.
3. Update the README, TROUBLESHOOTING and changelog when user-visible behavior changes.
4. Internationalize all new user-visible strings: wrap them in `_(...)` with English source text (in JavaScript, through
   the panel's `data-i18n` strings), then add the Swedish `msgstr` to
   `ckanext/metadata_assistant/i18n/sv/LC_MESSAGES/ckanext-metadata-assistant.po` and `sv_SE`, and compile the `.mo`
   files. The tests fail when an extracted string has no translation or a `.mo` does not match its `.po`.
5. Never let the AI save or publish anything: suggestions are applied by an editor. Never log a key, a prompt or an
   answer from the AI service; log failures by type and status code.
6. Disclose material generative-AI assistance in the pull request description (see [AI_ASSISTANCE.md](AI_ASSISTANCE.md)).

## Translations

A new language is welcome as a pull request: add
`ckanext/metadata_assistant/i18n/<locale>/LC_MESSAGES/ckanext-metadata-assistant.po` and its compiled `.mo`. No code
change is needed; the plugin offers every compiled catalogue.
