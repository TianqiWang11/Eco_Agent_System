"""Project only the public response contract, never internal execution state."""
def public_response(result):
    response = {"answer": str(result.get("answer") or ""), "artifacts": result.get("artifacts") or []}
    if result.get("ue_actions"):
        response["ue_actions"] = result["ue_actions"]
    return response
