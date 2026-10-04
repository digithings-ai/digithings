var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// ../../node_modules/@cloudflare/containers/dist/lib/helpers.js
function generateId(length = 9) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let result = "";
  for (let i = 0; i < length; i++) {
    result += alphabet[bytes[i] % alphabet.length];
  }
  return result;
}
__name(generateId, "generateId");
function parseTimeExpression(timeExpression) {
  if (typeof timeExpression === "number") {
    return timeExpression;
  }
  if (typeof timeExpression === "string") {
    const match = timeExpression.match(/^(\d+)([smh])$/);
    if (!match) {
      throw new Error(`invalid time expression ${timeExpression}`);
    }
    const value = parseInt(match[1]);
    const unit = match[2];
    switch (unit) {
      case "s":
        return value;
      case "m":
        return value * 60;
      case "h":
        return value * 60 * 60;
      default:
        throw new Error(`unknown time unit ${unit}`);
    }
  }
  throw new Error(`invalid type for a time expression: ${typeof timeExpression}`);
}
__name(parseTimeExpression, "parseTimeExpression");

// ../../node_modules/@cloudflare/containers/dist/lib/container.js
import { DurableObject, WorkerEntrypoint } from "cloudflare:workers";
var NO_CONTAINER_INSTANCE_ERROR = "there is no container instance that can be provided to this durable object";
var RATE_LIMITED_ERROR = "you are requesting too many containers per second";
var RUNTIME_SIGNALLED_ERROR = "runtime signalled the container to exit:";
var UNEXPECTED_EXIT_ERROR = "container exited with unexpected exit code:";
var NOT_LISTENING_ERROR = "the container is not listening";
var CONTAINER_STATE_KEY = "__CF_CONTAINER_STATE";
var OUTBOUND_CONFIGURATION_KEY = "OUTBOUND_CONFIGURATION";
var MAX_ALARM_RETRIES = 3;
var PING_TIMEOUT_MS = 5e3;
var DEFAULT_SLEEP_AFTER = "10m";
var INSTANCE_POLL_INTERVAL_MS = 300;
var TIMEOUT_TO_GET_CONTAINER_MS = 8e3;
var TIMEOUT_TO_GET_PORTS_MS = 2e4;
var FALLBACK_PORT_TO_CHECK = 33;
var outboundHandlersRegistry = /* @__PURE__ */ new Map();
var defaultOutboundHandlerNameRegistry = /* @__PURE__ */ new Map();
var outboundByHostRegistry = /* @__PURE__ */ new Map();
var signalToNumbers = {
  SIGINT: 2,
  SIGTERM: 15,
  SIGKILL: 9
};
function isErrorOfType(e, matchingString) {
  const errorString = e instanceof Error ? e.message : String(e);
  return errorString.toLowerCase().includes(matchingString);
}
__name(isErrorOfType, "isErrorOfType");
var isNoInstanceError = /* @__PURE__ */ __name((error) => isErrorOfType(error, NO_CONTAINER_INSTANCE_ERROR), "isNoInstanceError");
var isRateLimitedError = /* @__PURE__ */ __name((error) => isErrorOfType(error, RATE_LIMITED_ERROR), "isRateLimitedError");
var isRuntimeSignalledError = /* @__PURE__ */ __name((error) => isErrorOfType(error, RUNTIME_SIGNALLED_ERROR), "isRuntimeSignalledError");
var isNotListeningError = /* @__PURE__ */ __name((error) => isErrorOfType(error, NOT_LISTENING_ERROR), "isNotListeningError");
var isContainerExitNonZeroError = /* @__PURE__ */ __name((error) => isErrorOfType(error, UNEXPECTED_EXIT_ERROR), "isContainerExitNonZeroError");
function getExitCodeFromError(error) {
  if (!(error instanceof Error)) {
    return null;
  }
  if (isRuntimeSignalledError(error)) {
    return +error.message.toLowerCase().slice(error.message.toLowerCase().indexOf(RUNTIME_SIGNALLED_ERROR) + RUNTIME_SIGNALLED_ERROR.length + 1);
  }
  if (isContainerExitNonZeroError(error)) {
    return +error.message.toLowerCase().slice(error.message.toLowerCase().indexOf(UNEXPECTED_EXIT_ERROR) + UNEXPECTED_EXIT_ERROR.length + 1);
  }
  return null;
}
__name(getExitCodeFromError, "getExitCodeFromError");
function addTimeoutSignal(existingSignal, timeoutMs) {
  const controller = new AbortController();
  if (existingSignal?.aborted) {
    controller.abort();
    return controller.signal;
  }
  existingSignal?.addEventListener("abort", () => controller.abort());
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  controller.signal.addEventListener("abort", () => clearTimeout(timeoutId));
  return controller.signal;
}
__name(addTimeoutSignal, "addTimeoutSignal");
var ContainerState = class {
  static {
    __name(this, "ContainerState");
  }
  storage;
  status;
  constructor(storage) {
    this.storage = storage;
  }
  async setRunning() {
    await this.setStatusAndupdate("running");
  }
  async setHealthy() {
    await this.setStatusAndupdate("healthy");
  }
  async setStopping() {
    await this.setStatusAndupdate("stopping");
  }
  async setStopped() {
    await this.setStatusAndupdate("stopped");
  }
  async setStoppedIfUnchanged(previousState) {
    if (this.status !== previousState) {
      return;
    }
    await this.setStopped();
  }
  async setStoppedWithCode(exitCode) {
    this.status = { status: "stopped_with_code", lastChange: Date.now(), exitCode };
    await this.update();
  }
  async getState() {
    if (!this.status) {
      const state = await this.storage.get(CONTAINER_STATE_KEY);
      if (!state) {
        this.status = {
          status: "stopped",
          lastChange: Date.now()
        };
        await this.update();
      } else {
        this.status = state;
      }
    }
    return this.status;
  }
  async setStatusAndupdate(status) {
    this.status = { status, lastChange: Date.now() };
    await this.update();
  }
  async update() {
    if (!this.status)
      throw new Error("status should be init");
    await this.storage.put(CONTAINER_STATE_KEY, this.status);
  }
};
var Container = class extends DurableObject {
  static {
    __name(this, "Container");
  }
  static get outboundByHost() {
    return outboundByHostRegistry.get(this.name);
  }
  static set outboundByHost(handlers) {
    outboundByHostRegistry.set(this.name, handlers);
  }
  static get outboundHandlers() {
    return outboundHandlersRegistry.get(this.name);
  }
  static set outboundHandlers(handlers) {
    const existing = outboundHandlersRegistry.get(this.name) ?? {};
    outboundHandlersRegistry.set(this.name, { ...existing, ...handlers });
  }
  static get outbound() {
    const handlerName = defaultOutboundHandlerNameRegistry.get(this.name);
    if (!handlerName)
      return void 0;
    return outboundHandlersRegistry.get(this.name)?.[handlerName];
  }
  static set outbound(handler) {
    const key = "__outbound__";
    const existing = outboundHandlersRegistry.get(this.name) ?? {};
    outboundHandlersRegistry.set(this.name, { ...existing, [key]: handler });
    defaultOutboundHandlerNameRegistry.set(this.name, key);
  }
  static get outboundProxies() {
    return this.outboundHandlers;
  }
  static set outboundProxies(handlers) {
    this.outboundHandlers = handlers;
  }
  static get outboundProxy() {
    return this.outbound;
  }
  static set outboundProxy(handler) {
    this.outbound = handler;
  }
  // =========================
  //     Public Attributes
  // =========================
  // Default port for the container (undefined means no default port)
  defaultPort;
  // Required ports that should be checked for availability during container startup
  // Override this in your subclass to specify ports that must be ready
  requiredPorts;
  // Timeout after which the container will sleep if no activity
  // The signal sent to the container by default is a SIGTERM.
  // The container won't get a SIGKILL if this threshold is triggered.
  sleepAfter = DEFAULT_SLEEP_AFTER;
  // Container configuration properties
  // Set these properties directly in your container instance
  envVars = {};
  entrypoint;
  enableInternet = true;
  labels = {};
  // When true, outbound HTTPS traffic from the container will be intercepted.
  // The container must trust /etc/cloudflare/certs/cloudflare-containers-ca.crt
  interceptHttps = false;
  // Hosts that are allowed to access the internet, even when enableInternet is false.
  // Useful for allowing specific domains on a per-host basis.
  allowedHosts;
  // Hosts that are denied internet access, even when enableInternet is true.
  // Also blocks hosts from being handled by the catch-all outbound handler.
  deniedHosts;
  // pingEndpoint is the host and path value that the class will use to send a request to the container and check if the
  // instance is ready.
  //
  // The user does not have to implement this route by any means,
  // but it's still useful if you want to control the path that
  // the Container class uses to send HTTP requests to.
  pingEndpoint = "ping";
  applyOutboundInterceptionPromise = Promise.resolve();
  usingInterception = false;
  // =========================
  //     PUBLIC INTERFACE
  // =========================
  constructor(ctx, env, options) {
    super(ctx, env);
    if (ctx.container === void 0) {
      throw new Error("Containers have not been enabled for this Durable Object class. Have you correctly setup your Wrangler config? More info: https://developers.cloudflare.com/containers/get-started/#configuration");
    }
    this.state = new ContainerState(this.ctx.storage);
    const persistedOutboundConfiguration = this.restoreOutboundConfiguration();
    this.ctx.blockConcurrencyWhile(async () => {
      await this.scheduleNextAlarm();
      this.renewActivityTimeout();
      const ctor = this.constructor;
      if (persistedOutboundConfiguration !== void 0 || ctor.outboundByHost !== void 0 || ctor.outbound !== void 0 || ctor.outboundHandlers !== void 0 || this.effectiveAllowedHosts !== void 0 || this.effectiveDeniedHosts !== void 0) {
        this.usingInterception = true;
      }
      if (this.container.running) {
        this.applyOutboundInterceptionPromise = this.applyOutboundInterception();
      }
    });
    this.container = ctx.container;
    if (options) {
      if (options.defaultPort !== void 0)
        this.defaultPort = options.defaultPort;
      if (options.sleepAfter !== void 0)
        this.sleepAfter = options.sleepAfter;
      if (options.envVars !== void 0)
        this.envVars = options.envVars;
      if (options.entrypoint !== void 0)
        this.entrypoint = options.entrypoint;
      if (options.enableInternet !== void 0)
        this.enableInternet = options.enableInternet;
    }
    this.sql`
      CREATE TABLE IF NOT EXISTS container_schedules (
        id TEXT PRIMARY KEY NOT NULL DEFAULT (randomblob(9)),
        callback TEXT NOT NULL,
        payload TEXT,
        type TEXT NOT NULL CHECK(type IN ('scheduled', 'delayed')),
        time INTEGER NOT NULL,
        delayInSeconds INTEGER,
        created_at INTEGER DEFAULT (unixepoch())
      )
    `;
    if (this.container.running) {
      this.monitor = this.container.monitor();
      this.setupMonitorCallbacks();
    }
  }
  /**
   * Gets the current state of the container
   * @returns Promise<State>
   */
  async getState() {
    return { ...await this.state.getState() };
  }
  // ====================================
  //     OUTBOUND INTERCEPTION CONFIG
  // ====================================
  /**
   * Set the catch-all outbound handler to a named method from `outboundHandlers`.
   * Overrides the default `outbound` at runtime via ContainerProxy props.
   *
   * @param methodName - Name of a method defined in `static outboundHandlers`
   * @param params - Optional params passed to the handler as `ctx.params`
   * @throws Error if the method name is not found in `outboundHandlers`
   */
  async setOutboundHandler(methodName, ...paramsArg) {
    this.validateOutboundHandlerMethodName(methodName);
    this.outboundHandlerOverride = paramsArg.length === 0 ? { method: methodName } : { method: methodName, params: paramsArg[0] };
    await this.refreshOutboundInterception();
  }
  /**
   * Add or override a hostname-specific outbound handler at runtime,
   * referencing a named method from `outboundHandlers`.
   * Overrides any matching entry in `static outboundByHost` for this hostname.
   *
   * @param hostname - The hostname or ip:port to intercept (e.g. `'google.com'`)
   * @param methodName - Name of a method defined in `static outboundHandlers`
   * @param params - Optional params passed to the handler as `ctx.params`
   * @throws Error if the method name is not found in `outboundHandlers`
   */
  async setOutboundByHost(hostname, methodName, ...paramsArg) {
    this.validateOutboundHandlerMethodName(methodName);
    this.outboundByHostOverrides[hostname] = paramsArg.length === 0 ? { method: methodName } : { method: methodName, params: paramsArg[0] };
    await this.refreshOutboundInterception();
  }
  /**
   * Remove a runtime hostname override added via `setOutboundByHost`.
   * The default handler from `static outboundByHost` (if any) will be used again.
   *
   * @param hostname - The hostname or ip:port to stop overriding
   */
  async removeOutboundByHost(hostname) {
    delete this.outboundByHostOverrides[hostname];
    await this.refreshOutboundInterception();
  }
  /**
   * Replace all runtime hostname overrides at once.
   * Each value may be either a method name or an object with `method` and `params`.
   *
   * @param handlers - Record mapping hostnames to handler configs in `outboundHandlers`
   * @throws Error if any method name is not found in `outboundHandlers`
   */
  async setOutboundByHosts(handlers) {
    for (const handler of Object.values(handlers)) {
      const methodName = typeof handler === "string" ? handler : handler.method;
      this.validateOutboundHandlerMethodName(methodName);
    }
    this.outboundByHostOverrides = Object.fromEntries(Object.entries(handlers).map(([hostname, handler]) => [
      hostname,
      typeof handler === "string" ? { method: handler } : handler
    ]));
    await this.refreshOutboundInterception();
  }
  // ====================================
  //     ALLOWED / DENIED HOSTS CONFIG
  // ====================================
  /**
   * Replace all allowed hosts at runtime.
   * Allowed hosts get internet access even when `enableInternet` is false.
   *
   * @param hosts - Array of hostnames to allow (e.g. `['api.stripe.com', 'example.com']`)
   */
  async setAllowedHosts(hosts) {
    this.allowedHostsOverride = [...hosts];
    this.usingInterception = true;
    await this.refreshOutboundInterception();
  }
  /**
   * Replace all denied hosts at runtime.
   * Denied hosts are blocked unconditionally, even when `enableInternet` is true
   * or a catch-all outbound handler is set.
   *
   * @param hosts - Array of hostnames to deny (e.g. `['evil.com', 'blocked.org']`)
   */
  async setDeniedHosts(hosts) {
    this.deniedHostsOverride = [...hosts];
    this.usingInterception = true;
    await this.refreshOutboundInterception();
  }
  /**
   * Add a single hostname to the allowed hosts list at runtime.
   *
   * @param hostname - The hostname to allow (e.g. `'api.stripe.com'`)
   */
  async allowHost(hostname) {
    const effective = this.effectiveAllowedHosts ?? [];
    if (!effective.includes(hostname)) {
      this.allowedHostsOverride = [...effective, hostname];
    }
    this.usingInterception = true;
    await this.refreshOutboundInterception();
  }
  /**
   * Add a single hostname to the denied hosts list at runtime.
   *
   * @param hostname - The hostname to deny (e.g. `'evil.com'`)
   */
  async denyHost(hostname) {
    const effective = this.effectiveDeniedHosts ?? [];
    if (!effective.includes(hostname)) {
      this.deniedHostsOverride = [...effective, hostname];
    }
    this.usingInterception = true;
    await this.refreshOutboundInterception();
  }
  /**
   * Remove a hostname from the allowed hosts list.
   *
   * @param hostname - The hostname to remove from the allow list
   */
  async removeAllowedHost(hostname) {
    this.allowedHostsOverride = (this.effectiveAllowedHosts ?? []).filter((h) => h !== hostname);
    await this.refreshOutboundInterception();
  }
  /**
   * Remove a hostname from the denied hosts list.
   *
   * @param hostname - The hostname to remove from the deny list
   */
  async removeDeniedHost(hostname) {
    this.deniedHostsOverride = (this.effectiveDeniedHosts ?? []).filter((h) => h !== hostname);
    await this.refreshOutboundInterception();
  }
  // ==========================
  //     CONTAINER STARTING
  // ==========================
  /**
   * Start the container if it's not running and set up monitoring and lifecycle hooks,
   * without waiting for ports to be ready.
   *
   * It will automatically retry if the container fails to start, using the specified waitOptions
   *
   *
   * @example
   * await this.start({
   *   envVars: { DEBUG: 'true', NODE_ENV: 'development' },
   *   entrypoint: ['npm', 'run', 'dev'],
   *   enableInternet: false,
   *   labels: { tenant: 'acme', env: 'prod' },
   * });
   *
   * @param startOptions - Override `envVars`, `entrypoint`, `enableInternet` and `labels` on a per-instance basis
   * @param waitOptions - Optional wait configuration with abort signal for cancellation. Default ~8s timeout.
   * @returns A promise that resolves when the container start command has been issued
   * @throws Error if no container context is available or if all start attempts fail
   */
  async start(startOptions, waitOptions) {
    const portToCheck = waitOptions?.portToCheck ?? this.defaultPort ?? (this.requiredPorts ? this.requiredPorts[0] : FALLBACK_PORT_TO_CHECK);
    const pollInterval = waitOptions?.waitInterval ?? INSTANCE_POLL_INTERVAL_MS;
    await this.startContainerIfNotRunning({
      signal: waitOptions?.signal,
      waitInterval: pollInterval,
      retries: waitOptions?.retries ?? Math.ceil(TIMEOUT_TO_GET_CONTAINER_MS / pollInterval),
      portToCheck
    }, startOptions);
    this.setupMonitorCallbacks();
    await this.ctx.blockConcurrencyWhile(async () => {
      await this.onStart();
    });
  }
  async startAndWaitForPorts(portsOrArgs, cancellationOptions, startOptions) {
    let ports;
    let resolvedCancellationOptions;
    let resolvedStartOptions;
    if (typeof portsOrArgs === "object" && portsOrArgs !== null && !Array.isArray(portsOrArgs)) {
      ports = portsOrArgs.ports;
      resolvedCancellationOptions = portsOrArgs.cancellationOptions;
      resolvedStartOptions = portsOrArgs.startOptions;
    } else {
      ports = portsOrArgs;
      resolvedCancellationOptions = cancellationOptions;
      resolvedStartOptions = startOptions;
    }
    const portsToCheck = await this.getPortsToCheck(ports);
    await this.syncPendingStoppedEvents();
    resolvedCancellationOptions ??= {};
    const containerGetTimeout = resolvedCancellationOptions.instanceGetTimeoutMS ?? TIMEOUT_TO_GET_CONTAINER_MS;
    const pollInterval = resolvedCancellationOptions.waitInterval ?? INSTANCE_POLL_INTERVAL_MS;
    const containerGetRetries = Math.ceil(containerGetTimeout / pollInterval);
    const waitOptions = {
      signal: resolvedCancellationOptions.abort,
      retries: containerGetRetries,
      waitInterval: pollInterval,
      portToCheck: portsToCheck[0]
    };
    const triesUsed = await this.startContainerIfNotRunning(waitOptions, resolvedStartOptions);
    const totalPortReadyTries = Math.ceil((resolvedCancellationOptions.portReadyTimeoutMS ?? TIMEOUT_TO_GET_PORTS_MS) / pollInterval);
    let triesLeft = totalPortReadyTries - triesUsed;
    for (const port of portsToCheck) {
      triesLeft = await this.waitForPort({
        signal: resolvedCancellationOptions.abort,
        waitInterval: pollInterval,
        retries: triesLeft,
        portToCheck: port
      });
    }
    this.setupMonitorCallbacks();
    await this.ctx.blockConcurrencyWhile(async () => {
      await this.state.setHealthy();
      await this.onStart();
    });
  }
  /**
   *
   * Waits for a specified port to be ready
   *
   * Returns the number of tries used to get the port, or throws if it couldn't get the port within the specified retry limits.
   *
   * @param waitOptions -
   * - `portToCheck`: The port number to check
   * - `abort`: Optional AbortSignal to cancel waiting
   * - `retries`: Number of retries before giving up (default: TRIES_TO_GET_PORTS)
   * - `waitInterval`: Interval between retries in milliseconds (default: INSTANCE_POLL_INTERVAL_MS)
   */
  async waitForPort(waitOptions) {
    const port = waitOptions.portToCheck;
    const tcpPort = this.container.getTcpPort(port);
    const abortedSignal = new Promise((res) => {
      waitOptions.signal?.addEventListener("abort", () => {
        res(true);
      });
    });
    const pollInterval = waitOptions.waitInterval ?? INSTANCE_POLL_INTERVAL_MS;
    const tries = waitOptions.retries ?? Math.ceil(TIMEOUT_TO_GET_PORTS_MS / pollInterval);
    for (let i = 0; i < tries; i++) {
      try {
        const combinedSignal = addTimeoutSignal(waitOptions.signal, PING_TIMEOUT_MS);
        await tcpPort.fetch(`http://${this.pingEndpoint}`, { signal: combinedSignal });
        break;
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : String(e);
        if (!this.container.running) {
          try {
            await this.onError(new Error(`Container crashed while checking for ports, did you start the container and setup the entrypoint correctly?`));
          } catch {
          }
          throw e;
        }
        if (i === tries - 1) {
          try {
            await this.onError(`Failed to verify port ${port} is available after ${(i + 1) * pollInterval}ms, last error: ${errorMessage}`);
          } catch {
          }
          throw e;
        }
        await Promise.any([
          new Promise((resolve) => setTimeout(resolve, pollInterval)),
          abortedSignal
        ]);
        if (waitOptions.signal?.aborted) {
          throw new Error("Container request aborted.", { cause: e });
        }
      }
    }
    return tries;
  }
  // =======================
  //     LIFECYCLE HOOKS
  // =======================
  /**
   * Send a signal to the container.
   * @param signal - The signal to send to the container (default: 15 for SIGTERM)
   */
  async stop(signal = "SIGTERM") {
    if (this.container.running) {
      this.container.signal(typeof signal === "string" ? signalToNumbers[signal] : signal);
    }
    await this.syncPendingStoppedEvents();
  }
  /**
   * Destroys the container with a SIGKILL. Triggers onStop.
   */
  async destroy() {
    await this.container.destroy();
  }
  /**
   * Lifecycle method called when container starts successfully
   * Override this method in subclasses to handle container start events
   */
  onStart() {
  }
  /**
   * Lifecycle method called when container shuts down
   * Override this method in subclasses to handle Container stopped events
   * @param params - Object containing exitCode and reason for the stop
   */
  onStop(params) {
    void params;
  }
  /**
   * Lifecycle method called when the container is running, and the activity timeout
   * expiration (set by `sleepAfter`) has been reached.
   *
   * If you want to shutdown the container, you should call this.stop() here
   *
   * By default, this method calls `this.stop()`
   */
  async onActivityExpired() {
    console.log("Activity expired, signalling container to stop");
    if (!this.container.running) {
      return;
    }
    await this.stop();
  }
  /**
   * Error handler for container errors
   * Override this method in subclasses to handle container errors
   * @param error - The error that occurred
   * @returns Can return any value or throw the error
   */
  onError(error) {
    console.error("Container error:", error);
    throw error;
  }
  /**
   * Renew the container's activity timeout
   *
   * Call this method whenever there is activity on the container
   */
  renewActivityTimeout() {
    const timeoutInMs = parseTimeExpression(this.sleepAfter) * 1e3;
    this.sleepAfterMs = Date.now() + timeoutInMs;
  }
  /**
   * Decrement the inflight request counter.
   * When the counter transitions to 0, renew the activity timeout so the
   * inactivity window starts fresh from the moment the last request completes.
   */
  decrementInflight() {
    this.inflightRequests = Math.max(0, this.inflightRequests - 1);
    if (this.inflightRequests === 0) {
      this.renewActivityTimeout();
    }
  }
  // ==================
  //     SCHEDULING
  // ==================
  /**
   * Schedule a task to be executed in the future.
   *
   * We strongly recommend using this instead of the `alarm` handler.
   *
   * @template T Type of the payload data
   * @param when When to execute the task (Date object or number of seconds delay)
   * @param callback Name of the method to call
   * @param payload Data to pass to the callback
   * @returns Schedule object representing the scheduled task
   */
  async schedule(when, callback, payload) {
    const id = generateId(9);
    if (typeof callback !== "string") {
      throw new Error("Callback must be a string (method name)");
    }
    if (typeof this[callback] !== "function") {
      throw new Error(`this.${callback} is not a function`);
    }
    if (when instanceof Date) {
      const timestamp = Math.floor(when.getTime() / 1e3);
      this.sql`
        INSERT OR REPLACE INTO container_schedules (id, callback, payload, type, time)
        VALUES (${id}, ${callback}, ${JSON.stringify(payload)}, 'scheduled', ${timestamp})
      `;
      await this.scheduleNextAlarm();
      return {
        taskId: id,
        callback,
        payload,
        time: timestamp,
        type: "scheduled"
      };
    }
    if (typeof when === "number") {
      const time = Math.floor(Date.now() / 1e3 + when);
      this.sql`
        INSERT OR REPLACE INTO container_schedules (id, callback, payload, type, delayInSeconds, time)
        VALUES (${id}, ${callback}, ${JSON.stringify(payload)}, 'delayed', ${when}, ${time})
      `;
      await this.scheduleNextAlarm();
      return {
        taskId: id,
        callback,
        payload,
        delayInSeconds: when,
        time,
        type: "delayed"
      };
    }
    throw new Error("Invalid schedule type. 'when' must be a Date or number of seconds");
  }
  // ============
  //     HTTP
  // ============
  /**
   * Send a request to the container (HTTP or WebSocket) using standard fetch API signature
   *
   * This method handles HTTP requests to the container.
   *
   * WebSocket requests done outside the DO won't work until https://github.com/cloudflare/workerd/issues/2319 is addressed.
   * Until then, please use `switchPort` + `fetch()`.
   *
   * Method supports multiple signatures to match standard fetch API:
   * - containerFetch(request: Request, port?: number)
   * - containerFetch(url: string | URL, init?: RequestInit, port?: number)
   *
   * Starts the container if not already running, and waits for the target port to be ready.
   *
   * @returns A Response from the container
   */
  async containerFetch(requestOrUrl, portOrInit, portParam) {
    const { request, port } = this.requestAndPortFromContainerFetchArgs(requestOrUrl, portOrInit, portParam);
    const state = await this.state.getState();
    if (!this.container.running || state.status !== "healthy") {
      try {
        await this.startAndWaitForPorts(port, { abort: request.signal });
      } catch (e) {
        if (isNoInstanceError(e)) {
          return new Response("There is no Container instance available at this time.\nThis is likely because you have reached your max concurrent instance count (set in wrangler config) or are you currently provisioning the Container.\nIf you are deploying your Container for the first time, check your dashboard to see provisioning status, this may take a few minutes.", { status: 503 });
        }
        if (isRateLimitedError(e)) {
          return new Response(e instanceof Error ? e.message : String(e), { status: 429 });
        }
        return new Response(`Failed to start container: ${e instanceof Error ? e.message : String(e)}`, {
          status: 500
        });
      }
    }
    const tcpPort = this.container.getTcpPort(port);
    const containerUrl = request.url.replace("https:", "http:");
    this.inflightRequests++;
    try {
      this.renewActivityTimeout();
      const res = await tcpPort.fetch(containerUrl, request);
      if (res.webSocket !== null) {
        const containerWs = res.webSocket;
        const [client, server] = Object.values(new WebSocketPair());
        let settled = false;
        const settleInflight = /* @__PURE__ */ __name(() => {
          if (!settled) {
            settled = true;
            this.decrementInflight();
          }
        }, "settleInflight");
        containerWs.accept();
        server.accept();
        server.addEventListener("message", async (event) => {
          this.renewActivityTimeout();
          try {
            const data = event.data instanceof Blob ? await event.data.arrayBuffer() : event.data;
            containerWs.send(data);
          } catch {
            server.close(1011, "Failed to forward message to container");
          }
        });
        containerWs.addEventListener("message", async (event) => {
          this.renewActivityTimeout();
          try {
            const data = event.data instanceof Blob ? await event.data.arrayBuffer() : event.data;
            server.send(data);
          } catch {
            containerWs.close(1011, "Failed to forward message to client");
          }
        });
        server.addEventListener("close", (event) => {
          settleInflight();
          const code = event.code === 1005 || event.code === 1006 ? 1e3 : event.code;
          containerWs.close(code, event.reason);
        });
        containerWs.addEventListener("close", (event) => {
          settleInflight();
          const code = event.code === 1005 || event.code === 1006 ? 1e3 : event.code;
          server.close(code, event.reason);
        });
        server.addEventListener("error", () => {
          settleInflight();
          containerWs.close(1011, "Client WebSocket error");
        });
        containerWs.addEventListener("error", () => {
          settleInflight();
          server.close(1011, "Container WebSocket error");
        });
        return new Response(null, { status: res.status, webSocket: client, headers: res.headers });
      }
      if (res.body !== null) {
        const { readable, writable } = new IdentityTransformStream();
        res.body?.pipeTo(writable).finally(() => {
          this.decrementInflight();
        });
        return new Response(readable, res);
      }
      this.decrementInflight();
      return res;
    } catch (e) {
      this.decrementInflight();
      if (!(e instanceof Error)) {
        throw e;
      }
      if (e.message.includes("Network connection lost.")) {
        return new Response("Container suddenly disconnected, try again", { status: 500 });
      }
      console.error(`Error proxying request to container ${this.ctx.id}:`, e);
      return new Response(`Error proxying request to container: ${e instanceof Error ? e.message : String(e)}`, { status: 500 });
    }
  }
  /**
   *
   * Fetch handler on the Container class.
   * By default this forwards all requests to the container by calling `containerFetch`.
   * Use `switchPort` to specify which port on the container to target, or this will use `defaultPort`.
   * @param request The request to handle
   */
  async fetch(request) {
    if (this.defaultPort === void 0 && !request.headers.has("cf-container-target-port")) {
      throw new Error("No port configured for this container. Set the `defaultPort` in your Container subclass, or specify a port with `container.fetch(switchPort(request, port))`.");
    }
    let portValue = this.defaultPort;
    if (request.headers.has("cf-container-target-port")) {
      const portFromHeaders = parseInt(request.headers.get("cf-container-target-port") ?? "");
      if (isNaN(portFromHeaders)) {
        throw new Error("port value from switchPort is not a number");
      } else {
        portValue = portFromHeaders;
      }
    }
    return await this.containerFetch(request, portValue);
  }
  // ===============================
  // ===============================
  //     PRIVATE METHODS & ATTRS
  // ===============================
  // ===============================
  // ==========================
  //     PRIVATE ATTRIBUTES
  // ==========================
  container;
  // onStopCalled will be true when we are in the middle of an onStop call
  onStopCalled = false;
  state;
  monitor;
  // Coalesces concurrent calls to startContainerIfNotRunning so we never
  // call `this.container.start()` twice. Without this guard, two requests
  // racing the readiness path can both pass the `if (this.container.running)`
  // early-return (each yielding the DO input gate at storage awaits) and
  // both reach the synchronous workerd `start()`, causing the second to
  // throw "start() cannot be called on a container that is already running."
  // See https://github.com/cloudflare/containers/issues/173.
  startInFlight;
  monitoredPromise;
  sleepAfterMs = 0;
  inflightRequests = 0;
  // Outbound interception runtime overrides (passed through ContainerProxy props)
  outboundByHostOverrides = {};
  outboundHandlerOverride;
  // Only set when the user calls setAllowedHosts/setDeniedHosts at runtime
  allowedHostsOverride;
  deniedHostsOverride;
  // The runtime does not expose a way to remove outbound interceptions yet, so
  // once we promote an instance to intercept-all we must keep using it.
  hasInterceptAllRegistration = false;
  // ==========================
  //     GENERAL HELPERS
  // ==========================
  /**
   * Validates that a method name exists in the outboundHandlers registry for this class.
   * @throws Error if the method name is not found
   */
  validateOutboundHandlerMethodName(methodName) {
    const handlers = outboundHandlersRegistry.get(this.constructor.name);
    if (!handlers || !(methodName in handlers)) {
      throw new Error(`Outbound handler method '${methodName}' not found in outboundHandlers for ${this.constructor.name}`);
    }
  }
  get effectiveAllowedHosts() {
    return this.allowedHostsOverride ?? this.allowedHosts;
  }
  get effectiveDeniedHosts() {
    return this.deniedHostsOverride ?? this.deniedHosts;
  }
  getOutboundConfiguration() {
    return {
      outboundByHostOverrides: Object.keys(this.outboundByHostOverrides).length > 0 ? this.outboundByHostOverrides : void 0,
      outboundHandlerOverride: this.outboundHandlerOverride,
      allowedHosts: this.effectiveAllowedHosts,
      deniedHosts: this.effectiveDeniedHosts,
      hasInterceptAllRegistration: this.hasInterceptAllRegistration || void 0
    };
  }
  persistOutboundConfiguration(configuration) {
    this.ctx.storage.kv.put(OUTBOUND_CONFIGURATION_KEY, {
      ...configuration,
      allowedHosts: this.allowedHostsOverride,
      deniedHosts: this.deniedHostsOverride
    });
  }
  restoreOutboundConfiguration() {
    const configuration = this.ctx.storage.kv.get(OUTBOUND_CONFIGURATION_KEY);
    if (!configuration) {
      return void 0;
    }
    this.outboundHandlerOverride = void 0;
    if (configuration.outboundHandlerOverride !== void 0) {
      try {
        this.validateOutboundHandlerMethodName(configuration.outboundHandlerOverride.method);
        this.outboundHandlerOverride = configuration.outboundHandlerOverride;
      } catch (error) {
        console.warn("Ignoring invalid persisted outbound handler override:", error);
      }
    }
    this.outboundByHostOverrides = {};
    for (const [hostname, override] of Object.entries(configuration.outboundByHostOverrides ?? {})) {
      try {
        this.validateOutboundHandlerMethodName(override.method);
        this.outboundByHostOverrides[hostname] = override;
      } catch (error) {
        console.warn(`Ignoring invalid persisted outbound override for ${hostname}:`, error);
      }
    }
    this.hasInterceptAllRegistration = configuration.hasInterceptAllRegistration === true;
    if (configuration.allowedHosts) {
      this.allowedHostsOverride = configuration.allowedHosts;
    }
    if (configuration.deniedHosts) {
      this.deniedHostsOverride = configuration.deniedHosts;
    }
    return this.getOutboundConfiguration();
  }
  /**
   * Returns true if a catch-all outbound HTTP interception is needed.
   * This is the case when a static `outbound` handler or a runtime
   * `outboundHandlerOverride` (catch-all) is configured.
   * When false, we only intercept specific hosts to avoid overhead.
   */
  needsCatchAllInterception() {
    const ctor = this.constructor;
    return ctor.outbound !== void 0 || this.outboundHandlerOverride !== void 0;
  }
  hasMutableOutboundConfiguration() {
    return Object.keys(this.outboundByHostOverrides).length > 0 || this.allowedHostsOverride !== void 0 || this.deniedHostsOverride !== void 0;
  }
  shouldInterceptAllOutbound() {
    return this.hasInterceptAllRegistration || this.needsCatchAllInterception() || this.effectiveAllowedHosts !== void 0 || this.effectiveDeniedHosts !== void 0 || this.hasMutableOutboundConfiguration();
  }
  getStaticOutboundByHostKeys() {
    const ctor = this.constructor;
    return ctor.outboundByHost ? Object.keys(ctor.outboundByHost) : [];
  }
  /**
   * Collects all hostnames that need per-host outbound interception.
   * This path is only used for the narrow optimized case where outbound
   * handling is static and host-specific.
   */
  getHostsToIntercept() {
    const hosts = /* @__PURE__ */ new Set();
    const ctor = this.constructor;
    if (ctor.outboundByHost) {
      for (const hostname of Object.keys(ctor.outboundByHost)) {
        hosts.add(hostname);
      }
    }
    for (const hostname of Object.keys(this.outboundByHostOverrides)) {
      hosts.add(hostname);
    }
    return [...hosts];
  }
  async refreshOutboundInterception() {
    if (!this.usingInterception) {
      return;
    }
    this.applyOutboundInterceptionPromise = this.applyOutboundInterception();
    await this.applyOutboundInterceptionPromise;
  }
  /**
   * Applies (or re-applies) outbound HTTP interception with the current
   * default registries + runtime overrides passed through ContainerProxy props.
   *
   * Uses per-host interception only for static host-specific outbound handlers.
   * As soon as the config needs to evaluate all hosts (catch-all outbound,
   * allow/deny lists, or runtime-mutated outbound config), we promote the
   * container to intercept-all and keep it there until the instance restarts.
   *
   * When `interceptHttps` is enabled, also applies HTTPS interception:
   * - Intercept-all mode: `interceptOutboundHttps('*', ...)` for all HTTPS traffic
   * - Per-host mode: `interceptOutboundHttps(host, ...)` for each known host
   */
  async applyOutboundInterception() {
    const ctx = this.ctx;
    if (ctx.exports === void 0) {
      throw new Error("ctx.exports is undefined, please try to update your compatibility date or export ContainerProxy from the containers package in your worker entrypoint");
    }
    if (ctx.exports.ContainerProxy === void 0) {
      throw new Error("ctx.exports.ContainerProxy is undefined, export ContainerProxy from the containers package in your worker entrypoint");
    }
    const interceptAll = this.shouldInterceptAllOutbound();
    if (interceptAll) {
      this.hasInterceptAllRegistration = interceptAll;
    }
    const outboundConfiguration = this.getOutboundConfiguration();
    this.persistOutboundConfiguration(outboundConfiguration);
    const hosts = this.getHostsToIntercept();
    const props = {
      enableInternet: this.enableInternet,
      containerId: this.ctx.id.toString(),
      className: this.constructor.name,
      outboundByHostOverrides: outboundConfiguration.outboundByHostOverrides,
      outboundHandlerOverride: outboundConfiguration.outboundHandlerOverride,
      allowedHosts: outboundConfiguration.allowedHosts,
      deniedHosts: outboundConfiguration.deniedHosts,
      interceptAll
    };
    const fetcher = ctx.exports.ContainerProxy({
      props
    });
    if (interceptAll) {
      for (const host of this.getStaticOutboundByHostKeys()) {
        await this.container.interceptOutboundHttp(host, fetcher);
        if (this.interceptHttps) {
          await this.container.interceptOutboundHttps(host, fetcher);
        }
      }
      if (this.interceptHttps) {
        await this.container.interceptOutboundHttps("*", fetcher);
      }
      await this.container.interceptAllOutboundHttp(fetcher);
    } else {
      for (const host of hosts) {
        await this.container.interceptOutboundHttp(host, fetcher);
        if (this.interceptHttps) {
          await this.container.interceptOutboundHttps(host, fetcher);
        }
      }
    }
  }
  /**
   * Execute SQL queries against the Container's database
   */
  sql(strings, ...values) {
    const query = strings.reduce((acc, str, i) => acc + str + (i < values.length ? "?" : ""), "");
    return [...this.ctx.storage.sql.exec(query, ...values)];
  }
  requestAndPortFromContainerFetchArgs(requestOrUrl, portOrInit, portParam) {
    let request;
    let port;
    if (requestOrUrl instanceof Request) {
      request = requestOrUrl;
      port = typeof portOrInit === "number" ? portOrInit : void 0;
    } else {
      const url = typeof requestOrUrl === "string" ? requestOrUrl : requestOrUrl.toString();
      const init = typeof portOrInit === "number" ? {} : portOrInit || {};
      port = typeof portOrInit === "number" ? portOrInit : typeof portParam === "number" ? portParam : void 0;
      request = new Request(url, init);
    }
    port ??= this.defaultPort;
    if (port === void 0) {
      throw new Error("No port specified for container fetch. Set defaultPort or specify a port parameter.");
    }
    return { request, port };
  }
  /**
   *
   * The method prioritizes port sources in this order:
   * 1. Ports specified directly in the method call
   * 2. `requiredPorts` class property (if set)
   * 3. `defaultPort` (if neither of the above is specified)
   * 4. Falls back to port 33 if none of the above are set
   */
  async getPortsToCheck(overridePorts) {
    if (overridePorts !== void 0) {
      return Array.isArray(overridePorts) ? overridePorts : [overridePorts];
    }
    if (this.requiredPorts && this.requiredPorts.length > 0) {
      return [...this.requiredPorts];
    }
    return [this.defaultPort ?? FALLBACK_PORT_TO_CHECK];
  }
  // ===========================================
  //     CONTAINER INTERACTION & MONITORING
  // ===========================================
  /**
   * Tries to start a container if it's not already running
   * Returns the number of tries used
   */
  async startContainerIfNotRunning(waitOptions, options) {
    if (this.startInFlight) {
      return this.startInFlight;
    }
    if (this.container.running) {
      if (!this.monitor) {
        this.monitor = this.container.monitor();
      }
      return 0;
    }
    const startPromise = this.doStartContainer(waitOptions, options);
    this.startInFlight = startPromise;
    try {
      return await startPromise;
    } finally {
      if (this.startInFlight === startPromise) {
        this.startInFlight = void 0;
      }
    }
  }
  async doStartContainer(waitOptions, options) {
    const abortedSignal = new Promise((res) => {
      waitOptions.signal?.addEventListener("abort", () => {
        res(true);
      });
    });
    const pollInterval = waitOptions.waitInterval ?? INSTANCE_POLL_INTERVAL_MS;
    const totalTries = waitOptions.retries ?? Math.ceil(TIMEOUT_TO_GET_CONTAINER_MS / pollInterval);
    for (let tries = 0; tries < totalTries; tries++) {
      const envVars = options?.envVars ?? this.envVars;
      const entrypoint = options?.entrypoint ?? this.entrypoint;
      const enableInternet = options?.enableInternet ?? this.enableInternet;
      const labels = options?.labels ?? this.labels;
      const startConfig = {
        enableInternet
      };
      if (envVars && Object.keys(envVars).length > 0)
        startConfig.env = envVars;
      if (entrypoint)
        startConfig.entrypoint = entrypoint;
      if (labels && Object.keys(labels).length > 0)
        startConfig.labels = labels;
      this.renewActivityTimeout();
      const handleError = /* @__PURE__ */ __name(async () => {
        const err = await this.monitor?.catch((err2) => err2);
        if (typeof err === "number") {
          const toThrow = new Error(`Container exited before we could determine the container health, exit code: ${err}`);
          await this.state.setStoppedWithCode(err);
          this.monitor = void 0;
          try {
            await this.onError(toThrow);
          } catch {
          }
          throw toThrow;
        } else if (!isNoInstanceError(err)) {
          await this.state.setStopped();
          this.monitor = void 0;
          try {
            await this.onError(err);
          } catch {
          }
          throw err;
        }
      }, "handleError");
      if (tries > 0 && !this.container.running) {
        await handleError();
      }
      await this.scheduleNextAlarm();
      if (!this.container.running) {
        await this.refreshOutboundInterception();
        this.container.start(startConfig);
        this.monitor = this.container.monitor();
        await this.state.setRunning();
      } else {
        await this.scheduleNextAlarm();
      }
      this.renewActivityTimeout();
      const port = this.container.getTcpPort(waitOptions.portToCheck);
      try {
        const combinedSignal = addTimeoutSignal(waitOptions.signal, PING_TIMEOUT_MS);
        await port.fetch("http://containerstarthealthcheck", { signal: combinedSignal });
        return tries;
      } catch (error) {
        if (isNotListeningError(error) && this.container.running) {
          return tries;
        }
        if (!this.container.running && isNotListeningError(error)) {
          await handleError();
        }
        await Promise.any([
          new Promise((res) => setTimeout(res, waitOptions.waitInterval)),
          abortedSignal
        ]);
        if (waitOptions.signal?.aborted) {
          throw new Error("Aborted waiting for container to start as we received a cancellation signal", { cause: error });
        }
        if (totalTries === tries + 1) {
          if (error instanceof Error && error.message.includes("Network connection lost")) {
            this.ctx.abort();
          }
          await handleError();
          await this.state.setStopped();
          this.monitor = void 0;
          throw new Error(NO_CONTAINER_INSTANCE_ERROR, { cause: error });
        }
        continue;
      }
    }
    throw new Error(`Container did not start after ${totalTries * pollInterval}ms`);
  }
  setupMonitorCallbacks() {
    const monitor = this.monitor;
    if (!monitor || this.monitoredPromise === monitor) {
      return;
    }
    this.monitoredPromise = monitor;
    monitor.then(async () => {
      await this.ctx.blockConcurrencyWhile(async () => {
        if (this.monitor === monitor) {
          await this.state.setStoppedWithCode(0);
        }
      });
    }).catch(async (error) => {
      if (this.monitor !== monitor) {
        return;
      }
      if (isNoInstanceError(error)) {
        await this.ctx.blockConcurrencyWhile(async () => {
          if (this.monitor === monitor) {
            await this.state.setStopped();
          }
        });
        return;
      }
      const exitCode = getExitCodeFromError(error);
      if (exitCode !== null) {
        await this.ctx.blockConcurrencyWhile(async () => {
          if (this.monitor === monitor) {
            await this.state.setStoppedWithCode(exitCode);
          }
        });
        return;
      }
      await this.ctx.blockConcurrencyWhile(async () => {
        if (this.monitor === monitor) {
          await this.state.setStopped();
        }
      });
      if (this.monitor !== monitor) {
        return;
      }
      try {
        await this.onError(error);
      } catch {
      }
    }).finally(() => {
      if (this.monitor !== monitor) {
        return;
      }
      this.monitoredPromise = void 0;
      this.monitor = void 0;
      if (this.timeout) {
        if (this.resolve)
          this.resolve();
        clearTimeout(this.timeout);
      }
    });
  }
  deleteSchedules(name) {
    this.sql`DELETE FROM container_schedules WHERE callback = ${name}`;
  }
  // ============================
  //     ALARMS AND SCHEDULES
  // ============================
  /**
   * Method called when an alarm fires
   * Executes any scheduled tasks that are due
   */
  async alarm(alarmProps) {
    if (alarmProps !== void 0 && alarmProps.isRetry && alarmProps.retryCount > MAX_ALARM_RETRIES) {
      const scheduleCount = Number(this.sql`SELECT COUNT(*) as count FROM container_schedules`[0]?.count) || 0;
      const hasScheduledTasks = scheduleCount > 0;
      if (hasScheduledTasks || this.container.running) {
        await this.scheduleNextAlarm();
      }
      return;
    }
    const prevAlarm = Date.now();
    await this.ctx.storage.setAlarm(prevAlarm);
    await this.ctx.storage.sync();
    const result = this.sql`
         SELECT * FROM container_schedules;
       `;
    let minTime = Date.now() + 3 * 60 * 1e3;
    const now = Date.now() / 1e3;
    for (const row of result) {
      if (row.time > now) {
        continue;
      }
      const callback = this[row.callback];
      if (!callback || typeof callback !== "function") {
        console.error(`Callback ${row.callback} not found or is not a function`);
        continue;
      }
      const schedule = this.getSchedule(row.id);
      try {
        const payload = row.payload ? JSON.parse(row.payload) : void 0;
        await callback.call(this, payload, await schedule);
      } catch (e) {
        console.error(`Error executing scheduled callback "${row.callback}":`, e);
      }
      this.sql`DELETE FROM container_schedules WHERE id = ${row.id}`;
    }
    const resultForMinTime = this.sql`
         SELECT * FROM container_schedules;
       `;
    const minTimeFromSchedules = Math.min(...resultForMinTime.map((r) => r.time * 1e3));
    if (!this.container.running) {
      await this.syncPendingStoppedEvents();
      if (resultForMinTime.length == 0) {
        await this.ctx.storage.deleteAlarm();
      } else {
        await this.ctx.storage.setAlarm(minTimeFromSchedules);
      }
      return;
    }
    if (this.isActivityExpired()) {
      await this.onActivityExpired();
      this.renewActivityTimeout();
      return;
    }
    minTime = Math.min(minTimeFromSchedules, minTime, this.sleepAfterMs);
    const timeout = Math.max(0, minTime - Date.now());
    await new Promise((resolve) => {
      this.resolve = resolve;
      if (!this.container.running) {
        resolve();
        return;
      }
      this.timeout = setTimeout(() => {
        resolve();
      }, timeout);
    });
    await this.ctx.storage.setAlarm(Date.now());
  }
  timeout;
  resolve;
  // synchronises container state with the container source of truth to process events
  async syncPendingStoppedEvents() {
    const state = await this.state.getState();
    if (!this.container.running && (state.status === "healthy" || state.status === "running")) {
      await this.callOnStop({ exitCode: 0, reason: "exit" }, state);
      return;
    }
    if (!this.container.running && state.status === "stopped_with_code") {
      await this.callOnStop({ exitCode: state.exitCode ?? 0, reason: "exit" }, state);
      return;
    }
  }
  async callOnStop(onStopParams, stateBeforeOnStop) {
    if (this.onStopCalled) {
      return;
    }
    this.onStopCalled = true;
    const promise = this.onStop(onStopParams);
    if (promise instanceof Promise) {
      await promise.finally(() => {
        this.onStopCalled = false;
      });
    } else {
      this.onStopCalled = false;
    }
    await this.state.setStoppedIfUnchanged(stateBeforeOnStop);
  }
  /**
   * Schedule the next alarm based on upcoming tasks
   */
  async scheduleNextAlarm(ms = 1e3) {
    const nextTime = ms + Date.now();
    if (this.timeout) {
      if (this.resolve)
        this.resolve();
      clearTimeout(this.timeout);
    }
    await this.ctx.storage.setAlarm(nextTime);
    await this.ctx.storage.sync();
  }
  async listSchedules(name) {
    const result = this.sql`
      SELECT * FROM container_schedules WHERE callback = ${name} LIMIT 1
    `;
    if (!result || result.length === 0) {
      return [];
    }
    return result.map(this.toSchedule);
  }
  toSchedule(schedule) {
    let payload;
    try {
      payload = JSON.parse(schedule.payload);
    } catch (e) {
      console.error(`Error parsing payload for schedule ${schedule.id}:`, e);
      payload = void 0;
    }
    if (schedule.type === "delayed") {
      return {
        taskId: schedule.id,
        callback: schedule.callback,
        payload,
        type: "delayed",
        time: schedule.time,
        delayInSeconds: schedule.delayInSeconds
      };
    }
    return {
      taskId: schedule.id,
      callback: schedule.callback,
      payload,
      type: "scheduled",
      time: schedule.time
    };
  }
  /**
   * Get a scheduled task by ID
   * @template T Type of the payload data
   * @param id ID of the scheduled task
   * @returns The Schedule object or undefined if not found
   */
  async getSchedule(id) {
    const result = this.sql`
      SELECT * FROM container_schedules WHERE id = ${id} LIMIT 1
    `;
    if (!result || result.length === 0) {
      return void 0;
    }
    const schedule = result[0];
    return this.toSchedule(schedule);
  }
  isActivityExpired() {
    if (this.inflightRequests > 0) {
      this.renewActivityTimeout();
      return false;
    }
    return this.sleepAfterMs <= Date.now();
  }
};

