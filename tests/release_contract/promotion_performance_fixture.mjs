import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { compareBaseline, summarizeK6, summarizeResources } from "../performance/bin/summary.mjs";

// Test-only raw profiles. Production evidence must come from real runs.
const [root, commit, image] = process.argv.slice(2);
const host = { kernel: "Linux", cpu_model: "fixture", cpu_governor: "performance", docker_version: "1", compose_version: "1" };
const history = ["Idle", "Readiness", "Warmup", "Running", "Cooldown", "Validating", "Published"];
const records = {};
for (const [name, profile, candidate] of [["c8_reference", "baseline", false], ["c8_candidate", "baseline", true], ["soak", "soak", true]]) {
  const directory = path.join(root, name);
  mkdirSync(directory, { recursive: true });
  const files = [];
  const write = (filename, value) => {
    writeFileSync(path.join(directory, filename), JSON.stringify(value));
    files.push(`${name}/${filename}`);
  };
  const metadata = {
    run_id: name, profile, source_commit: candidate ? commit : "3c1e8e95e854df724ab0ea21a271dcd42b97b061",
    source_tree: candidate ? "e".repeat(40) : "b2007971753908843855772fa8f7624011f7a784", edge_image_id: `sha256:${"f".repeat(64)}`,
    host_identity: host,
  };
  if (candidate) Object.assign(metadata, {
    config_sha256: "0bd42ccc14f224764ab913292ae131517a3998d80b2aca889fd83f19447761f4",
    measurement_mode: "published_candidate", candidate_image: image,
    candidate_provenance: {
      image, image_id: metadata.edge_image_id, container_image_id: metadata.edge_image_id,
      revision: commit, version: image.match(/:(v[^@]+)@/)[1],
      repo_digest: `ghcr.io/sponzey-lab/sponzey-edge@${image.split("@")[1]}`,
    },
  });
  write("metadata.json", metadata);
  write("state.json", { history });
  const raw = { metrics: {
    checks: { value: 1 }, http_req_failed: { value: 0 }, http_reqs: { rate: 100 },
    http_req_duration: { "p(50)": 2, "p(95)": 5, "p(99)": 9 },
    data_sent: { count: 10 }, data_received: { count: 20 },
  } };
  const runs = [];
  for (let i = 1; i <= (profile === "baseline" ? 3 : 1); i++) {
    write(`${profile}-${i}.json`, raw);
    runs.push(summarizeK6(raw, i));
  }
  const samples = [
    { sampled_at: "2026-09-07T00:00:00.000Z", cpu_percent: 1, memory_usage_bytes: 1000 },
    { sampled_at: profile === "soak" ? "2026-09-07T00:30:00.000Z" : "2026-09-07T00:00:01.000Z", cpu_percent: 2, memory_usage_bytes: 1001 },
  ];
  write("edge-resource-samples.json", samples);
  const summary = { profile, runs, resource_trend: summarizeResources(samples) };
  if (profile === "baseline") summary.baseline_comparison = compareBaseline(runs);
  write("summary.json", summary);
  records[name] = files;
}
process.stdout.write(JSON.stringify(records));
