#!/usr/bin/env node
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { auditArtifact } from "../../tests/performance/bin/audit.mjs";
import { compareBaseline, evaluateC8Gate, summarizeK6, summarizeResources } from "../../tests/performance/bin/summary.mjs";

const REFERENCE = "3c1e8e95e854df724ab0ea21a271dcd42b97b061";
// The approved clean-source reference predates config_sha256 metadata. These
// values are the tree and config bytes of that exact immutable Git commit.
const REFERENCE_TREE = "b2007971753908843855772fa8f7624011f7a784";
const REFERENCE_CONFIG = "0bd42ccc14f224764ab913292ae131517a3998d80b2aca889fd83f19447761f4";
const [referenceDir, candidateDir, soakDir, commit, image] = process.argv.slice(2);
const read = (directory, name) => JSON.parse(readFileSync(path.join(directory, name), "utf8"));

function check(directory, profile, sourceCommit, publishedImage) {
  const audited = auditArtifact(directory);
  assert.equal(audited.profile, profile);
  assert.equal(audited.source_commit, sourceCommit);
  const metadata = read(directory, "metadata.json");
  assert.match(metadata.source_tree, /^[0-9a-f]{40}$/);
  if (sourceCommit === REFERENCE && !publishedImage) {
    assert.equal(metadata.source_tree, REFERENCE_TREE);
    if (metadata.config_sha256 !== undefined) assert.equal(metadata.config_sha256, REFERENCE_CONFIG);
  } else assert.match(metadata.config_sha256, /^[0-9a-f]{64}$/);
  if (publishedImage) {
    assert.equal(metadata.measurement_mode, "published_candidate");
    assert.equal(metadata.candidate_image, publishedImage);
  }
  const count = profile === "baseline" ? 3 : 1;
  const runs = Array.from({ length: count }, (_, index) => summarizeK6(read(directory, `${profile}-${index + 1}.json`), index + 1));
  const summary = read(directory, "summary.json");
  assert.deepEqual(summary.runs, runs);
  assert.deepEqual(summary.resource_trend, summarizeResources(read(directory, "edge-resource-samples.json")));
  if (profile === "baseline") assert.deepEqual(summary.baseline_comparison, compareBaseline(runs));
  if (profile === "soak") assert.ok(summary.resource_trend.elapsed_ms >= 1_800_000);
  return { metadata, summary };
}

try {
  const reference = check(referenceDir, "baseline", REFERENCE);
  const candidate = check(candidateDir, "baseline", commit, image);
  const soak = check(soakDir, "soak", commit, image);
  assert.deepEqual(reference.metadata.host_identity, candidate.metadata.host_identity);
  assert.deepEqual(candidate.metadata.host_identity, soak.metadata.host_identity);
  assert.equal(candidate.metadata.source_tree, soak.metadata.source_tree);
  assert.equal(candidate.metadata.edge_image_id, soak.metadata.edge_image_id);
  assert.equal(REFERENCE_CONFIG, candidate.metadata.config_sha256);
  assert.equal(candidate.metadata.config_sha256, soak.metadata.config_sha256);
  assert.equal(evaluateC8Gate(reference.summary.baseline_comparison, candidate.summary.baseline_comparison).passed, true);
  process.stdout.write('{"performance_valid":true}\n');
} catch {
  // No raw result, filesystem path, request data, or credential is printed.
  process.stderr.write("PROMOTION_PERFORMANCE_INVALID\n");
  process.exitCode = 2;
}
