from flask import Blueprint, render_template_string, request, redirect, url_for, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

from app.ai_integration import generate_tf_code
from app.terraform_service import (
    create_workspace,
    delete_workspace,
    list_workspaces_in_org,
    add_env_variable,
    create_configuration_version,
    upload_tf_to_url,
    trigger_plan_run,
    check_user_permissions,
    apply_run,
)
from app.utils.validator import simple_hcl_sanity_check

main_bp = Blueprint("main", __name__)

# ------------------ Helpers ------------------
def _require_login():
    return "user" in session

def _get_current_user():
    """Fetch current logged-in user safely."""
    user_email = session.get("user")
    if not user_email:
        return None
    user = current_app.mongo.users.find_one({"email": user_email})
    return user

# ------------------ Templates ------------------
LOGIN_HTML = """
<h2>Login</h2>
<form method="post" action="{{ url_for('main.login') }}">
  Email: <input name="email" type="email" required><br/>
  Password: <input name="password" type="password" required><br/>
  <button type="submit">Login</button>
</form>
<p>New here? <a href="{{ url_for('main.register') }}">Register</a></p>
"""

REGISTER_HTML = """
<h2>Register</h2>
<form method="post" action="{{ url_for('main.register') }}">
  Email: <input name="email" type="email" required><br/>
  Password: <input name="password" type="password" required><br/>
  <button type="submit">Create account</button>
</form>
<p>Already have an account? <a href="{{ url_for('main.login') }}">Login</a></p>
"""

DASHBOARD_HTML = """
<h2>Welcome {{ user }}</h2>
<p><a href="{{ url_for('main.logout') }}">Logout</a></p>

<h3>Your Workspaces</h3>
<ul>
{% for ws in workspaces %}
  <li>
    {{ ws.name }} (id: {{ ws.workspace_id }})
    — <a href="{{ url_for('main.open_workspace', wid=ws._id) }}">Open</a>
    — <a href="{{ url_for('main.manage_vars', wid=ws._id) }}">Env Vars</a>
    — <a href="{{ url_for('main.delete_workspace_route', wid=ws._id) }}">Delete</a>
  </li>
{% endfor %}
</ul>

<h3>Create Workspace</h3>
<form method="post" action="{{ url_for('main.create_workspace_route') }}">
  <input name="workspace_name" placeholder="e.g. ai-demo" required />
  <button type="submit">Create</button>
</form>

<h3>Import My Workspaces</h3>
<form method="post" action="{{ url_for('main.import_workspaces') }}">
  <button type="submit">Import</button>
</form>
"""

VARS_HTML = """
<h2>Manage Env Vars — {{ ws.name }}</h2>
<form method="post">
  Key: <input name="key" required> &nbsp;
  Value: <input name="value" required> &nbsp;
  Sensitive: <input type="checkbox" name="sensitive" checked>
  <button type="submit">Add</button>
</form>
<p><a href="{{ url_for('main.dashboard') }}">Back</a></p>
<ul>
{% for v in vars %}
  <li>{{ v.key }} = {% if v.sensitive %}(sensitive){% else %}{{ v.value }}{% endif %}</li>
{% endfor %}
</ul>
"""

PROMPT_HTML = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>AI Terraform Cloud Deployer</title></head>
<body style="font-family: Arial, sans-serif; margin:40px;">
  <h2>Workspace: {{ ws_name }}</h2>
  <p><a href="{{ url_for('main.dashboard') }}">Back to Dashboard</a></p>

  <form method="post" action="{{ url_for('main.generate') }}">
    <label><b>Deployment prompt</b></label><br/>
    <textarea name="prompt" rows="5" cols="80" placeholder="e.g. Create an Azure resource group in East US"></textarea><br/><br/>
    <button type="submit">Generate Terraform Plan</button>
  </form>

  {% if tf_code %}
    <hr/>
    <h3>Generated Terraform HCL</h3>
    <pre style="background:#f3f3f3;padding:12px;border-radius:6px;max-height:400px;overflow:auto;">{{ tf_code }}</pre>

    <h3>Plan</h3>
    <p>{{ plan_msg }}</p>

    {% if can_apply %}
      <form method="post" action="{{ url_for('main.apply') }}">
        <input type="hidden" name="run_id" value="{{ run_id }}" />
        <button type="submit">🚀 Apply (Run on Terraform Cloud)</button>
      </form>
    {% else %}
      <p style="color:crimson;"><i>Apply disabled — insufficient Terraform Cloud permissions.</i></p>
    {% endif %}
  {% endif %}
