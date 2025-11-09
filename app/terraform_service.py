import os
import io
import tarfile
import requests

TERRAFORM_API = "https://app.terraform.io/api/v2"

def _headers():
    token = os.getenv("TERRAFORM_TOKEN")
    if not token:
        raise RuntimeError("TERRAFORM_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.api+json",
    }

# ---------- Workspace helpers ----------
def get_or_create_workspace_id(org_name, workspace_name):
    url = f"{TERRAFORM_API}/organizations/{org_name}/workspaces/{workspace_name}"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()["data"]["id"]
    payload = {
        "data": {
            "type": "workspaces",
            "attributes": {"name": workspace_name, "auto-apply": True},
        }
    }
    r = requests.post(
        f"{TERRAFORM_API}/organizations/{org_name}/workspaces",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]

def create_workspace(org_name, workspace_name):
    """Creates a new Terraform workspace with auto-apply enabled."""
    url = f"{TERRAFORM_API}/organizations/{org_name}/workspaces"
    payload = {
        "data": {
            "type": "workspaces",
            "attributes": {
                "name": workspace_name,
                "auto-apply": True,  # ✅ enable auto apply
                "execution-mode": "remote",
                "terraform-version": "1.7.5",
            },
        }
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Error creating workspace: {r.text}")
    return r.json()["data"]["id"]

def delete_workspace(workspace_id):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}"
    r = requests.delete(url, headers=_headers(), timeout=30)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Failed to delete workspace: {r.status_code} {r.text}")
    return True

def list_workspaces_in_org(org_name):
    url = f"{TERRAFORM_API}/organizations/{org_name}/workspaces"
    r = requests.get(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    return [{"id": d["id"], "name": d["attributes"]["name"]} for d in data]

# ---------- Variables ----------
def add_env_variable(workspace_id, key, value, sensitive=True):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}/vars"
    payload = {
        "data": {
            "type": "vars",
            "attributes": {
                "key": key,
                "value": value,
                "category": "env",
                "hcl": False,
                "sensitive": sensitive,
            },
        }
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Error adding variable {key}: {r.text}")
    return True

# ---------- Configuration upload / runs ----------
def create_configuration_version(workspace_id, auto_queue_runs=False):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}/configuration-versions"
    payload = {
        "data": {
            "type": "configuration-versions",
            "attributes": {"auto-queue-runs": auto_queue_runs},
        }
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["data"]

def upload_tf_to_url(upload_url, tf_code):
    buf = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buf) as tar:
        tf_bytes = tf_code.encode("utf-8")
        info = tarfile.TarInfo(name="main.tf")
        info.size = len(tf_bytes)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(tf_bytes))
    buf.seek(0)
    r = requests.put(
        upload_url,
        headers={"Content-Type": "application/octet-stream"},
        data=buf.getvalue(),
        timeout=60,
    )
    r.raise_for_status()

def trigger_plan_run(workspace_id, config_id):
    url = f"{TERRAFORM_API}/runs"
    payload = {
        "data": {
            "type": "runs",
            "attributes": {
                "message": "AI-generated plan (auto-apply enabled)",
                "auto-apply": True,  # ✅ runs automatically apply
            },
            "relationships": {
                "workspace": {"data": {"type": "workspaces", "id": workspace_id}},
                "configuration-version": {
                    "data": {"type": "configuration-versions", "id": config_id}
                },
            },
        }
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["id"]

def check_user_permissions(workspace_id):
    url = f"{TERRAFORM_API}/workspaces/{workspace_id}/permissions"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code != 200:
        return False
    return (
        r.json()
        .get("data", {})
        .get("attributes", {})
        .get("can-queue-apply", False)
    )

def apply_run(run_id):
    url = f"{TERRAFORM_API}/runs/{run_id}/actions/apply"
    r = requests.post(url, headers=_headers(), timeout=30)
    return r.status_code == 200




