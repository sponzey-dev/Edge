const CANDIDATE_IMAGE = /^ghcr\.io\/sponzey-lab\/sponzey-edge:(v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))@sha256:([0-9a-f]{64})$/;

export function isCandidateImage(image) {
  return typeof image === "string" && CANDIDATE_IMAGE.test(image);
}

/** Compare an explicit digest's Docker inspection and the running container. */
export function validateCandidateImage(image, commit, inspection, containerImageId = null) {
  const match = typeof image === "string" && CANDIDATE_IMAGE.exec(image);
  if (!match || !/^[0-9a-f]{40}$/.test(commit)) throw new Error("invalid candidate image provenance");
  const labels = inspection?.Config?.Labels;
  const imageId = inspection?.Id;
  const digest = `ghcr.io/sponzey-lab/sponzey-edge@sha256:${match[2]}`;
  if (!/^sha256:[0-9a-f]{64}$/.test(imageId ?? "") || !inspection.RepoDigests?.includes(digest)
      || labels?.["org.opencontainers.image.revision"] !== commit
      || labels?.["org.opencontainers.image.version"] !== match[1]
      || (containerImageId !== null && containerImageId !== imageId)) {
    throw new Error("candidate image provenance mismatch");
  }
  return { image, image_id: imageId, revision: commit, version: match[1], container_image_id: containerImageId, repo_digest: digest };
}

/** Recheck the recorded, secret-free Docker facts without contacting a registry. */
export function validateRecordedCandidate(metadata) {
  const proof = metadata?.candidate_provenance;
  if (!proof || proof.image !== metadata.candidate_image || proof.image_id !== metadata.edge_image_id
      || typeof proof.container_image_id !== "string" || proof.container_image_id !== metadata.edge_image_id) {
    throw new Error("candidate image provenance is missing or inconsistent");
  }
  const inspected = {
    Id: proof.image_id,
    RepoDigests: [proof.repo_digest],
    Config: { Labels: { "org.opencontainers.image.revision": proof.revision, "org.opencontainers.image.version": proof.version } },
  };
  validateCandidateImage(proof.image, metadata.source_commit, inspected, proof.container_image_id);
  if (!/^[0-9a-f]{40}$/.test(metadata.source_tree ?? "") || !/^[0-9a-f]{64}$/.test(metadata.config_sha256 ?? "")) {
    throw new Error("candidate source provenance is incomplete");
  }
}
