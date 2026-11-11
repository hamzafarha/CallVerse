"""Put CallVerse online on Azure (works with Azure for Students).

One small Linux virtual machine builds and runs the same Docker container as the Hugging Face Space, behind
Caddy, which gets a free HTTPS certificate (needed for the microphone and for wss:// WebSockets).

Why a virtual machine: Azure for Students does not run cloud image builds (ACR Tasks), and pushing the
finished image (about 6 GB) over a slow connection would take hours. Here only the cleaned folder (about
120 MB, compressed) leaves your PC; the VM downloads the heavy parts (Python packages, bge-m3) itself.

Two ways to get the VM:
A. Nothing to install: create the VM in the Azure Portal (the settings are in docs/RUN_GUIDE.md, section 7),
   paste the public key printed by --public-key, then run the script with --host <the VM's DNS name>.
B. With the Azure CLI (az login): the script creates the VM itself.

    python scripts/deploy_azure.py --public-key                                   (A, once)
    python scripts/deploy_azure.py --host NAME.REGION.cloudapp.azure.com --send-openrouter-key   (A)
    python scripts/deploy_azure.py --send-openrouter-key                          (B)

What it does, in order. Steps already done are skipped, so running it again updates the app:
1. Builds and checks the cleaned folder (scripts/deploy_space.py: no .env, no private data, no secret).
2. (B only) Creates the resource group and the VM with a public name; opens ports 80 and 443.
3. Installs Docker on the VM if needed, sends the folder, builds the image there, (re)starts the app, and
   starts Caddy for HTTPS.
4. Waits until https://<name>.<region>.cloudapp.azure.com answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from deploy_space import MARKER, PROJECT_ROOT, build_staging

IMAGE = "Canonical:ubuntu-24_04-lts:server:latest"
ADMIN = "azureuser"
SSH_KEY = Path.home() / ".ssh" / "callverse_azure"  # a key for this VM only: your other keys are not touched
KNOWN_HOSTS = Path.home() / ".ssh" / "callverse_known_hosts"
SSH_HINT = "Windows: Settings > System > Optional features > add 'OpenSSH Client'."

# Commands run on the VM (bash), in order.
READY = (
    "cloud-init status --wait > /dev/null 2>&1;"  # the VM's first-boot setup must finish first (apt)
    " command -v docker > /dev/null || curl -fsSL https://get.docker.com | sudo sh > /dev/null;"
    " sudo docker version --format 'Docker {{.Server.Version}} is ready'"
)
UNPACK = (
    "rm -rf ~/callverse && mkdir ~/callverse"
    " && tar -xzf ~/callverse-app.tar.gz -C ~/callverse && rm ~/callverse-app.tar.gz"
)
BUILD = "cd ~/callverse && sudo docker build -t callverse ."
# The app listens on 127.0.0.1 only: visitors reach it through Caddy. Old images are removed (disk space).
RESTART_APP = (
    "sudo docker rm -f callverse > /dev/null 2>&1;"
    " sudo docker run -d --name callverse --restart unless-stopped -p 127.0.0.1:7860:7860"
    " --env-file ~/callverse.env callverse"
    " && sudo docker image prune -f > /dev/null"
)
# Caddy, the HTTPS front door: a Let's Encrypt certificate for the VM's name, and every request (WebSockets
# included) passed to the app. Started once; its certificates live in the caddy_data volume.
START_CADDY = (
    "sudo docker inspect caddy > /dev/null 2>&1 || sudo docker run -d --name caddy --restart unless-stopped"
    " --network host -v caddy_data:/data caddy:2 caddy reverse-proxy --from {host} --to localhost:7860"
)
LOGS = "sudo docker logs --tail 40 callverse; sudo docker logs --tail 15 caddy"


def run(command: list[str], *, capture: bool = False, check: bool = True) -> str:
    """Run a command (az, ssh-keygen). Its output is shown, or returned with capture=True."""
    result = subprocess.run(command, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        if capture:
            print(result.stderr.strip())
        sys.exit(f"Stopped: '{Path(command[0]).stem} {' '.join(command[1:3])}' failed.")
    return (result.stdout or "").strip() if capture and result.returncode == 0 else ""


def tool(name: str, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"'{name}' was not found. {hint}")
    return path


def ensure_key(key: Path) -> Path:
    """This VM's SSH key pair (made once with ssh-keygen, which comes with Windows)."""
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                tool("ssh-keygen", SSH_HINT),
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "callverse-azure",
                "-f",
                str(key),
            ]
        )
    return key


