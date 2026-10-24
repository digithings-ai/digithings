// CSS module declarations — side-effect imports (e.g. `import './globals.css'`)
declare module '*.css' {
  const content: Record<string, string>;
  export default content;
}

declare module '@digithings/design/starfield.js' {
  export function initStarfield(options?: {
    canvasId?: string;
    density?: number;
    theme?: 'dark' | 'auto';
  }): { stop(): void };
}
