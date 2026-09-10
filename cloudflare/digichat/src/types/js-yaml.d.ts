declare module "js-yaml" {
  export function load(str: string, opts?: object): unknown;
  export function dump(obj: unknown, opts?: object): string;
}
