import { describe, expect, it } from "vitest";
import { buildRuntimeUrl, buildEditorUrl } from "./appLinks";

describe("appLinks", () => {
  it("builds a runtime URL with the app id", () => {
    expect(buildRuntimeUrl("a1", "https://oi.example:8090")).toBe(
      "https://oi.example:8090/app/?app=a1",
    );
  });

  it("builds an editor URL with the app id", () => {
    expect(buildEditorUrl("a1", "https://oi.example:8090")).toBe(
      "https://oi.example:8090/views?app=a1",
    );
  });

  it("trims a trailing slash from the origin", () => {
    expect(buildRuntimeUrl("x", "http://host/")).toBe("http://host/app/?app=x");
  });

  it("falls back to the root when no app id", () => {
    expect(buildRuntimeUrl(null, "http://host")).toBe("http://host/app/");
    expect(buildEditorUrl(undefined, "http://host")).toBe("http://host/");
  });
});
