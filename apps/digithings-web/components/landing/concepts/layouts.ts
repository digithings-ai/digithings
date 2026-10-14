import type { EmbeddingLayout } from "./embedding-field";

export type LayoutInfo = { slug: EmbeddingLayout; name: string; note: string };

export const LAYOUTS: LayoutInfo[] = [
  {
    slug: "continents",
    name: "A · Continents",
    note: "A handful of large clusters hugging the edges, a few small islands between them. Closest to the world map's weight and rhythm.",
  },
  {
    slug: "scatter",
    name: "B · Scatter",
    note: "Sixteen smaller topic islands and more stray points, like a t-SNE plot of a big knowledge base. Busier and more obviously data.",
  },
  {
    slug: "drift",
    name: "C · Drift",
    note: "The continents layout, but the clusters slowly shift and breathe as if the index is being rebuilt. The most alive, and the most motion.",
  },
];