class Vm:
    """SSH and SCP to the VM, with this VM's own key and known-hosts file."""

    def __init__(self, host: str, key: Path) -> None:
        self.host = host
        self.ssh, self.scp = tool("ssh", SSH_HINT), tool("scp", SSH_HINT)
        self.options = ["-i", str(key), "-o", "IdentitiesOnly=yes"]
        for option in (f"UserKnownHostsFile={KNOWN_HOSTS}", "StrictHostKeyChecking=accept-new",
                       "ServerAliveInterval=30", "ConnectTimeout=15"):  # fmt: skip
            self.options += ["-o", option]

    def sh(self, script: str, *, check: bool = True, stdin: str | None = None) -> bool:
        """Run a bash command on the VM; its output appears here."""
        command = [self.ssh, *self.options, f"{ADMIN}@{self.host}", script]
        done = subprocess.run(command, input=stdin, text=True)
        if check and done.returncode != 0:
            sys.exit(f"Stopped: this command failed on the VM:\n    {script}")
        return done.returncode == 0

    def send(self, local: Path, remote: str) -> None:
        if subprocess.run([self.scp, *self.options, str(local), f"{ADMIN}@{self.host}:{remote}"]).returncode:
            sys.exit("Stopped: the upload to the VM failed.")


def read_openrouter_key() -> str:
    """OPENROUTER_API_KEY from the project's .env (it is never printed)."""
    env = PROJECT_ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY" and value.strip():
            return value.strip().strip("\"'")
    sys.exit("--send-openrouter-key: no OPENROUTER_API_KEY in .env")


def pack(staging: Path) -> Path:
    """The cleaned folder as one compressed file (one upload instead of 500 small ones)."""
    archive = staging.parent / "callverse-app.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(staging.iterdir()):
            if path.name != MARKER:
                tar.add(path, arcname=path.name)
    print(f"    Compressed to {archive.stat().st_size / 1e6:.0f} MB")
    return archive


def create_vm(args: argparse.Namespace) -> str:
    """Way B, step 2: the resource group, the VM and its open ports (Azure CLI). Returns its DNS name."""
    az = tool("az", "Install the Azure CLI, or create the VM in the Portal and pass --host.")
    account = json.loads(run([az, "account", "show", "-o", "json"], capture=True, check=False) or "{}")
    if not account:
        sys.exit("Not logged in to Azure: run  az login")
    print(f"    Azure subscription: {account.get('name')}")
    group, name = ["-g", args.group], ["-n", args.vm]
    show = [az, "vm", "show", "-d", *group, *name, "--query", "fqdns", "-o", "tsv"]
    run([az, "group", "create", "--name", args.group, "--location", args.location, "-o", "none"])
    if host := run(show, capture=True, check=False):
        print(f"    The VM {args.vm} already exists: it is reused.")
        return host
    # Student subscriptions only get some sizes in some regions: check before creating anything.
    skus = [
        az,
        "vm",
        "list-skus",
        "-l",
        args.location,
        "--size",
        args.size,
        "--resource-type",
        "virtualMachines",
    ]
    offered = [
        sku
        for sku in json.loads(run([*skus, "-o", "json"], capture=True) or "[]")
        if sku["name"].lower() == args.size.lower()
        and not any(limit.get("type") == "Location" for limit in sku.get("restrictions", []))
    ]
    if not offered:
        sys.exit(f"The size {args.size} is not offered to this subscription in {args.location}: "
                 "try another --size (e.g. Standard_D2s_v5) or --location.")  # fmt: skip
    KNOWN_HOSTS.unlink(missing_ok=True)  # a new VM has a new host key
    # A stable public name: the same subscription always gets the same address.
    label = "callverse-" + hashlib.sha1(account["id"].encode()).hexdigest()[:6]
    print(f"    Creating the VM {args.vm} ({args.size}, {args.location}): about 2-3 minutes...")
    run([
        az, "vm", "create", *group, *name, "--image", IMAGE, "--size", args.size, "--admin-username", ADMIN,
        "--ssh-key-values", f"{args.key}.pub", "--public-ip-sku", "Standard",
        "--public-ip-address-dns-name", label, "--os-disk-size-gb", "64", "--storage-sku", "StandardSSD_LRS",
        "-o", "none",
    ])  # fmt: skip
    # Web traffic in (SSH, port 22, is opened by vm create).
    for priority, port in ((900, "80"), (901, "443")):
        run([az, "vm", "open-port", *group, *name, "--port", port, "--priority", str(priority), "-o", "none"])
    return run(show, capture=True)