// ../../node_modules/@cloudflare/containers/dist/lib/utils.js
var singletonContainerId = "cf-singleton-container";
function getContainer(binding, name = singletonContainerId) {
  const objectId = binding.idFromName(name);
  return binding.get(objectId);
}
__name(getContainer, "getContainer");

// src/commands.ts
function loadCommands(json) {
  if (typeof json !== "object" || json === null || Array.isArray(json)) {
    throw new Error("commands.json must be an object");
  }
  const out = {};
  for (const [name, value] of Object.entries(json)) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`command ${name} is not an object`);
    }
    out[name] = value;
  }
  return out;
}
__name(loadCommands, "loadCommands");
function assertKnownCommand(name, commands) {
  const spec = commands[name];
  if (!spec) {
    throw new Error(`unknown command: ${name}`);
  }
  return spec;
}
__name(assertKnownCommand, "assertKnownCommand");

// commands.json
var commands_default = {
  "market-data-refresh": {
    timeout_seconds: 1800,
    concurrency: "market-data-refresh",
    code_ref: "main",
    alias_supabase: true,
    env: ["R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CORE_POSTGRES_URI", "CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "scripts/refresh_market_data_r2.py", "--manifest-out", "/tmp/market-data-refresh.json"]
    ],
    publish: ["/tmp/market-data-refresh.json"]
  },
  "prices-fx-candles": {
    timeout_seconds: 600,
    concurrency: "digiquant-fx-candles",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-fx-intraday", "--supabase"],
      ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-fx-intraday", "--interval", "5m", "--period", "60d", "--supabase"]
    ]
  },
  "prices-at-open": {
    timeout_seconds: 900,
    concurrency: "digiquant-at-open",
    code_ref: "main",
    alias_supabase: true,
    market_backend: "r2",
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY", "R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/execute_at_open.py", "--prior-trading-day-rebalance", "--require-ledger"]
    ]
  },
  "prices-eod-macro": {
    timeout_seconds: 1200,
    concurrency: "digiquant-eod-macro",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "sync-calendar", "--venues", "NYSE,NASDAQ,CRYPTO,FX", "--start", "1950-01-01", "--end", "+5y", "--supabase"] },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--supabase"], when_arg: "run_writers", equals: "true" }
    ]
  },
  "prices-fx-refresh-writers": {
    timeout_seconds: 600,
    concurrency: "digiquant-fx-refresh",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--sources", "yahoo", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--latest-only", "--supabase"], when_arg: "run_writers", equals: "true" }
    ]
  },
  "onchain-bitview": {
    timeout_seconds: 900,
    concurrency: "digiquant-onchain",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "onchain", "fetch-bitview", "--cache-dir", "data/onchain/bitview", "--supabase"]
    ]
  },
  "execution-cron-check": {
    timeout_seconds: 600,
    concurrency: "execution-cron-check",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY", "CLOUDFLARE_EMAIL_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "NOTIFY_FROM"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "scripts/execution_cron_check.py"],
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant.dashboard.overlay", "--dry-run"], always: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant.execution.sync_cron", "--dry-run"], always: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant.execution.route_cron", "--dry-run"], always: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant.notify.dispatch", "--dry-run"], always: true }
    ]
  },
  "research-metrics": {
    timeout_seconds: 1200,
    concurrency: "research-refresh-metrics",
    code_ref: "main",
    alias_supabase: true,
    market_backend: "r2",
    extra_env: { DIGIQUANT_ACCOUNTING_FINALIZER: "shadow" },
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY", "R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"],
    steps: [
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/finalize_period_accounting.py", "--supabase", "--date"], when_arg_set: "date", append_arg: "date", continue_on_error: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/finalize_period_accounting.py", "--supabase"], when_arg_empty: "date", continue_on_error: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/verify_nav_replay.py", "--write", "--date"], when_arg_set: "date", append_arg: "date" },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/verify_nav_replay.py", "--write", "--mark-through"], when_arg_empty: "date", append_utc_date: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/refresh_performance_metrics.py", "--supabase", "--date"], when_arg_set: "date", append_arg: "date" },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/refresh_performance_metrics.py", "--supabase", "--mark-through-book"], when_arg_empty: "date" },
      ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/verify_nav_replay.py"],
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/refresh_attribution.py", "--date"], when_arg_set: "date", append_arg: "date", always: true },
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/refresh_attribution.py"], when_arg_empty: "date", always: true }
    ]
  },
  tearsheets: {
    timeout_seconds: 2700,
    concurrency: "digiquant-tearsheets",
    code_ref: "main",
    alias_supabase: true,
    env: ["CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/verify_strategy_calibrations_rls.py"],
      ["uv", "run", "--frozen", "--with", "ccxt", "python", "digiquant/scripts/fetch_coinbase.py", "--through-yesterday"],
      { argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/export_sdca_macro.py"], when_file: "digiquant/scripts/export_sdca_macro.py" },
      ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/generate_tearsheets.py", "--from-supabase", "--push-supabase", "--signal-delay-days", "3", "--cache-dir", "digiquant/data/price-history"]
    ]
  },
  "house-run": {
    timeout_seconds: 14400,
    concurrency: "digiquant-pipeline",
    code_ref: "main",
    alias_supabase: true,
    pipeline_env: ".github/digiquant-pipeline.yml",
    checkpoint_run_id: true,
    export_args: ["refresh_scope", "run_date", "dry_run", "resume_run_id"],
    publish_dir: "artifacts",
    publish_always: true,
    extra_env: {
      DIGIKEY_URL: "https://key.digithings.ai",
      DIGISEARCH_URL: "https://search.digithings.ai",
      CHEAPERINFERENCE_API_BASE: "https://api.cheaperinference.com/v1",
      LANGSMITH_PROJECT: "digiquant-baseline",
      DIGILLM_PROVIDER_MAX_ATTEMPTS: "2",
      DIGILLM_EMPTY_RETRY_MAX: "1",
      DIGILLM_MAX_CONCURRENT_CALLS: "8",
      DIGIQUANT_SHADOW_ARTIFACT_MODE: "export",
      DIGIQUANT_SHADOW_ARTIFACT_DIR: "artifacts"
    },
    env: [
      "DIGIQUANT_DIGIKEY_API_KEY",
      "OPENROUTER_API_KEY",
      "CHEAPERINFERENCE_API_KEY",
      "CHEAPERINFERENCE_API_BASE",
      "CORE_POSTGRES_URI",
      "LANGSMITH_API_KEY",
      "R2_ACCOUNT_ID",
      "R2_BUCKET",
      "R2_ACCESS_KEY_ID",
      "R2_SECRET_ACCESS_KEY",
      "CORE_SUPABASE_URL",
      "CORE_SUPABASE_SERVICE_KEY"
    ],
    steps: [
      {
        argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--sources", "fedprob", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--dry-run"],
        when_arg: "dry_run",
        equals: "true",
        continue_on_error: true
      },
      {
        argv: ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--sources", "fedprob", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--supabase"],
        when_arg_empty: "dry_run",
        continue_on_error: true
      },
      {
        argv: ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/validate-providers.py", "--skip-dry-run"],
        step_timeout_seconds: 600
      },
      {
        argv: ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/wake_stack.py"],
        continue_on_error: true
      },
      ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/web_search_preflight.py"],
      {
        argv: ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/house_chain_step.py"],
        step_timeout_seconds: 13800
      }
    ]
  },
  "allocation-shadow": {
    timeout_seconds: 600,
    concurrency: "digiquant-allocation-shadow",
    code_ref: "main",
    stage_r2_prefix_arg: "artifact_prefix",
    env: [],
    steps: [
      ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/check_allocation_shadow_isolation.py", "--output", "/tmp/allocation-shadow-isolation-report.json"]
    ],
    publish: ["/tmp/allocation-shadow-isolation-report.json"]
  }
};

