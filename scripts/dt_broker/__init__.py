"""dt-broker -- the host-resident broker for per-run GitHub App tokens.

The broker is the only thing on the machine that holds a GitHub App private
key. A seat never sees one. A seat asks the broker, over a unix socket, for a
token scoped to the repository its own ticket names, and the broker decides
whether that seat may have one.

Three rules shape every decision in here:

* A token is scoped to **one** repository -- the repository the run's ticket is
  bound to. Not the organization, not the installation: one repository.
* A token is only minted while the run that asked for it is still `running`.
  A token outlives the run that wanted it by exactly as long as GitHub says
  installation tokens live, and no longer.
* Nothing that can read a credential is ever written down. The audit log
  records the last four characters of a token, never the token.

The modules:

* `core` -- policy, identity, JWT signing, the audit log.
* `github` -- the GitHub REST calls (mint, revoke, bot id, commit trailers).
* `paperclip` -- the Paperclip calls that turn a run JWT into a run context.
* `server` -- the unix-socket daemon.
* `client` -- the socket client.
* `ghshim` -- the `gh` wrapper that sits in front of the host gh guard.
* `cli` -- the `dt-broker` command line.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
