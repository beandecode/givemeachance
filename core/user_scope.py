"""Pure user identity helpers shared by HTTP and background workflows."""


def is_admin_user(user_row) -> bool:
    return user_row is not None and int(user_row["is_admin"]) == 1


def profile_scope_user_id(user_row) -> int | None:
    if user_row is None:
        return None
    return int(user_row["id"])


def quota_subject_for_user(user_row) -> str:
    if user_row is None:
        return "anonymous"
    return f"user:{int(user_row['id'])}"
