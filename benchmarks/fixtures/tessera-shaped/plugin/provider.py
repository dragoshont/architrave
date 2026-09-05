def authentication_state() -> dict[str, str]:
    return {
        "type": "AUTH_REQUIRED",
        "principal": "fixture-user",
        "provider": "fixture-mail",
        "resolutionRef": "evidence:fixture-auth-resolved",
    }