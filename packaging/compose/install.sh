#!/bin/sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Compose upgrade helper install must run as root" >&2; exit 2; }
[ -x /usr/bin/python3 ] || { echo "Python 3 is unavailable" >&2; exit 2; }
[ "$#" -eq 6 ] && [ "$1" = "--image-tag" ] && [ "$3" = "--image-digest" ] && [ "$5" = "--release-manifest-file" ] || { echo "usage: install.sh --image-tag vMAJOR.MINOR.PATCH --image-digest SHA256 --release-manifest-file /absolute/path" >&2; exit 2; }
case "$2" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "invalid image tag" >&2; exit 2 ;; esac
digest=${4#sha256:}
[ "${#digest}" -eq 64 ] || { echo "invalid image digest" >&2; exit 2; }
case "$digest" in *[!0123456789abcdef]*|'') echo "invalid image digest" >&2; exit 2 ;; esac
case "$6" in /*) ;; *) echo "release manifest path must be absolute" >&2; exit 2 ;; esac
[ -f "$6" ] && [ ! -L "$6" ] || { echo "release manifest is missing or unsafe" >&2; exit 2; }
manifest_owner=$(stat -c %u "$6" 2>/dev/null || stat -f %u "$6") || { echo "cannot inspect release manifest owner" >&2; exit 2; }
[ "$manifest_owner" = 0 ] || { echo "release manifest is not root owned" >&2; exit 2; }
manifest_mode=$(stat -c %a "$6" 2>/dev/null || stat -f %Lp "$6") || { echo "cannot inspect release manifest mode" >&2; exit 2; }
[ $((0$manifest_mode & 022)) -eq 0 ] || { echo "release manifest is group or world writable" >&2; exit 2; }
[ -x /usr/bin/docker ] || { echo "Docker executable is unavailable" >&2; exit 2; }
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
image_config_verifier=$package_dir/verify-local-image-config.py
[ -f "$image_config_verifier" ] && [ ! -L "$image_config_verifier" ] || { echo "image config verifier is missing or unsafe" >&2; exit 2; }

image_reference="ghcr.io/sponzey-lab/sponzey-edge:$2@sha256:$digest"
local_image="ghcr.io/sponzey-lab/sponzey-edge:$2"
expected_config_digest=$(/usr/bin/python3 - "$6" "$2" "$image_reference" <<'PY'
import json
import re
import sys

path, version, image = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit("invalid release manifest")
if not isinstance(manifest, dict):
    raise SystemExit("invalid release manifest")
config_digest = manifest.get("image_config_digest")
if manifest.get("schema_version") != 1 or manifest.get("tag") != version or manifest.get("image") != image:
    raise SystemExit("release manifest image identity mismatch")
if not isinstance(config_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest) is None:
    raise SystemExit("release manifest config digest is invalid")
print(config_digest)
PY
) || { echo "release manifest does not match requested image identity" >&2; exit 2; }
image_platform=$(/usr/bin/docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image_reference") || { echo "cannot inspect pinned Compose image platform" >&2; exit 2; }
[ "$image_platform" = "linux/amd64" ] || { echo "Compose image must target linux/amd64" >&2; exit 2; }
image_version=$(/usr/bin/docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image_reference") || { echo "cannot inspect pinned Compose image version" >&2; exit 2; }
[ "$image_version" = "${2#v}" ] || { echo "pinned Compose image version mismatch" >&2; exit 2; }
image_revision=$(/usr/bin/docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image_reference") || { echo "cannot inspect pinned Compose image revision" >&2; exit 2; }
[ "${#image_revision}" -eq 40 ] || { echo "pinned Compose image revision is invalid" >&2; exit 2; }
case "$image_revision" in *[!0123456789abcdef]*|'') echo "pinned Compose image revision is invalid" >&2; exit 2 ;; esac
/usr/bin/docker image tag "$image_reference" "$local_image" || { echo "cannot assign local Compose image tag" >&2; exit 2; }
/usr/bin/python3 "$image_config_verifier" "$local_image" "$local_image" "$expected_config_digest" || { echo "local Compose image config digest mismatch" >&2; exit 2; }

release_root=$(dirname "$package_dir")
config_target=/etc/sponzey-edge/current.toml
install -d -o root -g root -m 0755 /etc/sponzey-edge/compose
install -d -o root -g root -m 0755 /usr/local/libexec/sponzey-edge
install -o root -g root -m 0644 "$package_dir/docker-compose.yml" /etc/sponzey-edge/compose/docker-compose.yml
install -o root -g root -m 0644 "$package_dir/docker-compose.upgrade.yml" /etc/sponzey-edge/compose/docker-compose.upgrade.yml
install -o root -g root -m 0644 "$image_config_verifier" /usr/local/libexec/sponzey-edge/verify-local-image-config.py
[ -e "$config_target" ] || install -o root -g root -m 0644 "$release_root/current.toml" "$config_target"
umask 077
printf 'SPONZEY_EDGE_TAG=%s\nSPONZEY_EDGE_DIGEST=%s\nSPONZEY_EDGE_IMAGE_CONFIG_DIGEST=%s\nSPONZEY_EDGE_LOCAL_IMAGE=%s\nSPONZEY_EDGE_IMAGE_REFERENCE=%s\n' \
  "$2" "$digest" "$expected_config_digest" "$local_image" "$image_reference" > /etc/sponzey-edge/compose/runtime.env.tmp
chmod 0644 /etc/sponzey-edge/compose/runtime.env.tmp
mv /etc/sponzey-edge/compose/runtime.env.tmp /etc/sponzey-edge/compose/runtime.env
install -o root -g root -m 0755 "$package_dir/compose-upgrade-helper" /usr/local/libexec/sponzey-edge/compose-upgrade-helper
