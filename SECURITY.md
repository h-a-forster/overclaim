# Security policy

Security fixes are made for the latest release.

## Reporting

Report vulnerabilities privately through the repository's **Security** tab ("Report a
vulnerability"). Do not open a public issue. Include the overclaim version, the operating
system, the impact, and the smallest input that reproduces it.

## Scope

overclaim reads transcripts and run directories, and its Stop hook runs inside Claude Code on
every stop.

In scope:

- a transcript, run directory or manifest that makes overclaim read or write files outside the
  paths you gave it, or run commands;
- the Stop hook doing anything other than reading its input and the transcript and printing a
  decision;
- Markdown or HTML output that executes script from transcript contents;
- secrets from transcripts written to reports or caches beyond what you asked to export.

Out of scope:

- what an agent does during an experiment (the experiments run agents with full permissions;
  see [experiments/README.md](experiments/README.md));
- the task suites, which contain deliberately wrong code;
- vulnerabilities in the agents themselves (report those to their maintainers).
