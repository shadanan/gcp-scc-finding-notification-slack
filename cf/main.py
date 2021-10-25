#!/usr/bin/env python3
import base64
import json
import os

import requests
from google.cloud import secretmanager, securitycenter_v1

PREFIX = "https://console.cloud.google.com/security/command-center/findings"

TEMPLATE = "\n".join(
    ["*Category:* <{link}|{category}>", "*Severity:* {severity}", "*Asset:* {asset}"]
)


def get_slack_api_token():
    client = secretmanager.SecretManagerServiceClient()
    secret_name = client.secret_version_path(
        os.environ["PROJECT_ID"], "slack-api-token", "latest"
    )
    return client.access_secret_version(
        request={"name": secret_name}
    ).payload.data.decode("UTF-8")


def get_finding_detail_page_link(finding_name):
    """Constructs a direct link to the finding detail page."""
    org_id = finding_name.split("/")[1]
    return f"{PREFIX}?organizationId={org_id}&resourceId={finding_name}"


def get_asset(org_id, resource_name):
    """Retrieves the asset corresponding to `resource_name` from SCC."""
    client = securitycenter_v1.SecurityCenterClient()
    maybe_asset = list(
        client.list_assets(
            securitycenter_v1.ListAssetsRequest(
                parent=f"organizations/{org_id}",
                filter=f'security_center_properties.resource_name = "{resource_name}"',
            )
        )
    )
    if len(maybe_asset) == 1:
        return maybe_asset[0].asset
    return securitycenter_v1.Asset()


def process_finding(finding):
    asset = get_asset(finding["parent"].split("/")[1], finding["resourceName"])

    token = get_slack_api_token()
    content = TEMPLATE.format(
        link=get_finding_detail_page_link(finding["name"]),
        category=finding["category"],
        severity=finding["severity"],
        asset=asset.security_center_properties.resource_display_name,
    )

    requests.post(
        "https://slack.com/api/chat.postMessage",
        data={
            "token": token,
            "channel": "#general",
            "text": content,
        },
    )


def decode_finding(data):
    """Decode the finding from the data payload."""
    pubsub_message = base64.b64decode(data).decode("utf-8")
    return json.loads(pubsub_message)["finding"]


def process_notification(event, context):
    """Process the finding notification."""
    try:
        process_finding(decode_finding(event["data"]))
    except requests.exceptions.HTTPError as err:
        print(err.response.text)
        raise err
