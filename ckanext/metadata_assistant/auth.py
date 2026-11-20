"""Authorization for the AI settings: sysadmins only (they pass every check)."""


def ai_settings(context, data_dict):
    return {"success": False}
