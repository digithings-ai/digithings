/* ==========================================================================
   @digithings/design — app-shell-terminal/slash-commands
   --------------------------------------------------------------------------
   Registry + parser + dispatcher for slash commands. Used by the app shell's
   input bar and Cmd+K palette.
   ========================================================================== */

export class SlashCommandRegistry {
  constructor() {
    this._commands = new Map();
  }

  /** Register a command.
   *  @param {string} name — e.g. "help" (no leading slash).
   *  @param {{ description?: string, handler: (args: string[]) => unknown }} spec
   */
  register(name, spec) {
    if (!name || typeof name !== 'string') throw new Error('register: name required');
    if (!spec || typeof spec.handler !== 'function') throw new Error('register: handler required');
    const clean = name.replace(/^\//, '');
    this._commands.set(clean, {
      description: spec.description || '',
      handler: spec.handler,
    });
  }

  /** Unregister a command by name. */
  unregister(name) {
    this._commands.delete(name.replace(/^\//, ''));
  }

  /** List all commands for a palette. */
  list() {
    return Array.from(this._commands.entries()).map(([name, spec]) => ({
      name,
      description: spec.description,
    }));
  }

  /** Parse `/cmd arg1 arg2` → { name, args } or null if not a command. */
  parse(input) {
    if (typeof input !== 'string') return null;
    const trimmed = input.trim();
    if (!trimmed.startsWith('/')) return null;
    const parts = trimmed.slice(1).split(/\s+/);
    const name = parts.shift();
    if (!name) return null;
    return { name, args: parts };
  }

  /** Parse + invoke. Returns the handler's result, or undefined if no match. */
  dispatch(input) {
    const parsed = this.parse(input);
    if (!parsed) return undefined;
    const spec = this._commands.get(parsed.name);
    if (!spec) return undefined;
    return spec.handler(parsed.args);
  }
}
