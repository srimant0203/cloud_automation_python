import os
import io
import tarfile
import requests

TERRAFORM_API = "https://app.terraform.io/api/v2"


# -------------------------------------------------
# Helper: authorization headers
# -------------------------------------------------
def _headers():
    return {
        "Authorization": f"Bearer {os.getenv('TERRAFORM_TOKEN')}",
        "Content-Type": "application/vnd.api+json",
    }


# -------------------------------------------------
# Get or create workspace
# -------------------------------------------------
def get_workspace_id():
    org = os.getenv("TERRAFORM_ORG_NAME")
    workspace = os.getenv("TERRAFORM_WORKSPACE")
    if not org or not workspace:
        raise RuntimeError("TERRAFORM_ORG_NAME or TERRAFORM_WORKSPACE not set in environment variables.")

    url = f"{TERRAFORM_API}/organizations/{org}/workspaces/{workspace}"
    r = requests.get(url, headers=_headers(), timeout=30)

    # If workspace exists, return its ID
    if r.status_code == 200:
        return r.json()["data"]["id"]

    # Otherwise, create it
    payload = {"data": {"type": "workspaces", "attributes": {"name": workspace}}}
    r = requests.post(f"{TERRAFORM_API}/organizations/{org}/workspaces", headers=_headers(), json=payload)
    r.raise_for_status()
    return r.json()["data"]["id"]


# -------------------------------------------------
# Create configuration version
# -------------------------------------------------
def create_configuration_version(workspace_id, auto_queue_runs=False):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}/configuration-versions"
    payload = {"data": {"type": "configuration-versions", "attributes": {"auto-queue-runs": auto_queue_runs}}}
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["data"]


# -------------------------------------------------
# Upload Terraform configuration as .tar.gz
# -------------------------------------------------
def upload_tf_to_url(upload_url, tf_code):
    """
    Upload Terraform configuration to Terraform Cloud as a gzipped tar archive.
    """
    # Create in-memory tar.gz containing a single main.tf file
    buf = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buf) as tar:
        tf_bytes = tf_code.encode("utf-8")
        info = tarfile.TarInfo(name="main.tf")
        info.size = len(tf_bytes)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(tf_bytes))

    buf.seek(0)

    # Upload the archive
    r = requests.put(
        upload_url,
        headers={"Content-Type": "application/octet-stream"},
        data=buf.getvalue(),
        timeout=60,
    )
    r.raise_for_status()


# -------------------------------------------------
# Trigger a plan run
# -------------------------------------------------
def trigger_plan_run(workspace_id, config_id):
    url = f"{TERRAFORM_API}/runs"
    payload = {
        "data": {
            "type": "runs",
            "attributes": {"message": "AI-generated plan", "auto-apply": False},
            "relationships": {
                "workspace": {"data": {"type": "workspaces", "id": workspace_id}},
                "configuration-version": {"data": {"type": "configuration-versions", "id": config_id}},
            },
        }
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["id"]


# -------------------------------------------------
# Check user permissions
# -------------------------------------------------
def check_user_permissions(workspace_id):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}/permissions"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code != 200:
        return False
    return r.json().get("data", {}).get("attributes", {}).get("can-queue-apply", False)


# -------------------------------------------------
# Apply a Terraform run
# -------------------------------------------------
def apply_run(run_id):
    url = f"{TERRAFORM_API}/runs/{run_id}/actions/apply"
    r = requests.post(url, headers=_headers(), timeout=30)
    return r.status_code == 200
