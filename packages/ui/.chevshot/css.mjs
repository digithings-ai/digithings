import postcss from "postcss"; import tw from "@tailwindcss/postcss"; import { readFileSync, writeFileSync } from "node:fs";
const from = new URL("./in.css", import.meta.url).pathname;
const out = await postcss([tw()]).process(readFileSync(from, "utf8"), { from });
writeFileSync(new URL("./out.css", import.meta.url).pathname, out.css); console.log("css", out.css.length);
