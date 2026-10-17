// @vitest-environment node
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { canonicalBody } from "./canonical";
import { loadRecordings, recordingsDir, sha256 } from "./load";

const committed = loadRecordings(join(__dirname, "../../../../../recordings"));

describe("committed recordings", () => {
  it("all pass the site's checks, including the exporter's sha256", () => {
    expect(committed.rejected).toEqual([]);
    expect(committed.recordings.length).toBeGreaterThan(0);
    for (const recording of committed.recordings) {
      expect(recording.data.provenance.synthetic).toBe(false);
      expect(recording.data.provenance.evidence_level).toBe("unclassified");
    }
  });
});

describe("canonicalBody", () => {
  it("keeps number lexemes and sorts keys like the Python exporter", () => {
    const text = '{"b": 1.0, "a": [10, 2.50, -0.0], "integrity": {"x": 1}, "c": "é\\u001f"}';
    expect(canonicalBody(text)).toBe('{"a":[10,2.50,-0.0],"b":1.0,"c":"é\\u001f"}');
  });

  it("rejects duplicate keys and trailing content", () => {
    expect(() => canonicalBody('{"a":1,"a":2}')).toThrow(/duplicate/);
    expect(() => canonicalBody('{"a":1} x')).toThrow(/trailing/);
  });
});

describe("loadRecordings", () => {
  const source = committed.recordings[0];
  const original = readFileSync(join(__dirname, "../../../../../recordings", source.file), "utf8");

  function dirWith(files: Record<string, string>): string {
    const dir = mkdtempSync(join(tmpdir(), "recordings-"));
    for (const [name, text] of Object.entries(files)) writeFileSync(join(dir, name), text);
    return dir;
  }

  it("rejects a tampered file and never returns it", () => {
    const tampered = original.replace('"evidence_category": "development_run"', '"evidence_category": "controlled_research"');
    expect(tampered).not.toBe(original);
    const result = loadRecordings(dirWith({ [source.file]: tampered }));
    expect(result.recordings).toEqual([]);
    expect(result.rejected).toEqual([{ file: source.file, reason: "integrity hash does not match the content" }]);
  });

  it("rejects unsupported schemas, wrong names, synthetic data and broken JSON", () => {
    const doc = JSON.parse(original);
    const resign = (value: Record<string, unknown>) => {
      const text = JSON.stringify(value, null, 2);
      const withHash = { ...value, integrity: { ...doc.integrity, content_sha256: sha256(canonicalBody(text)) } };
      return JSON.stringify(withHash, null, 2);
    };
    const result = loadRecordings(
      dirWith({
        "a.json": JSON.stringify({ ...doc, schema: "autoresilience-recording/9" }),
        "b.json": original,
        [`${doc.recording_id}.json`]: resign({ ...doc, provenance: { ...doc.provenance, synthetic: true } }),
        "d.json": "{not json",
      }),
    );
    expect(result.recordings).toEqual([]);
    expect(Object.fromEntries(result.rejected.map((r) => [r.file, r.reason]))).toEqual({
      "a.json": 'unsupported schema "autoresilience-recording/9"',
      "b.json": "file name does not match recording_id",
      [`${doc.recording_id}.json`]: "synthetic or unlabelled evidence is never published",
      "d.json": expect.stringMatching(/^not valid JSON/),
    });
  });

  it("treats a missing directory as no recordings", () => {
    expect(loadRecordings(join(tmpdir(), "does-not-exist-recordings"))).toEqual({ recordings: [], rejected: [] });
    expect(recordingsDir()).toMatch(/recordings$/);
  });
});
