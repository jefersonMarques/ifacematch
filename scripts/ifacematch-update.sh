#!/usr/bin/env bash
# Atualizador Customer Hosted: obtenção via GitHub Releases e ativação assinada.
set -euo pipefail
set +x
umask 077

release_version=0.1.11
archive_name=ifacematch-0.1.11-ubuntu-amd64.tar.gz
expected_archive_sha256=4a44480bc5fe340ae1c26405284599560325807ac88c8c0daab8a645df10dc32
release_url="https://github.com/jefersonMarques/ifacematch/releases/download/v0.1.11/ifacematch-0.1.11-ubuntu-amd64.tar.gz"
cache_dir="/var/cache/ifacematch/releases/0.1.11"
archive_path="$cache_dir/$archive_name"

if [[ "$(id -u)" != 0 ]]; then
    echo '[BLOCK] Run as root on the Customer Hosted server.' >&2
    exit 1
fi

if [[ "$#" != 1 || ( "$1" != "$release_version" && "$1" != "--check" ) ]]; then
    echo "Usage: bash ifacematch-update.sh $release_version | --check" >&2
    exit 2
fi

update_mode="$1"

if [[ "$(hostname -s)" != srv855672 ]]; then
    echo '[BLOCK] This 0.1.11 upgrade is authorized only for the first pilot host.' >&2
    exit 1
fi

for tool in curl sha256sum stat mktemp; do
    if ! command -v "$tool" >/dev/null; then
        echo "[BLOCK] Missing dependency: $tool" >&2
        exit 1
    fi
done

if [[ -e "$cache_dir" ]]; then
    [[ -d "$cache_dir" && ! -L "$cache_dir" &&
       "$(stat -c '%u' "$cache_dir")" == 0 &&
       "$(stat -c '%a' "$cache_dir")" == 700 ]] || {
        echo '[BLOCK] Release cache ownership or permissions are unsafe.' >&2
        exit 1
    }
else
    install -d -m 0700 -o root -g root "$cache_dir"
fi

if [[ ! -e "$archive_path" && ! -L "$archive_path" ]]; then
    temporary_archive="$(mktemp "$cache_dir/.incoming-XXXXXXXX")"
    if ! curl --fail --location --silent --show-error --retry 3 \
        --connect-timeout 10 --max-time 600 \
        --output "$temporary_archive" "$release_url"; then
        rm -f -- "$temporary_archive"
        echo '[BLOCK] Cannot download the published release.' >&2
        exit 1
    fi
    if ! printf '%s  %s\n' "$expected_archive_sha256" "$temporary_archive" |
        sha256sum --check --status; then
        rm -f -- "$temporary_archive"
        echo '[BLOCK] GitHub release SHA-256 does not match the approved build.' >&2
        exit 1
    fi
    chmod 0600 "$temporary_archive"
    if ! mv --no-clobber -- "$temporary_archive" "$archive_path"; then
        rm -f -- "$temporary_archive"
        echo '[BLOCK] Release cache appeared concurrently.' >&2
        exit 1
    fi
fi

[[ -f "$archive_path" && ! -L "$archive_path" &&
   "$(stat -c '%u' "$archive_path")" == 0 ]] || {
    echo '[BLOCK] Cached release is not a root-owned regular file.' >&2
    exit 1
}
printf '%s  %s\n' "$expected_archive_sha256" "$archive_path" |
    sha256sum --check --status || {
        echo '[BLOCK] Cached release SHA-256 mismatch.' >&2
        exit 1
    }

echo "[PASS] Published signed release $release_version: SHA-256 verified."

if [[ "$update_mode" == "--check" ]]; then
    echo '[PASS] Download/read-only preflight completed; no services modified.'
    exit 0
fi

set -- "$archive_path" "$expected_archive_sha256"

set -euo pipefail
set +x
umask 077

fail() {
    printf '[BLOCK] %s\n' "$*" >&2
    exit 1
}

[[ "$#" == 2 ]] ||
    fail 'Usage: apply-signed-console-login-0.1.11.sh <absolute-signed-archive> <expected-sha256>'
