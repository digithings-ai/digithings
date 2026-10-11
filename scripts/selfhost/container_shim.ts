/**
 * Self-host container shim (DIG-2771, plan slice S3).
 *
 * `wrangler dev` cannot run Cloudflare Containers reliably, so a local
 * `wrangler dev` session must map each container class to a service published
 * by `docker-compose.yml` on the host.
 *
 * This module is the ONLY new runtime code in the slice. It is a Durable
 * Object base class: the worker calls
 * `getContainer(env.STACK, id).fetch(switchPort(request, PORT))`, so the target
 * port arrives in the `cf-container-target-port` request header (see
 * `apps/digithings-stack-cloudflare/src/index.ts:153` and `:308`). The shim
 * reads that header and forwards to the compose service.
 *
 * Contract:
 * - Resolution is keyed on (className, containerPort), never on port alone.
 *   `DigiChatContainer` and `LangfuseWebContainer` both default to 3000, so a
 *   port-only table would be ambiguous.
 * - An unmapped (class, port) returns HTTP 503 naming the class, the port and
 *   the compose service that must be added. It never hangs and never throws an
 *   opaque 500.
 * - The host port is NOT the container port. Compose publishes `digichat` as
 *   `${DIGICHAT_PUBLISH_PORT:-3005}:3000`, so container port 3000 maps to host
 *   port 3005.
 */

/** The compose service that answers a container port on the host. */
export interface SelfHostUpstream {
	/** docker-compose service name. */
	readonly service: string;
	/** Port the compose file publishes on the host. */
	readonly hostPort: number;
	/** Compose profile that starts the service, or "" when it is unprofiled. */
	readonly profile: string;
}

/** Outcome of a routing decision. */
export type SelfHostResolution =
	| {
			readonly ok: true;
			readonly className: string;
			readonly containerPort: number;
			readonly upstream: SelfHostUpstream;
			readonly url: string;
	  }
	| {
			readonly ok: false;
			readonly className: string;
			readonly containerPort: number;
			/** Human-readable reason, safe to return in a response body. */
			readonly reason: string;
			/** The compose service that has to be added, when known. */
			readonly neededService: string;
			readonly knownPorts: readonly number[];
	  };

/**
 * Container class -> (container port -> compose upstream).
 *
 * Only pairs that are exactly determined by the compose file are listed. A
 * class that has no compose service yet carries an empty `ports` map and a
 * `neededService`, which the shim reports as an explicit gap.
 */
export const SELF_HOST_CLASSES: Readonly<
	Record<string, { ports: Readonly<Record<number, SelfHostUpstream>>; neededService: string; note: string }>
> = {
	DigiStackContainer: {
		// One container fronts five services, selected by the target port.
		ports: {
			8000: { service: "digigraph", hostPort: 8000, profile: "" },
			8001: { service: "digiquant", hostPort: 8001, profile: "" },
			8002: { service: "digisearch", hostPort: 8002, profile: "" },
			8003: { service: "digitrace", hostPort: 8003, profile: "" },
			8004: { service: "digivault", hostPort: 8004, profile: "digivault" },
			8005: { service: "digikey", hostPort: 8005, profile: "" },
			4000: { service: "litellm", hostPort: 4000, profile: "" },
		},
		neededService: "",
		note: "graph./key./search. routing in ports.ts selects the target port.",
	},
	DigiChatContainer: {
		ports: {
			3000: { service: "digichat", hostPort: 3005, profile: "digichat" },
		},
		neededService: "",
		note: "compose publishes digichat as ${DIGICHAT_PUBLISH_PORT:-3005}:3000.",
	},
	DigiQuantMcpContainer: {
		ports: {},
		neededService: "digiquant-mcp",
		note: "docker-compose.yml publishes no service on 8767.",
	},
	DigiQuantRunnerContainer: {
		ports: {},
		neededService: "digiquant-runner",
		note: "Dockerfile.digiquant-runner exposes 8080 in-container; compose publishes no 8080.",
	},
	LangfuseWebContainer: {
		ports: {},
		neededService: "digitrace-langfuse-web",
		note: "apps/digitrace-langfuse/docker-compose.local.yml has only clickhouse and redis.",
	},
	LangfuseWorkerContainer: {
		ports: {},
		neededService: "digitrace-langfuse-worker",
		note: "No compose service; the worker has no public HTTP surface in prod either.",
	},
};