</body>
</html>
"""

# ------------------ Auth routes ------------------
@main_bp.route("/", methods=["GET"])
def root():
    return redirect(url_for("main.dashboard") if _require_login() else url_for("main.login"))

@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = current_app.mongo.users.find_one({"email": email})
        if not user or not check_password_hash(user["password"], password):
            return "Invalid credentials", 401
        session["user"] = email
        return redirect(url_for("main.dashboard"))
    return render_template_string(LOGIN_HTML)

@main_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if current_app.mongo.users.find_one({"email": email}):
            return "User already exists. Please login.", 400
        hashed = generate_password_hash(password)
        current_app.mongo.users.insert_one({"email": email, "password": hashed, "workspaces": []})
        session["user"] = email
        return redirect(url_for("main.dashboard"))
    return render_template_string(REGISTER_HTML)

@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))

# ------------------ Dashboard & Workspaces ------------------
@main_bp.route("/dashboard", methods=["GET"])
def dashboard():
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    workspaces = user.get("workspaces", [])
    for ws in workspaces:
        ws["_id"] = str(ws["_id"])
    return render_template_string(DASHBOARD_HTML, user=session["user"], workspaces=workspaces)

@main_bp.route("/workspace/create", methods=["POST"])
def create_workspace_route():
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    ws_name = request.form.get("workspace_name", "").strip()
    if not ws_name:
        return "Workspace name required", 400

    org = current_app.config.get("TERRAFORM_ORG_NAME")
    user_email = session["user"]

    try:
        ws_id = create_workspace(org, ws_name)
        # ✅ Auto-run immediately after creation
        create_configuration_version(ws_id, auto_queue_runs=True)
    except Exception as e:
        return f"Terraform Cloud error: {e}", 500

    ws_doc = {
        "_id": ObjectId(),
        "name": ws_name,
        "workspace_id": ws_id,
        "vars": [],
        "owner": user_email,
    }
    current_app.mongo.users.update_one({"email": user_email}, {"$push": {"workspaces": ws_doc}})
    return redirect(url_for("main.dashboard"))

@main_bp.route("/workspaces/import", methods=["POST"])
def import_workspaces():
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    org = current_app.config.get("TERRAFORM_ORG_NAME")
    user_email = session["user"]

    try:
        remote_ws = list_workspaces_in_org(org)
    except Exception as e:
        return f"Error listing remote workspaces: {e}", 500

    existing_ids = {ws["workspace_id"] for ws in user.get("workspaces", [])}
    user_prefix = user_email.split("@")[0].lower()
    owned_remote = [r for r in remote_ws if r["name"].startswith(user_prefix)]

    to_add = []
    for r in owned_remote:
        if r["id"] not in existing_ids:
            ws_doc = {
                "_id": ObjectId(),
                "name": r["name"],
                "workspace_id": r["id"],
                "vars": [],
                "owner": user_email,
            }
            to_add.append(ws_doc)

    if to_add:
        current_app.mongo.users.update_one(
            {"email": user_email},
            {"$push": {"workspaces": {"$each": to_add}}},
        )

    return redirect(url_for("main.dashboard"))

@main_bp.route("/workspace/<wid>/delete", methods=["GET"])
def delete_workspace_route(wid):
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    ws = next((w for w in user.get("workspaces", []) if str(w["_id"]) == wid), None)
    if not ws:
        return "Workspace not found", 404
    try:
        delete_workspace(ws["workspace_id"])
    except Exception:
        pass
    current_app.mongo.users.update_one({"email": user["email"]}, {"$pull": {"workspaces": {"_id": ObjectId(wid)}}})
    return redirect(url_for("main.dashboard"))

@main_bp.route("/workspace/<wid>/vars", methods=["GET", "POST"])
def manage_vars(wid):
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    ws = next((w for w in user.get("workspaces", []) if str(w["_id"]) == wid), None)
    if not ws:
        return "Workspace not found", 404

    if request.method == "POST":
        key = request.form.get("key", "").strip()
        value = request.form.get("value", "").strip()
        sensitive = True if request.form.get("sensitive") else False
        if not key or not value:
            return "Key and value required", 400
        try:
            add_env_variable(ws["workspace_id"], key, value, sensitive=sensitive)
        except Exception as e:
            return f"Error adding variable: {e}", 500
        current_app.mongo.users.update_one(
            {"email": user["email"], "workspaces._id": ObjectId(wid)},
            {"$push": {"workspaces.$.vars": {"key": key, "value": (None if sensitive else value), "sensitive": sensitive}}},
        )
        return redirect(url_for("main.manage_vars", wid=wid))

    return render_template_string(VARS_HTML, ws=ws, vars=ws.get("vars", []))

@main_bp.route("/workspace/<wid>/open", methods=["GET"])
def open_workspace(wid):
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    ws = next((w for w in user.get("workspaces", []) if str(w["_id"]) == wid), None)
    if not ws:
        return "Workspace not found", 404
    session["selected_workspace_id"] = ws["workspace_id"]
    session["selected_workspace_name"] = ws["name"]
    return redirect(url_for("main.prompt"))

# ------------------ Prompt / Plan / Apply ------------------
@main_bp.route("/prompt", methods=["GET"])
def prompt():
    if not _require_login():
        return redirect(url_for("main.login"))
    ws_name = session.get("selected_workspace_name", "(none selected)")
    return render_template_string(PROMPT_HTML, ws_name=ws_name)

@main_bp.route("/generate", methods=["POST"])
def generate():
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    prompt_text = request.form.get("prompt", "").strip()
    if not prompt_text:
        return "Provide a deployment prompt.", 400

    try:
        tf_code = generate_tf_code(prompt_text)
    except Exception as e:
        return f"Error generating code: {e}", 500

    ok, msg = simple_hcl_sanity_check(tf_code)
    if not ok:
        return f"Validation failed: {msg}", 400

    workspace_id = session.get("selected_workspace_id")
    if not workspace_id:
        return "No workspace selected. Go back and open a workspace first.", 400

    try:
        conf = create_configuration_version(workspace_id, auto_queue_runs=True)
        upload_tf_to_url(conf["attributes"]["upload-url"], tf_code)
        run_id = trigger_plan_run(workspace_id, conf["id"])
        plan_msg = f"Plan queued successfully. Run ID: {run_id}"
    except Exception as e:
        return f"Terraform Cloud error: {e}", 500

    can_apply = check_user_permissions(workspace_id)
    return render_template_string(
        PROMPT_HTML,
        ws_name=session.get("selected_workspace_name"),
        tf_code=tf_code,
        plan_msg=plan_msg,
        can_apply=can_apply,
        run_id=run_id,
    )

@main_bp.route("/apply", methods=["POST"])
def apply():
    if not _require_login():
        return redirect(url_for("main.login"))
    user = _get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("main.login"))

    run_id = request.form.get("run_id")
    try:
        ok = apply_run(run_id)
        if ok:
            return f"Apply request submitted for run {run_id}."
        else:
            return "Failed to start apply.", 500
    except Exception as e:
        return f"Apply error: {e}", 500