def wait_for_site(url: str, minutes: int = 12) -> bool:
    import httpx

    start = time.time()
    while time.time() - start < minutes * 60:
        try:
            if httpx.get(f"{url}/api/health", timeout=10).status_code == 200:
                return True
        except httpx.HTTPError:
            pass  # not up yet, or the HTTPS certificate is still being issued
        time.sleep(10)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--public-key", action="store_true", help="print the public key to paste in the Portal"
    )
    parser.add_argument(
        "--host", help="DNS name of a VM made in the Portal, e.g. NAME.REGION.cloudapp.azure.com"
    )
    parser.add_argument("--key", type=Path, default=SSH_KEY, help=f"SSH private key (default: {SSH_KEY})")
    parser.add_argument(
        "--send-openrouter-key",
        action="store_true",
        help="copy OPENROUTER_API_KEY from .env to the VM (it stays there for later updates); without it, "
        "the agents use their offline templates",
    )
    parser.add_argument(
        "--location", default="francecentral", help="way B: Azure region (default: francecentral)"
    )
    parser.add_argument(
        "--size", default="Standard_B2ms", help="way B: VM size (default: Standard_B2ms, 2 CPU, 8 GB)"
    )
    parser.add_argument(
        "--group", default="callverse-rg", help="way B: resource group (default: callverse-rg)"
    )
    parser.add_argument("--vm", default="callverse-vm", help="way B: VM name (default: callverse-vm)")
    parser.add_argument(
        "--staging",
        type=Path,
        default=Path(tempfile.gettempdir()) / "callverse-azure" / "app",
        help="where the cleaned folder is built (default: your temporary folder, outside OneDrive)",
    )
    args = parser.parse_args()
    if args.public_key:
        print(Path(f"{ensure_key(args.key)}.pub").read_text(encoding="utf-8").strip())
        return
    ensure_key(args.key)
    openrouter_key = read_openrouter_key() if args.send_openrouter_key else None

    staging = build_staging(args.staging.resolve())
    print("4/4 Deploying to Azure")
    host = args.host.strip().lower() if args.host else create_vm(args)
    url, vm = f"https://{host}", Vm(host, args.key)

    print(f"    Connecting to {host}, then installing Docker if needed (1-3 minutes)...")
    for _ in range(30):
        if vm.sh(READY, check=False):
            break
        time.sleep(10)
    else:
        sys.exit("Stopped: cannot reach the VM by SSH (is port 22 open, and the right public key on it?).")

    print("    Sending the app...")
    vm.send(pack(staging), "callverse-app.tar.gz")
    vm.sh(UNPACK)
    # The key goes through SSH's input (never on a command line) into a file only this user can read.
    if openrouter_key:
        vm.sh("umask 077 && cat > ~/callverse.env", stdin=f"OPENROUTER_API_KEY={openrouter_key}\n")
    else:
        vm.sh("umask 077 && touch ~/callverse.env")  # keeps a key sent by an earlier run

    print("    Building the image on the VM (about 10-20 minutes the first time)...")
    vm.sh(BUILD)
    vm.sh(RESTART_APP)
    vm.sh(START_CADDY.format(host=host))

    print(f"    Waiting for {url} ...")
    if not wait_for_site(url):
        vm.sh(LOGS, check=False)
        sys.exit("The site did not answer: see the logs above (are ports 80 and 443 open?).")
    print(f"\nFront office: {url}/\nBack office:  {url}/back-office/\nAPI docs:     {url}/docs")
    print(
        "\nThe VM uses your Azure credit while it runs. In the Azure Portal, on the VM's page: Stop pauses it"
    )
    print(f"(start it again before a demo); deleting the resource group {args.group} removes everything.")


if __name__ == "__main__":
    main()