// src/runner-session.ts
var HEARTBEAT_MS = 6e4;
var MAX_INFLIGHT = 2;
var WATCHDOG_GRACE_SECONDS = 120;
var STATE_KEY = "runner-state";
var COMMANDS = loadCommands(commands_default);
function emptyLedger() {
  return { idem: {}, locks: {}, runs: {}, queue: [] };
}
__name(emptyLedger, "emptyLedger");
function isTerminal(status) {
  return status === "succeeded" || status === "failed" || status === "timed_out";
}
__name(isTerminal, "isTerminal");
function houseLockHeld(ledger) {
  return Object.values(ledger.locks).some(
    (lock) => ledger.runs[lock.run_id]?.command === "house-run"
  );
}
__name(houseLockHeld, "houseLockHeld");
function mustQueue(ledger, command) {
  if (Object.keys(ledger.locks).length >= MAX_INFLIGHT) return true;
  if (houseLockHeld(ledger) && command !== "house-run") return true;
  if (command === "house-run" && Object.keys(ledger.locks).length > 0) return true;
  return false;
}
__name(mustQueue, "mustQueue");
function asRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value;
}
__name(asRecord, "asRecord");
function parseRunJob(value) {
  const body = asRecord(value);
  if (!body) return null;
  const args = asRecord(body.args) ?? {};
  const stringArgs = {};
  for (const [key, item] of Object.entries(args)) {
    if (typeof item !== "string") return null;
    stringArgs[key] = item;
  }
  if (typeof body.job_id !== "string" || typeof body.command !== "string") return null;
  if (typeof body.concurrency !== "string" || typeof body.idempotency_key !== "string") {
    return null;
  }
  if (typeof body.timeout_seconds !== "number" || typeof body.scheduled_time !== "number") {
    return null;
  }
  if (body.code_ref !== "main" || typeof body.cron !== "string") return null;
  if (!body.idempotency_key) return null;
  return {
    job_id: body.job_id,
    command: body.command,
    args: stringArgs,
    concurrency: body.concurrency,
    timeout_seconds: body.timeout_seconds,
    code_ref: "main",
    cron: body.cron,
    scheduled_time: body.scheduled_time,
    idempotency_key: body.idempotency_key
  };
}
__name(parseRunJob, "parseRunJob");
var RunnerSession = class {
  constructor(deps) {
    this.deps = deps;
    this.now = deps.now ?? (() => Date.now());
  }
  deps;
  static {
    __name(this, "RunnerSession");
  }
  now;
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    if (request.method === "GET" && path === "/healthz") {
      return Response.json(await this.health());
    }
    if (request.method === "POST" && path === "/v1/jobs") {
      let parsed;
      try {
        parsed = await request.json();
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      const job = parseRunJob(parsed);
      if (!job) return Response.json({ error: "invalid_body" }, { status: 400 });
      try {
        assertKnownCommand(job.command, COMMANDS);
      } catch (err) {
        const message = err instanceof Error ? err.message : "unknown command";
        return Response.json({ error: message }, { status: 400 });
      }
      try {
        const body = await this.accept(job);
        return Response.json(body, { status: 202 });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return Response.json({ error: message }, { status: 500 });
      }
    }
    if (request.method === "GET" && path.startsWith("/v1/jobs/")) {
      const runId = decodeURIComponent(path.slice("/v1/jobs/".length));
      const run = await this.getRun(runId);
      if (!run) return Response.json({ error: "not_found" }, { status: 404 });
      return Response.json(publicRun(run));
    }
    return new Response("Not Found", { status: 404 });
  }
  async health() {
    const ledger = await this.load();
    const running = Object.values(ledger.locks).map((lock) => lock.run_id);
    const sha = Object.values(ledger.runs).map((run) => run.git_sha).find((value) => value && value !== "unknown") ?? "unknown";
    return { ok: true, service: "digiquant-runner", git_sha: sha, running };
  }
  async hasActiveWork() {
    const ledger = await this.load();
    return Object.keys(ledger.locks).length > 0 || ledger.queue.length > 0;
  }
  async accept(request) {
    const ledger = await this.load();
    const existingId = ledger.idem[request.idempotency_key];
    if (existingId) {
      return { ok: true, run_id: existingId, status: "duplicate" };
    }
    const held = ledger.locks[request.concurrency];
    if (held) {
      return { ok: true, run_id: held.run_id, status: "already_running" };
    }
    if (ledger.queue.some((id) => ledger.runs[id]?.concurrency === request.concurrency)) {
      const queued = ledger.queue.find(
        (id) => ledger.runs[id]?.concurrency === request.concurrency
      );
      return {
        ok: true,
        run_id: queued ?? request.idempotency_key,
        status: "already_running"
      };
    }
    const run = this.freshRun(request);
    ledger.idem[request.idempotency_key] = run.run_id;
    ledger.runs[run.run_id] = run;
    if (mustQueue(ledger, request.command)) {
      ledger.queue.push(run.run_id);
      await this.save(ledger);
      await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
      return { ok: true, run_id: run.run_id, status: "accepted" };
    }
    this.holdLock(ledger, run);
    await this.save(ledger);
    try {
      await this.deps.port.startRun({
        run_id: run.run_id,
        command: run.command,
        args: run.args,
        timeout_seconds: run.timeout_seconds
      });
    } catch (err) {
      await this.rollback(run.run_id);
      throw err;
    }
    try {
      const remote = await this.deps.port.readStatus(run.run_id);
      if (remote) {
        this.applyRemote(run, remote);
        await this.save(ledger);
      }
    } catch {
    }
    await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
    return { ok: true, run_id: run.run_id, status: "accepted" };
  }
  async alarm() {
    const ledger = await this.load();
    let reschedule = false;
    for (const group of Object.keys(ledger.locks)) {
      const keep = await this.pollLock(ledger, group);
      if (keep) reschedule = true;
    }
    reschedule = await this.promote(ledger) || reschedule;
    await this.save(ledger);
    if (reschedule || ledger.queue.length > 0 || Object.keys(ledger.locks).length > 0) {
      await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
    }
  }
  async getRun(runId) {
    const ledger = await this.load();
    const run = ledger.runs[runId];
    if (!run) return null;
    const lock = Object.values(ledger.locks).find((item) => item.run_id === runId);
    if (lock) {
      await this.pollLock(ledger, lock.concurrency);
      await this.save(ledger);
      return ledger.runs[runId] ?? run;
    }
    return run;
  }
  freshRun(request) {
    const now = this.now();
    return {
      run_id: crypto.randomUUID(),
      job_id: request.job_id,
      command: request.command,
      args: request.args,
      concurrency: request.concurrency,
      timeout_seconds: request.timeout_seconds,
      idempotency_key: request.idempotency_key,
      status: "accepted",
      exit_code: null,
      started_at: new Date(now).toISOString(),
      finished_at: null,
      git_sha: "unknown",
      log_tail: "",
      started_at_ms: now
    };
  }
  holdLock(ledger, run) {
    ledger.locks[run.concurrency] = {
      run_id: run.run_id,
      concurrency: run.concurrency,
      started_at_ms: run.started_at_ms,
      timeout_seconds: run.timeout_seconds
    };
    run.status = "running";
  }
  async pollLock(ledger, group) {
    const lock = ledger.locks[group];
    if (!lock) return false;
    const run = ledger.runs[lock.run_id];
    if (!run) {
      delete ledger.locks[group];
      return false;
    }
    let remote = null;
    try {
      remote = await this.deps.port.readStatus(lock.run_id);
    } catch {
      remote = null;
    }
    if (remote) {
      this.applyRemote(run, remote);
      if (remote.started_at) {
        const remoteMs = Date.parse(remote.started_at);
        if (!Number.isNaN(remoteMs) && remoteMs > 0) {
          lock.started_at_ms = remoteMs;
          run.started_at_ms = remoteMs;
        }
      }
    }
    const ageSeconds = (this.now() - lock.started_at_ms) / 1e3;
    const pastDeadline = ageSeconds > lock.timeout_seconds + WATCHDOG_GRACE_SECONDS;
    if (pastDeadline && !isTerminal(run.status)) {
      if (remote && !isTerminal(remote.status)) {
        return true;
      }
      run.status = "timed_out";
      run.exit_code = 124;
      run.finished_at = new Date(this.now()).toISOString();
      delete ledger.locks[group];
      return false;
    }
    if (!remote) return true;
    if (isTerminal(run.status)) {
      delete ledger.locks[group];
      if (run.command === "house-run" && run.status === "succeeded") {
        await this.onHouseSucceeded(ledger, run);
      }
      return false;
    }
    return true;
  }
  async onHouseSucceeded(ledger, run) {
    const runDate = run.args.run_date?.trim() ?? "";
    if (runDate && this.deps.archive) {
      const key = `pipeline-runs/house-run/${runDate}/success.json`;
      const body = JSON.stringify({
        run_id: run.run_id,
        finished_at: run.finished_at,
        git_sha: run.git_sha
      });
      try {
        await this.deps.archive.put(key, body);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error(`house_ledger_write_failed ${message}`);
      }
    }
    const idempotencyKey = `allocation-shadow:${run.run_id}`;
    if (ledger.idem[idempotencyKey]) return;
    const spec = COMMANDS["allocation-shadow"];
    if (!spec) return;
    const shadow = this.freshRun({
      job_id: "allocation-shadow",
      command: "allocation-shadow",
      args: {
        artifact_prefix: `pipeline-runs/house-run/${run.run_id}/`,
        source_branch: "main"
      },
      concurrency: spec.concurrency,
      timeout_seconds: spec.timeout_seconds,
      code_ref: "main",
      cron: "",
      scheduled_time: this.now(),
      idempotency_key: idempotencyKey
    });
    ledger.idem[idempotencyKey] = shadow.run_id;
    ledger.runs[shadow.run_id] = shadow;
    ledger.queue.push(shadow.run_id);
  }
  applyRemote(run, remote) {
    run.status = remote.status;
    run.exit_code = remote.exit_code;
    run.log_tail = remote.log_tail ?? "";
    if (remote.git_sha) run.git_sha = remote.git_sha;
    if (remote.started_at) run.started_at = remote.started_at;
    if (remote.finished_at) run.finished_at = remote.finished_at;
  }
  async promote(ledger) {
    let started = false;
    const waiting = [...ledger.queue];
    ledger.queue = [];
    for (const runId of waiting) {
      const run = ledger.runs[runId];
      if (!run) continue;
      if (ledger.locks[run.concurrency] || mustQueue(ledger, run.command)) {
        ledger.queue.push(runId);
        continue;
      }
      this.holdLock(ledger, run);
      try {
        await this.deps.port.startRun({
          run_id: run.run_id,
          command: run.command,
          args: run.args,
          timeout_seconds: run.timeout_seconds
        });
        started = true;
      } catch {
        delete ledger.locks[run.concurrency];
        run.status = "failed";
        run.finished_at = new Date(this.now()).toISOString();
      }
    }
    return started;
  }
  async rollback(runId) {
    const ledger = await this.load();
    const run = ledger.runs[runId];
    if (!run) return;
    delete ledger.locks[run.concurrency];
    delete ledger.runs[runId];
    delete ledger.idem[run.idempotency_key];
    ledger.queue = ledger.queue.filter((id) => id !== runId);
    await this.save(ledger);
  }
  async load() {
    const stored = await this.deps.kv.get(STATE_KEY);
    if (!stored) return emptyLedger();
    return {
      idem: stored.idem ?? {},
      locks: stored.locks ?? {},
      runs: stored.runs ?? {},
      queue: stored.queue ?? []
    };
  }
  async save(ledger) {
    await this.deps.kv.put(STATE_KEY, ledger);
  }
};
function publicRun(run) {
  return {
    run_id: run.run_id,
    job_id: run.job_id,
    status: run.status,
    exit_code: run.exit_code,
    started_at: run.started_at,
    finished_at: run.finished_at,
    git_sha: run.git_sha,
    log_tail: run.log_tail
  };
}
__name(publicRun, "publicRun");