/** Header `switchPort()` writes. Verified in apps/digithings-stack-cloudflare/src/index.ts. */
export const SELF_HOST_TARGET_PORT_HEADER = "cf-container-target-port";

/** Resolve a container class and target port to a compose upstream. */
export function resolveSelfHostUpstream(className: string, containerPort: number): SelfHostResolution {
	const entry = SELF_HOST_CLASSES[className];
	if (entry === undefined) {
		return {
			ok: false,
			className,
			containerPort,
			reason: `class ${className} is not in the self-host shim table`,
			neededService: "",
			knownPorts: [],
		};
	}
	const upstream = entry.ports[String(containerPort)];
	if (upstream === undefined) {
		const knownPorts = Object.keys(entry.ports).map((p) => Number.parseInt(p, 10));
		const reason =
			knownPorts.length === 0
				? `${className} has no docker-compose service yet (${entry.note})`
				: `${className} has no route for container port ${containerPort}; known ports: ${knownPorts.join(", ")}`;
		return {
			ok: false,
			className,
			containerPort,
			reason,
			neededService: entry.neededService,
			knownPorts,
		};
	}
	return {
		ok: true,
		className,
		containerPort,
		upstream,
		url: `http://127.0.0.1:${upstream.hostPort}`,
	};
}

/**
 * Base class for a generated `SelfHost<Class>` Durable Object.
 *
 * Generated entries under `apps/<worker>/.selfhost-dev/entry.ts` subclass this
 * and set `selfHostClass`. The subclassed name is distinct from the real
 * container class name on purpose: a Durable Object binding can then point at
 * the shim without any reliance on ESM star-export precedence.
 */
export class SelfHostContainer {
	/** Set by the generated subclass. */
	readonly selfHostClass = "";
	/** Used when the request carries no target-port header. */
	readonly selfHostDefaultPort = 0;

	/** Read the target port the worker asked for. */
	protected targetPort(request: Request): number | null {
		const raw = request.headers.get(SELF_HOST_TARGET_PORT_HEADER);
		if (raw === null || raw === "") return this.selfHostDefaultPort || null;
		const parsed = Number.parseInt(raw, 10);
		return Number.isNaN(parsed) ? this.selfHostDefaultPort || null : parsed;
	}

	async fetch(request: Request): Promise<Response> {
		const containerPort = this.targetPort(request);
		if (containerPort === null) {
			return new Response(
				JSON.stringify(
					{
						error: "selfhost_container_port_missing",
						className: this.selfHostClass,
						hint: `send the ${SELF_HOST_TARGET_PORT_HEADER} header, or set selfHostDefaultPort`,
					},
					null,
					2,
				),
				{ status: 400, headers: { "content-type": "application/json" } },
			);
		}

		const resolution = resolveSelfHostUpstream(this.selfHostClass, containerPort);
		if (!resolution.ok) {
			// An explicit 503 naming what is missing beats a hang.
			return new Response(
				JSON.stringify(
					{
						error: "selfhost_upstream_unmapped",
						className: resolution.className,
						containerPort: resolution.containerPort,
						reason: resolution.reason,
						neededComposeService: resolution.neededService,
						knownPorts: resolution.knownPorts,
					},
					null,
					2,
				),
				{ status: 503, headers: { "content-type": "application/json" } },
			);
		}

		const { url, upstream } = resolution;
		const target = new URL(request.url);
		const headers = new Headers(request.headers);
		// Do not leak the container-routing header to the compose service.
		headers.delete(SELF_HOST_TARGET_PORT_HEADER);
		try {
			return await fetch(new Request(`${url}${target.pathname}${target.search}`, {
				method: request.method,
				headers,
				body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
				redirect: request.redirect,
				// @ts-expect-error duplex is required by undici for a streamed body.
				duplex: "half",
			}));
		} catch (cause) {
			return new Response(
				JSON.stringify(
					{
						error: "selfhost_upstream_unreachable",
						className: resolution.className,
						containerPort: resolution.containerPort,
						composeService: upstream.service,
						hostPort: upstream.hostPort,
						hint: upstream.profile ? `docker compose --profile ${upstream.profile} up -d ${upstream.service}` : `docker compose up -d ${upstream.service}`,
						cause: String(cause),
					},
					null,
					2,
				),
				{ status: 502, headers: { "content-type": "application/json" } },
			);
		}
	}
}
