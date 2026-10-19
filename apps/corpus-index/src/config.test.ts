import { describe, expect, it } from "vitest";
import { parseJob, parseJobs } from "./config";

const job = {
  id: "helpdesk",
  zammadBaseUrl: "https://support.example",
  siteUrl: "https://help.example/docs",
  helpIndex: "help-m3",
  ticketsIndex: "tickets-m3",
};

describe("parseJob", () => {
  it("keeps https origins and defaults skipInternal to true", () => {
    expect(parseJob(job)).toEqual({
      ...job,
      zammadBaseUrl: "https://support.example",
      siteUrl: "https://help.example",
      skipInternal: true,
    });
  });

  it("rejects tokens, http and userinfo", () => {
    expect(() => parseJob({ ...job, token: "present" })).toThrow("config_secret");
    expect(() => parseJob({ ...job, zammadBaseUrl: "http://support.example" })).toThrow(
      "config_zammadBaseUrl",
    );
    expect(() =>
      parseJob({ ...job, siteUrl: "https://user:pass@help.example" }),
    ).toThrow("config_siteUrl");
  });

  it("parses a KV job list", () => {
    expect(parseJobs(JSON.stringify([job]))).toHaveLength(1);
    expect(() => parseJobs("{")).toThrow("config_jobs");
  });
});
