import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import { describeError } from "./errors";

const fallback = "The note was not sent. Try again.";

describe("describeError", () => {
  it("explains username_taken", () => {
    expect(describeError(new ApiError(409, { error: "username_taken" }), { fallback })).toBe(
      "That username is taken. Choose another.",
    );
  });

  it("explains invalid_credentials without saying which part was wrong", () => {
    expect(describeError(new ApiError(401, { error: "invalid_credentials" }), { fallback })).toBe(
      "The username or password is incorrect.",
    );
  });

  it("explains not_logged_in", () => {
    expect(describeError(new ApiError(401, { error: "not_logged_in" }), { fallback })).toBe(
      "You are signed out, so this was not saved. Sign in again to continue.",
    );
  });

  it("explains authwho_unavailable", () => {
    expect(describeError(new ApiError(502, { error: "authwho_unavailable" }), { fallback })).toBe(
      "The identity check service is not responding, so this was not completed. Try again in a moment.",
    );
  });

  it("names the invalid fields by their labels for invalid_request", () => {
    const error = new ApiError(422, { error: "invalid_request", fields: ["username", "password"] });
    expect(describeError(error, { fallback, fields: { username: "Username", password: "Password" } })).toBe(
      "Check these fields and try again: Username, Password.",
    );
  });

  it("names a single invalid field", () => {
    const error = new ApiError(422, { error: "invalid_request", fields: ["account"] });
    expect(describeError(error, { fallback, fields: { account: "Account number" } })).toBe(
      "Check this field and try again: Account number.",
    );
  });

  it("makes unknown field names readable", () => {
    const error = new ApiError(422, { error: "invalid_request", fields: ["pointer_device"] });
    expect(describeError(error, { fallback })).toBe("Check this field and try again: Pointer device.");
  });

  it("explains invalid_request without fields", () => {
    expect(describeError(new ApiError(422, { error: "invalid_request" }), { fallback })).toBe(
      "Some details were not accepted. Check the form and try again.",
    );
  });

  it("uses the fallback for unknown codes and network failures", () => {
    expect(describeError(new ApiError(500, undefined), { fallback })).toBe(fallback);
    expect(describeError(new TypeError("Failed to fetch"), { fallback })).toBe(fallback);
  });
});
