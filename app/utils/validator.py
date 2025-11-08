import re

def simple_hcl_sanity_check(hcl_code: str):
    if not hcl_code or len(hcl_code.strip()) < 30:
        return False, "HCL too short or empty"
    if "resource" not in hcl_code:
        return False, "No resource block found"
    if "provider" not in hcl_code:
        return False, "No provider block found"
    if re.search(r"(bash|curl|sudo|rm\s+-rf)", hcl_code, re.IGNORECASE):
        return False, "Unsafe content found"
    return True, "OK"
