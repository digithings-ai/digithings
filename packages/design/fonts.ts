import { Geist_Mono } from "next/font/google";

/**
 * The one font loader. Each app re-exports `fontVariables` and puts that
 * class on `<html>`. Geist Mono is the face (Chris, 14 Oct 2026). next/font
 * self-hosts the file at build time, so no request leaves for a font host.
 */
export const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

/** The class a root layout puts on `<html>`. */
export const fontVariables = mono.variable;