// src/env.ts
function dataPlaneEnv(env) {
  return {
    R2_ACCOUNT_ID: env.R2_ACCOUNT_ID ?? "",
    R2_BUCKET: env.R2_BUCKET ?? "",
    R2_ACCESS_KEY_ID: env.R2_ACCESS_KEY_ID ?? "",
    R2_SECRET_ACCESS_KEY: env.R2_SECRET_ACCESS_KEY ?? "",
    CORE_POSTGRES_URI: env.CORE_POSTGRES_URI ?? "",
    CORE_SUPABASE_URL: env.CORE_SUPABASE_URL ?? "",
    CORE_SUPABASE_SERVICE_KEY: env.CORE_SUPABASE_SERVICE_KEY ?? "",
    CLOUDFLARE_EMAIL_API_TOKEN: env.CLOUDFLARE_EMAIL_API_TOKEN ?? "",
    CLOUDFLARE_ACCOUNT_ID: env.CLOUDFLARE_ACCOUNT_ID ?? "",
    NOTIFY_FROM: env.NOTIFY_FROM ?? "",
    DIGIQUANT_RUNNER_GIT_SHA: env.DIGIQUANT_RUNNER_GIT_SHA ?? "",
    DIGIQUANT_DIGIKEY_API_KEY: env.DIGIQUANT_DIGIKEY_API_KEY ?? "",
    OPENROUTER_API_KEY: env.OPENROUTER_API_KEY ?? "",
    CHEAPERINFERENCE_API_KEY: env.CHEAPERINFERENCE_API_KEY ?? "",
    CHEAPERINFERENCE_API_BASE: env.CHEAPERINFERENCE_API_BASE ?? "",
    LANGSMITH_API_KEY: env.LANGSMITH_API_KEY ?? ""
  };
}
__name(dataPlaneEnv, "dataPlaneEnv");

