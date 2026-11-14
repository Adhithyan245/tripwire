# Chat deployment handoff

The experimental chat runs in Python with Streamlit and the existing Driftwire engine. The current Vercel site is a static practice replay; copying these Python files to that site alone will not run the chat, AI agents or firewall. A teammate with access to a suitable Python/Streamlit hosting service needs to deploy this branch. The repository's plan-change and feature-freeze rules still apply before merging it into `dev`.

## Security and scope before deployment

This is a research prototype, not a production service. The local workflow stores session files and accepts paths to release folders on its host. **Do not expose the full dashboard to untrusted internet visitors as-is:** visitors could supply paths available to the server, and session storage is not a production data-isolation design. Use an access-controlled environment for the team/judges, restrict filesystem access, and use synthetic demo data until a reviewed upload and isolation design exists. Do not accept real patient records, PHI, or other confidential data.

The chat can use `OPENAI_API_KEY` as a server environment variable, or a user can enter a key into the masked optional field. Session-entered keys are held in the app server's session memory, not committed; on a remote deployment they transit to that server and then to OpenAI, so only use an HTTPS host you trust. Agents send the separately consented metadata and question to OpenAI, not table rows. No key should be committed or placed in logs, URLs, screenshots, video, or PR descriptions.

## Deployment prerequisites

1. Confirm with the team the exact approved commit and deployment owner; this work begins on `role3/ai-intake-prototype`.
2. Provision an access-controlled Python host supporting a long-running Streamlit process. A minimal command is `streamlit run app/dashboard.py --server.address 0.0.0.0 --server.port "$PORT"`; the hosting provider must inject `$PORT` or you must set a suitable port. Install `requirements.txt` and use a supported Python version.
3. Provision only the non-sensitive synthetic demo files and record their host paths. The path values from Hemnaath's Mac will not work on the hosted machine. The local recording runbook describes how to generate synthetic data; never copy raw TCGA files into the repository.
4. Set any server-side OpenAI key as a secret using the provider's secret manager, not as a source file. Use separate per-agent consent. Confirm provider data handling and access controls before using any real research data.
5. On the hosted version, run through upload, consent, both agent calls, a question, the firewall result, evidence, and human review. Confirm the result uses the intended supported files and that the deployed commit is the one being presented. If AI calls fail, use and label the manual fallback.

Do not advertise the static Vercel site as a live chat or claim arbitrary formats or clinical use. The challenge demo should still use the organizers' approved data and sealed input under their rules.
