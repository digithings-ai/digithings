# Getting help

## Read first

- [README.md](README.md#quick-start): install and first request.
- [docs/SELF_HOST.md](docs/SELF_HOST.md): running the stack on your own machine.
- [ARCHITECTURE.md](ARCHITECTURE.md): how the services fit together.
- Each module's own `README.md` or `ARCHITECTURE.md`, linked from the [module table](README.md#modules).

## Ask a question

Search [existing issues](https://github.com/digithings-ai/digithings/issues?q=is%3Aissue) first. If nothing matches, open an issue with the **Feature request** form for an idea, or the **Bug report** form for a defect. A question about usage is fine as a blank issue; say which module, which version or commit, and what you tried.

## Report a bug

Use the [Bug report form](https://github.com/digithings-ai/digithings/issues/new?template=bug_report.yml). A good report has:

- the module and the version or commit SHA;
- how you run it (`make up`, `make up-ghcr`, `make stack-local`, or your own setup);
- the smallest steps that reproduce it, and what you expected instead;
- logs with secrets removed.

## Report a security issue

Do not open a public issue. Follow [SECURITY.md](SECURITY.md#reporting-vulnerabilities).

## Contribute a fix

See [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused PRs with a test are the fastest to land.

## What to expect

This project is maintained by a small team. Issues are triaged as time allows, and there is no guaranteed response time outside security reports. Commercial support and hosted deployments are not offered through this repository; for those, email **contact@digithings.ai**.