// src/runner.ts
var RUNNER_CONTAINER_ID = "runner-v1";
var DigiQuantRunnerContainer = class extends Container {
  static {
    __name(this, "DigiQuantRunnerContainer");
  }
  defaultPort = 8080;
  requiredPorts = [8080];
  /** Idle tail. Raised to 30m while a lock is held. */
  sleepAfter = "2m";
  enableInternet = true;
  async fetch(request) {
    this.envVars = dataPlaneEnv(this.env);
    const session = this.session();
    const response = await session.fetch(request);
    await this.applyActivityWindow(session);
    return response;
  }
  /** Alarm callback. Container.schedule names this method. */
  async heartbeat() {
    this.envVars = dataPlaneEnv(this.env);
    const session = this.session();
    await session.alarm();
    await this.applyActivityWindow(session);
  }
  async onActivityExpired() {
    if (await this.session().hasActiveWork()) {
      this.sleepAfter = "30m";
      this.renewActivityTimeout();
      return;
    }
    await super.onActivityExpired();
  }
  session() {
    return new RunnerSession({
      kv: kvFromStorage(this.ctx.storage),
      port: portFromContainer(this),
      archive: this.env.ARCHIVE,
      scheduleAlarm: /* @__PURE__ */ __name((delayMs) => {
        const seconds = Math.max(1, Math.round(delayMs / 1e3));
        return this.schedule(seconds, "heartbeat").then(() => void 0);
      }, "scheduleAlarm")
    });
  }
  async applyActivityWindow(session) {
    this.sleepAfter = await session.hasActiveWork() ? "30m" : "2m";
    this.renewActivityTimeout();
  }
};
function kvFromStorage(storage) {
  return {
    get: /* @__PURE__ */ __name((key) => storage.get(key), "get"),
    put: /* @__PURE__ */ __name((key, value) => storage.put(key, value), "put"),
    delete: /* @__PURE__ */ __name((key) => storage.delete(key), "delete")
  };
}
__name(kvFromStorage, "kvFromStorage");
function portFromContainer(container) {
  return {
    async startRun(body) {
      const res = await container.containerFetch("http://container/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body)
      });
      if (res.status === 400) {
        throw new Error("unknown command");
      }
      if (res.status === 409) {
        throw new Error("container /run HTTP 409 already_running");
      }
      if (res.status !== 202 && !res.ok) {
        throw new Error(`container /run HTTP ${res.status}`);
      }
    },
    async readStatus(runId) {
      const res = await container.containerFetch(
        `http://container/status?run_id=${encodeURIComponent(runId)}`
      );
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`container /status HTTP ${res.status}`);
      return res.json();
    }
  };
}
__name(portFromContainer, "portFromContainer");

