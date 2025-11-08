from flask import Blueprint, render_template_string, request
from app.ai_integration import generate_tf_code
from app.utils.validator import simple_hcl_sanity_check
from app.terraform_service import (
    get_workspace_id,
    create_configuration_version,
    upload_tf_to_url,
    trigger_plan_run,
    check_user_permissions,
    apply_run,
)

main_bp = Blueprint("main", __name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>AI Terraform Cloud Deployer</title></head>
<body style="font-family: Arial, sans-serif; margin:40px;">
  <h2>AI → Terraform Cloud Deployer</h2>

  <form method="post" action="/generate">
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
      <form method="post" action="/apply">
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

@main_bp.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE)

@main_bp.route("/generate", methods=["POST"])
def generate():
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return "Provide a deployment prompt.", 400

    try:
        tf_code = generate_tf_code(prompt)
    except Exception as e:
        return f"Error generating code: {e}", 500

    ok, msg = simple_hcl_sanity_check(tf_code)
    if not ok:
        return f"Validation failed: {msg}", 400

    try:
        workspace_id = get_workspace_id()
        conf = create_configuration_version(workspace_id, auto_queue_runs=False)
        upload_tf_to_url(conf["attributes"]["upload-url"], tf_code)
        run_id = trigger_plan_run(workspace_id, conf["id"])
        plan_msg = f"Plan queued successfully. Run ID: {run_id}"
    except Exception as e:
        return f"Terraform Cloud error: {e}", 500

    can_apply = check_user_permissions(workspace_id)
    return render_template_string(
        HTML_TEMPLATE, tf_code=tf_code, plan_msg=plan_msg, can_apply=can_apply, run_id=run_id
    )

@main_bp.route("/apply", methods=["POST"])
def apply():
    run_id = request.form.get("run_id")
    try:
        ok = apply_run(run_id)
        if ok:
            return f"Apply request submitted for run {run_id}."
        else:
            return "Failed to start apply.", 500
    except Exception as e:
        return f"Apply error: {e}", 500
