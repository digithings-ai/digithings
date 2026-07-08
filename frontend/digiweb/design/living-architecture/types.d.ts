// Type hints for the living-architecture primitive.

export interface DiagramNode {
  id: string;
  label: string;
  x: number;
  y: number;
  /** CSS custom-property name, e.g. "--accent-digigraph". */
  accentVar?: string;
  /** Arrow-left/right nav cycles nodes where group === "core". */
  group?: "core" | string;
}

export interface DiagramEdge {
  source: string;
  target: string;
}

export interface CameraAPI {
  focus(nodeId: string): void;
  reset(): void;
  /** viewBox tuple: [x, y, width, height]. */
  zoomTo(bbox: [number, number, number, number]): void;
}

export interface DiagramHandle {
  camera: CameraAPI;
  focus(nodeId: string): void;
  reset(): void;
  destroy(): void;
}

export interface InitDiagramOptions {
  hostId: string;
  svgId: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  onNodeFocus?: (nodeId: string) => void;
}

export function initDiagram(opts: InitDiagramOptions): DiagramHandle;