// src/index.ts
function normalizePath(pathname) {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}
__name(normalizePath, "normalizePath");
function authorized(request, env) {
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) return false;
  return (request.headers.get("Authorization") ?? "") === `Bearer ${token}`;
}
__name(authorized, "authorized");
function argsOf(parsed) {
  if (typeof parsed !== "object" || parsed === null || !("args" in parsed)) return {};
  const args = parsed.args;
  if (typeof args !== "object" || args === null || Array.isArray(args)) return {};
  return args;
}
__name(argsOf, "argsOf");
async function houseRunGate(parsed, env) {
  if (!env.ARCHIVE) {
    return Response.json({ error: "house_ledger_unconfigured" }, { status: 500 });
  }
  const args = argsOf(parsed);
  if (args.force === "true") return null;
  const runDate = args.run_date;
  if (typeof runDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(runDate)) return null;
  const key = `pipeline-runs/house-run/${runDate}/success.json`;
  let hit;
  try {
    hit = await env.ARCHIVE.head(key);
  } catch {
    return Response.json({ error: "house_ledger_read_failed" }, { status: 500 });
  }
  if (!hit) return null;
  let runId = "";
  try {
    const object = await env.ARCHIVE.get(key);
    if (object) {
      const text = await object.text();
      const body = JSON.parse(text);
      if (typeof body === "object" && body !== null && "run_id" in body) {
        const value = body.run_id;
        if (typeof value === "string") runId = value;
      }
    }
  } catch {
    runId = "";
  }
  console.log("skipped: house_already_succeeded");
  return Response.json({ ok: true, run_id: runId, status: "skipped" }, { status: 202 });
}
__name(houseRunGate, "houseRunGate");
function stub(env) {
  const binding = env.RUNNER_CONTAINER;
  return getContainer(binding, RUNNER_CONTAINER_ID);
}
__name(stub, "stub");
var src_default = {
  async fetch(request, env) {
    const path = normalizePath(new URL(request.url).pathname);
    if (request.method === "GET" && path === "/healthz") {
      return stub(env).fetch(request);
    }
    if (!path.startsWith("/v1/jobs")) {
      return new Response("Not Found", { status: 404 });
    }
    if (!authorized(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }
    if (request.method === "POST" && path === "/v1/jobs") {
      const raw = await request.text();
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      const command = typeof parsed === "object" && parsed !== null && "command" in parsed ? parsed.command : void 0;
      if (typeof command !== "string") {
        return Response.json({ error: "invalid_body" }, { status: 400 });
      }
      try {
        assertKnownCommand(command, COMMANDS);
      } catch (err) {
        const message = err instanceof Error ? err.message : "unknown command";
        return Response.json({ error: message }, { status: 400 });
      }
      if (command === "house-run") {
        const gated = await houseRunGate(parsed, env);
        if (gated) return gated;
      }
      return stub(env).fetch(
        new Request(request.url, { method: "POST", headers: request.headers, body: raw })
      );
    }
    if (request.method === "GET") {
      return stub(env).fetch(request);
    }
    return new Response("Not Found", { status: 404 });
  }
};

// ../../node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// .wrangler/tmp/bundle-kvUWKO/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default
];
var middleware_insertion_facade_default = src_default;

// ../../node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-kvUWKO/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  scheduledTime;
  cron;
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  DigiQuantRunnerContainer,
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
