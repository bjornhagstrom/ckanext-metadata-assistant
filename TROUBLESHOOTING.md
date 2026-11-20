# Troubleshooting

Every message the assistant shows, what causes it and what to do. Start with the setup check: the top of the check
settings page (`/ckan-admin/metadata-assistant/check`), or `ckan -c $CKAN_INI metadata-assistant doctor`. The AI connection
(model, key, time limits) is set on the AI settings page of ckanext-ai-connector (`/ckan-admin/ai`). The setup check calls no
AI service and never shows a key.
`ckan -c $CKAN_INI metadata-assistant queue` shows the queues, workers, limits reached today and prepared reviews.

Messages appear in the portal's language; the English text is given here. The server log has the technical detail
(never a key, never the dataset's text).

## Setup check

| Message | Cause | What to do |
|---|---|---|
| The assistant's tables are missing or out of date. | The database was not upgraded after installing or updating the extension. | `ckan -c $CKAN_INI db upgrade -p metadata_assistant` |
| No AI model is set, so nothing that needs the AI works. | `ckanext.ai_connector.model` is empty (or still set under the old name `ckanext.metadata_assistant.ai_model`, which is no longer read). | Choose a model on the AI settings page, or rename the option (see the README, "Upgrading from the settings this extension had"). |
| The AI connection (the ai_connector plugin) is not switched on. Add ai_connector to ckan.plugins. | ckanext-ai-connector is installed but its plugin is not loaded. | Add `ai_connector` to `ckan.plugins` and restart. |
| The AI features need ckanext-ai-connector, which is not installed. | The extension was installed without its dependencies. | `pip install ckanext-ai-connector`, add `ai_connector` to `ckan.plugins`, restart. |
| Software that the AI connection needs is not installed: … | LiteLLM or cryptography is missing. | `pip install ckanext-ai-connector`, then restart. |
| No API key is found for the chosen key name. | Neither a key entered on the page nor the environment variable of that name exists. | Enter the key on the page, or set the variable on the server and restart. |
| A stored key cannot be read (the portal's secret has changed). | Keys entered on the page are encrypted with the portal's `SECRET_KEY` (else `beaker.session.secret`), which changed. | Enter the key again. |
| The schema has no multilingual fields, so translation suggestions are off. | No `*_translated` fields. | Add ckanext-fluent fields; see "Multilingual title, description and keywords" in the README. Not an error if you do not need translation. |
| The AI has no guidelines for any field, so it judges by its own taste. | Neither help texts in the schema nor the built-in baseline apply (`baseline_guidance: false`). | Add help texts, or remove that setting. |
| Unknown profile '…'. / Config option not set. / ckanext-scheming has no dataset schema loaded. | `ckanext.metadata_assistant.profile` or `schema_file` is wrong. | Use `auto`, or point `schema_file` at the schema YAML the portal uses. |
| Redis is not reachable, so AI requests run in the page. | CKAN's Redis is down or misconfigured. | Check `ckan.redis.url`. Reviews still work, without queue, limits or landing page cache. |
| Requests are queued but no worker is listening. | `jobs = on`, but no worker runs. | Start a worker, or set `jobs` to `auto`. |
| No worker: AI requests run in the page… | Normal without a worker. | Nothing, unless several editors work at once; then start a worker (README, "Many editors at once: background jobs"). |
| The AI service has failed repeatedly; requests wait N seconds. | The breaker is open after repeated failures. | Wait. Check the AI service's status and the key's quota. |
| Limits reached today (…) | See "Limits" below. | Use a stronger model or plan, or raise the limits. |

## While reviewing or translating

| Message | Cause | What to do |
|---|---|---|
| The AI review could not be completed. | A generic failure; the details are in the log. | Try again. If it repeats, press “Test the connection” on the AI settings page. |
| The AI provider could not complete the review. / could not translate the texts. | The AI service answered with an error or not at all (timeout, rate limit, overload). Tried twice, and a worker tries again after 5, 15 and 45 seconds. | The message says which: busy (wait and try again), too slow (a faster model, or raise the time limit on the AI settings page of ckanext-ai-connector), or out of quota (the service's own limit: see "Limits"). |
| The AI provider returned an invalid review response / translation / page summary. | The model's answer did not follow the required format. | Try again. If it repeats, choose a more capable model. |
| The environment variable '…' is missing or empty. / The name of the environment variable for the AI key is missing. | The key setting points at a variable that does not exist in the CKAN process. | Set the variable where CKAN runs (not only in your shell) and restart, or enter the key on the page. |
| The AI model is missing from the configuration. | No model set (`ckanext.ai_connector.model`). | Set it on the AI settings page. |
| LiteLLM is not installed. Install ckanext-ai-connector again with its dependencies. | As above. | `pip install ckanext-ai-connector` |
| AI settings from before: settings for the AI connection are still under this extension's old names (…) | An upgrade from before the move: values saved on the old page, keys entered there, or old option names on the server. | `ckan -c $CKAN_INI metadata-assistant migrate-ai-settings`, and rename the server's options (README). |
| The AI timeout must be a number of seconds. / greater than zero. | A bad value. | Enter a positive number. |
| The chosen AI provider cannot read landing pages / cannot translate. | The provider lacks the capability (reading pages with the service's own fetch needs a Gemini or Claude model; with `landing_page_fetch` = `auto` or `own` the portal fetches the page itself and any model can read the text). | Choose another model, or work without that feature. |
| The landing page must be a public https address. | The address is http, local, private or has credentials in it. The page is read by the AI service or fetched by the portal, and must be public. | Use the public https address. |
| The landing page could not be read. | The page is slow, down, or forbids robots. The review then runs without the page. | Try again later, or describe the page's content in the description yourself. |
| The landing page took too long to answer. / could not be reached. / answered with an error (code). / is not a web page or a text. / forwards too many times. / has no text to read. | The portal's own fetch (`landing_page_fetch` = `auto` after the service's fetch failed, or `own`) could not read the page: slow, down, an error, a PDF or image, a redirect loop, or a page built in the browser with JavaScript (no text in the HTML). | Try again later, or describe the page's content in the description yourself. |
| The landing page is not on a public address (an internal or private network, or a name that does not exist). Such pages are not read. | The address resolves to a private or internal address, or to nothing. Internal pages are not read, on purpose (see "Known limitations" in the README). | Use a public address, or describe the page's content in the description yourself. |
| Invalid page summary. | A page summary sent by the browser is malformed. | Reload the page. |
| This does not look like an API key. / Choose one of the allowed keys. / Keys cannot be stored on this portal. | A key was entered wrongly, or the key name is not in `api_key_envs`, or storing keys is disallowed. | Check the key; ask the server administrator to add the variable name to the allowed list. |
| There is no text in … to translate yet. / The profile has no fields for translation. / None of the requested languages is a target language. | Nothing to translate, or the schema defines no such target. | Write the text first; check the languages in the schema. |
| Dataset not found. / Not authorized. / You may not edit this dataset. | The dataset is gone, or the user may not edit it. AI suggestions need edit rights. | Sign in as an editor of the dataset's organization. |
| This proposal is no longer open. / The dataset could not be saved: … | Someone else decided it already, or the dataset's own validation failed. | Reload the list; fix the field named in the message. |

## Limits and queue

| Message | Cause | What to do |
|---|---|---|
| The AI service is busy. Try again in a minute. | All `ai_max_concurrent` places were taken for longer than `ai_slot_wait_seconds`, or `ai_max_per_minute` is reached. | Try again. If common, raise the limits or use a stronger plan. |
| The AI service is not answering right now. Try again in N seconds. | The breaker is open: 5 failures within a minute. | Wait N seconds. Check the service and the key's quota. |
| You already have N AI requests waiting or running. | The per-user limit (`ai_max_jobs_per_user`). Applies when a worker is running. | Wait for one to finish. |
| The daily limit of AI requests is reached. | `ai_max_per_user_per_day`. | Try tomorrow, or raise the limit. |
| Waiting in line: N before you… | Normal with a worker: the queue is longer than the free places. | Wait, or start more workers (they never exceed `ai_max_concurrent`). |
| The AI request is no longer there. Start it again. | The answer waited more than 15 minutes, or Redis was emptied. | Press the button again. |
| The AI request did not finish. Try again. | The worker process was stopped or killed while it had the job. | Try again. Check that a worker is running (`queue`). |
| The AI did not answer in time. / The connection was lost. | The browser waited 6 minutes, or the network dropped. | Try again. |
| Unknown kind of AI request. | A call to the API with a wrong `kind`. | Use `landing`, `review` or `translate`. |
| The AI request failed. | Anything else, including a job that ran over its 5 minutes; see the log (`Metadata assistant job failed`). | Try again, and report with the log line if it repeats. |

## Common situations

- **The AI used an old version of the landing page.** Pages are kept for up to 6 hours (`landing_page_cache_hours`). Press
  “Download the landing page again” to read it anew and get new suggestions.

- **Nothing is suggested.** The AI found nothing to change (the panel says so), or a keyword it suggested was already
  there or was a place name. This is not a fault.
- **"Suggestions prepared 10:45" shows old suggestions.** They come from `review-all` and are valid until any text of
  the dataset, the guidelines, the instruction or the model changes. "Get new suggestions" always asks again.
- **The first page load after a restart is slow.** CKAN warms up on the first request; it is not the assistant.
- **Several editors, and the site stalls.** Start a worker (README, "Many editors at once: background jobs"). Without one every request holds a web
  worker for the length of the AI call.
- **The worker does nothing.** It must be started with `ckan … metadata-assistant worker` (not `ckan jobs worker`),
  in the same environment as CKAN, and restarted after an upgrade. `queue` shows whether it is seen.
- **Everything runs in the page though a worker exists.** The worker is not seen: it has not beaten for 90 seconds
  (stopped, or no Redis connection), or it was started the other way.