[[ "$(id -u)" == 0 ]] || fail 'Customer application requires root.'
[[ "$(hostname -s)" == srv855672 ]] ||
    fail 'This procedure is pinned to the first Customer Hosted pilot host.'

archive="$1"
expected_sha="$2"
old_version=0.1.10
new_version=0.1.11
old_root=/opt/ifacematch/releases/0.1.10
new_root=/opt/ifacematch/releases/0.1.11
cli="$old_root/bin/ifacematchctl"
trust=/etc/ifacematch/distribution.public
trust_id=/etc/ifacematch/distribution-key-id
unit=/etc/systemd/system/ifacematch-console.service
service=ifacematch-console.service
server=ifacematch-server.service

[[ "$archive" == /* && -s "$archive" && -f "$archive" && ! -L "$archive" ]] ||
    fail 'Signed archive must be a regular absolute file.'
[[ "$expected_sha" =~ ^[a-f0-9]{64}$ ]] ||
    fail 'Expected release SHA-256 must contain 64 lowercase hex characters.'
printf '%s  %s\n' "$expected_sha" "$archive" | sha256sum -c --status ||
    fail 'Signed release SHA-256 mismatch.'
[[ -x "$cli" && -s "$trust" && -f "$trust_id" &&
   -s "$old_root/ifacematch-release.json" &&
   -s "$old_root/ifacematch-release.sig" &&
   -s /var/lib/ifacematch/installation/license.json ]] ||
    fail 'Existing signed installation, trust or license missing.'
[[ ! -e "$new_root" && ! -e /var/lib/ifacematch/unit-plans/0.1.11 ]] ||
    fail 'Signed target release already exists; refusing to overwrite it.'
[[ -f "$unit" && ! -L "$unit" ]] ||
    fail 'Customer Console systemd unit is missing or linked.'
[[ "$(tr -d '\r\n' < "$trust_id")" == ifm_distribution_prod_v1 ]] ||
    fail 'Unexpected installed distribution trust identifier.'
[[ "$(systemctl show "$service" --property=FragmentPath --value)" == "$unit" ]] ||
    fail 'Active Console unit path differs from expected production path.'
[[ -z "$(systemctl show "$service" --property=DropInPaths --value)" ]] ||
    fail 'Console has existing systemd overrides requiring manual review.'

systemctl is-active --quiet "$service" ||
    fail 'Console is not active before the upgrade.'
systemctl is-active --quiet "$server" ||
    fail 'Biometric Server is not healthy before the upgrade.'

old_exec="ExecStart=$old_root/console/ifacematch-console"
new_exec="ExecStart=$new_root/console/ifacematch-console"
[[ "$(grep -Fxc "$old_exec" "$unit")" == 1 ]] ||
    fail 'Active Console executable does not match signed 0.1.10.'

exec 9>/run/lock/ifacematch-console-upgrade.lock
flock --nonblock 9 || fail 'Another Console upgrade is in progress.'

scratch="$(mktemp -d /var/tmp/ifacematch-console-011.XXXXXXXX)"
backup=''
changed=no

on_exit() {
    result="$?"
    trap - EXIT

    if [[ "$result" != 0 && "$changed" == yes && -n "$backup" ]]; then
        echo '[ROLLBACK] Restoring the previous signed Console service unit'
        cp -a -- "$backup/ifacematch-console.service" "$unit"
        systemctl daemon-reload || true
        systemctl restart "$service" || true
        if systemctl is-active --quiet "$service"; then
            echo '[ROLLBACK PASS] Previous Console service restored'
        else
            echo '[ROLLBACK ALERT] Console requires manual inspection' >&2
        fi
    fi

    rm -rf -- "$scratch"
    exit "$result"
}
trap on_exit EXIT

mkdir -m 0700 "$scratch/release"

echo '[1/5] Extracting archive without links or unsafe paths'
python3 - "$archive" "$scratch/release" <<'PY'
import shutil
import sys
import tarfile
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
with tarfile.open(source, "r:gz") as archive:
    members = archive.getmembers()
    if len(members) < 9 or len(members) > 1002:
        raise SystemExit("[BLOCK] Unexpected signed archive inventory")
    if any(not member.isfile() for member in members):
        raise SystemExit("[BLOCK] Archive contains non-regular members")
    names = [member.name for member in members]
    if len(names) != len(set(names)):
        raise SystemExit("[BLOCK] Duplicate signed archive members")

    for member in members:
        parts = member.name.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise SystemExit("[BLOCK] Unsafe signed archive path")
        if len(parts) == 1:
            if member.name not in {"ifacematch-release.json", "ifacematch-release.sig"}:
                raise SystemExit("[BLOCK] Unexpected root artifact")
        elif parts[0] not in {"bin", "server", "console", "lib", "model-pack", "sdk-web"}:
            raise SystemExit("[BLOCK] Unexpected release artifact")

        target = destination.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        contents = archive.extractfile(member)
        if contents is None:
            raise SystemExit("[BLOCK] Signed archive entry unavailable")
        with target.open("xb") as output:
            shutil.copyfileobj(contents, output)
        target.chmod(0o600)

for filename in ("bin/ifacematchctl", "server/ifacematch-server", "console/ifacematch-console"):
    (destination / filename).chmod(0o700)
PY

echo '[2/5] Verifying both complete releases with pinned Ed25519 trust'
for release_dir in "$old_root" "$scratch/release"; do
    "$cli" install --dry-run \
        --release-dir "$release_dir" \
        --trust-public-key-file "$trust" \
        --trust-key-id ifm_distribution_prod_v1
done

python3 - "$old_root/ifacematch-release.json" "$scratch/release/ifacematch-release.json" <<'PY'
import json
import sys
from pathlib import Path

before, after = [json.loads(Path(name).read_text(encoding="utf-8")) for name in sys.argv[1:]]
if before["releaseVersion"] != "0.1.10" or after["releaseVersion"] != "0.1.11":
    raise SystemExit("[BLOCK] Unexpected release version transition")
before_files = {entry["path"]: entry["sha256"] for entry in before["files"]}
after_files = {entry["path"]: entry["sha256"] for entry in after["files"]}
modified = {name for name in before_files if before_files[name] != after_files.get(name)}
allowed = {"console/ifacematch-console", "console/BUILD_PROVENANCE.txt"}

if before_files.keys() != after_files.keys() or not modified.issubset(allowed):
    raise SystemExit("[BLOCK] Candidate would modify non-Console components")
if "console/ifacematch-console" not in modified:
    raise SystemExit("[BLOCK] Candidate contains no Console binary update")
if after["components"]["console"] != "0.1.11":
    raise SystemExit("[BLOCK] Console version is not 0.1.11")
for key in ("server", "secureCore", "modelPack", "webSdk"):
    if before["components"][key] != after["components"][key]:
        raise SystemExit("[BLOCK] Candidate changes an unrelated component version")
print("[PASS] Signed release is limited to the Console executable and its provenance")
PY

echo '[3/5] Staging the new verified signed release without activation'
"$cli" install --apply \
    --release-dir "$scratch/release" \
    --trust-public-key-file "$trust" \
    --trust-key-id ifm_distribution_prod_v1 \
    --target-root /opt/ifacematch/releases \
    --units-root /var/lib/ifacematch/unit-plans \
    --service-user ifacematch \
    --service-group ifacematch \
    --confirm-release "$new_version"

echo '[4/5] Backing up and switching only the Console systemd unit'
backup="$(mktemp -d /etc/ifacematch/console-upgrade-backup-XXXXXXXX)"
cp -a -- "$unit" "$backup/ifacematch-console.service"
temporary="$(mktemp /etc/systemd/system/.ifacematch-console-XXXXXXXX)"

python3 - "$unit" "$temporary" "$old_exec" "$new_exec" <<'PY'
from pathlib import Path
import sys

original = Path(sys.argv[1]).read_text(encoding="utf-8")
old = sys.argv[3]
new = sys.argv[4]
if original.splitlines().count(old) != 1:
    raise SystemExit("[BLOCK] Original Console executable changed")
updated = "\n".join(new if line == old else line for line in original.splitlines()) + "\n"
destination = Path(sys.argv[2])
destination.write_text(updated, encoding="utf-8")
PY

chmod --reference="$unit" "$temporary"
chown --reference="$unit" "$temporary"
cmp -s "$unit" "$backup/ifacematch-console.service" ||
    fail 'Original unit changed during preparation.'
changed=yes
mv -fT -- "$temporary" "$unit"
systemctl daemon-reload
systemctl restart "$service"
systemctl is-active --quiet "$service" ||
    fail 'Updated Console failed to start.'

echo '[5/5] Checking CSRF stability and unchanged biometric Server'
python3 - /etc/ifacematch/console.env <<'PY'
import http.client
import http.cookies
import re
import sys
import time
import urllib.parse
from pathlib import Path

settings = Path(sys.argv[1]).read_text(encoding="utf-8")
values = {}
for line in settings.splitlines():
    if line.startswith("IFACEMATCH_CONSOLE_PUBLIC_ORIGIN="):
        values["origin"] = line.partition("=")[2].strip().strip('"')
origin = urllib.parse.urlsplit(values.get("origin", ""))
if origin.scheme not in ("http", "https") or not origin.netloc:
    raise SystemExit("[BLOCK] Console public origin unavailable")

def request(path, method="GET", cookie="", body=""):
    connection = http.client.HTTPConnection("127.0.0.1", 8081, timeout=5)
    headers = {"Host": origin.netloc}
    if cookie:
        headers["Cookie"] = "ifacematch_login_nonce=" + cookie
    if method == "POST":
        headers["Origin"] = origin.scheme + "://" + origin.netloc
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    status = response.status
    response_headers = dict(response.getheaders())
    payload = response.read().decode("utf-8", errors="replace")
    connection.close()
    return status, response_headers, payload

for attempt in range(10):
    try:
        status, headers, page = request("/login")
        if status == 200:
            break
    except OSError:
        pass
    time.sleep(1)
else:
    raise SystemExit("[BLOCK] Updated Console failed to serve /login")

pattern = re.compile(r'name="csrf" value="([^"]+)"')
first = pattern.search(page)
cookie_header = headers.get("Set-Cookie", "")
cookies = http.cookies.SimpleCookie()
cookies.load(cookie_header)
nonce = cookies.get("ifacematch_login_nonce")
if first is None or nonce is None or nonce.value != first.group(1):
    raise SystemExit("[BLOCK] Initial login cookie/form mismatch")

status, headers, second_page = request("/login", cookie=nonce.value)
second = pattern.search(second_page)
if status != 200 or second is None or second.group(1) != first.group(1):
    raise SystemExit("[BLOCK] Repeated GET changed the CSRF token")
if "ifacematch_login_nonce=" in headers.get("Set-Cookie", ""):
    raise SystemExit("[BLOCK] Repeated GET replaced the CSRF cookie")

favicon_status, favicon_headers, _ = request("/favicon.ico")
if favicon_status != 204 or "Set-Cookie" in favicon_headers:
    raise SystemExit("[BLOCK] Favicon generates a redirect or CSRF cookie")

rejected_status, _, _ = request(
    "/login",
    method="POST",
    cookie=nonce.value,
    body="csrf=invalid",
)
if rejected_status != 403:
    raise SystemExit("[BLOCK] Invalid CSRF was not rejected")

print("[PASS] HTTP login CSRF remains valid across repeated requests")
print("[PASS] Invalid CSRF is still rejected")
print("[PASS] Favicon does not rotate the login token")
PY

systemctl is-active --quiet "$server" ||
    fail 'Biometric Server changed state during Console update.'
[[ "$(grep -Fxc "$new_exec" "$unit")" == 1 ]] ||
    fail 'Active Console service is not pinned to the signed 0.1.11 release.'

changed=no
echo '[PASS] Signed Console 0.1.11 active; Server, database and license unchanged.'
echo "[BACKUP] $backup"
echo '[NOTE] Keep the previous release and backup for rollback.'
