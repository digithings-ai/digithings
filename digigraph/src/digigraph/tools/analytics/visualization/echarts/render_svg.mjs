#!/usr/bin/env node
/**
 * ECharts option → SVG (SSR). Reads option JSON from stdin, writes SVG to stdout.
 * Usage: node render_svg.mjs [width] [height]
 * Defaults: 800 x 500. Requires: npm install echarts (in this directory).
 */
const width = parseInt(process.argv[2], 10) || 800;
const height = parseInt(process.argv[3], 10) || 500;

async function main() {
  const chunks = [];
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) chunks.push(chunk);
  const json = chunks.join('');
  const option = JSON.parse(json);
  const echarts = await import('echarts');
  const chart = echarts.init(null, null, {
    renderer: 'svg',
    ssr: true,
    width,
    height,
  });
  chart.setOption(option);
  const svgStr = chart.renderToSVGString();
  chart.dispose();
  process.stdout.write(svgStr, 'utf8');
}

main().catch((err) => {
  console.error('echarts-render-svg:', err.message);
  process.exit(1);
});
